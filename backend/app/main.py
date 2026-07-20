from contextlib import asynccontextmanager
from datetime import UTC, datetime
import asyncio
import copy
import logging
from typing import Literal
import uuid

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .ai import (
    AIProvider,
    AIProviderError,
    LocalImageProvider,
    OllamaProvider,
    OllamaProviderError,
    RemoteAIProvider,
)
from .database import SessionLocal, engine, get_session
from .models import (
    AIProviderConfig,
    GenerationJob,
    Presentation,
    PresentationStatus,
    PresentationVersion,
)
from .rendering import (
    PresentationRenderError,
    add_fade_transitions,
    presentation_asset_paths,
    remove_presentation_files,
    render_presentation,
)
from .security import decrypt_api_key, encrypt_api_key
from .schemas import (
    AIProviderConfigCreate,
    AIProviderConfigRead,
    AIProviderConfigUpdate,
    AIProviderConnectionRead,
    AIProviderRead,
    GeneratedDeck,
    GenerationJobCreated,
    GenerationJobRead,
    GenerationJobSummaryRead,
    GenerationRequest,
    GenerationResponse,
    HealthRead,
    OllamaConnectionRead,
    OllamaModelRead,
    PresentationCreate,
    PresentationOutline,
    PresentationOutlineUpdate,
    PresentationBatchDelete,
    PresentationContentUpdate,
    PresentationDetailRead,
    PresentationDeleteResult,
    PresentationRead,
    PresentationRenderRead,
    PresentationVersionDetailRead,
    PresentationVersionRead,
    SourceExtractionResponse,
)
from .source_parser import extract_source_bytes


settings = get_settings()
logger = logging.getLogger(__name__)


def get_ollama_provider() -> OllamaProvider:
    return OllamaProvider(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_seconds=settings.ollama_timeout_seconds,
    )


def build_ai_provider(
    *,
    provider_type: str,
    base_url: str,
    model: str,
    api_key: str | None = None,
) -> AIProvider:
    if provider_type == "ollama":
        return OllamaProvider(
            base_url=base_url,
            model=model,
            timeout_seconds=settings.ollama_timeout_seconds,
        )
    if provider_type not in {"openai", "anthropic", "gemini", "openai_compatible"}:
        raise ValueError(f"不支援的 AI Provider：{provider_type}")
    return RemoteAIProvider(
        provider_type=provider_type,  # type: ignore[arg-type]
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout_seconds=settings.ollama_timeout_seconds,
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        if settings.database_required_on_startup:
            raise
        logger.warning(
            "PostgreSQL is unavailable; generation API will remain available: %s",
            exc,
        )
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _presentation_urls(
    presentation: Presentation,
) -> tuple[list[str], str | None, str | None]:
    if presentation.last_rendered_revision != presentation.revision:
        return [], None, None
    pptx, pdf, previews = presentation_asset_paths(
        settings.presentation_storage_dir, presentation.id
    )
    version = int(presentation.updated_at.timestamp())
    preview_urls = [
        f"/api/v1/presentations/{presentation.id}/preview/{index}?v={version}"
        for index, _ in enumerate(previews, start=1)
    ]
    pptx_url = (
        f"/api/v1/presentations/{presentation.id}/download/pptx" if pptx.exists() else None
    )
    pdf_url = (
        f"/api/v1/presentations/{presentation.id}/download/pdf" if pdf.exists() else None
    )
    return preview_urls, pptx_url, pdf_url


def _presentation_read(presentation: Presentation) -> PresentationRead:
    pptx, pdf, previews = presentation_asset_paths(
        settings.presentation_storage_dir, presentation.id
    )
    has_unrendered_changes = (
        presentation.content is not None
        and presentation.last_rendered_revision != presentation.revision
    )
    has_current_output = (
        presentation.last_rendered_revision == presentation.revision
        and pptx.exists()
        and pdf.exists()
        and bool(previews)
    )
    return PresentationRead(
        id=presentation.id,
        title=presentation.title,
        language=presentation.language,
        template=presentation.template,
        status=presentation.status,
        confirmed_at=presentation.confirmed_at,
        created_at=presentation.created_at,
        updated_at=presentation.updated_at,
        slide_count=presentation.slide_count,
        has_output=has_current_output,
        revision=presentation.revision,
        last_rendered_revision=presentation.last_rendered_revision,
        has_unrendered_changes=has_unrendered_changes,
        failed_stage=presentation.failed_stage,
        last_error=presentation.last_error,
        can_retry=(
            presentation.status == PresentationStatus.FAILED
            and (
                presentation.generation_settings is not None
                or (presentation.failed_stage == "render" and presentation.content is not None)
            )
        ),
    )


def _ensure_presentation_downloadable(presentation: Presentation) -> None:
    if (
        presentation.status != PresentationStatus.COMPLETED
        or presentation.confirmed_at is None
    ):
        raise HTTPException(status_code=409, detail="請先確認簡報內容再下載")
    if presentation.last_rendered_revision != presentation.revision:
        raise HTTPException(status_code=409, detail="簡報內容已修改，請先更新預覽")


def _duplicate_deck(source_title: str, content: dict) -> GeneratedDeck:
    source_deck = GeneratedDeck.model_validate(copy.deepcopy(content))
    duplicated_title = f"{source_title[:176]}（副本）"
    return source_deck.model_copy(
        update={
            "title": duplicated_title,
            "slides": [
                slide.model_copy(update={"id": uuid.uuid4()})
                for slide in source_deck.slides
            ],
        }
    )


@app.get(
    "/api/v1/ai-provider",
    response_model=AIProviderRead,
    tags=["ai-providers"],
)
async def get_ai_provider() -> AIProviderRead:
    return AIProviderRead(
        provider="ollama",
        model=settings.ollama_model,
        image_model=settings.ollama_image_model,
    )


@app.post(
    "/api/v1/ai-provider/test",
    response_model=AIProviderConnectionRead,
    tags=["ai-providers"],
)
async def test_ai_provider() -> AIProviderConnectionRead:
    connected, models, error = await get_ollama_provider().test_connection()
    return AIProviderConnectionRead(
        connected=connected,
        provider="ollama",
        model=settings.ollama_model,
        available_models=models,
        error=error,
    )


@app.get(
    "/api/v1/ai-providers/ollama/models",
    response_model=list[OllamaModelRead],
    tags=["ai-providers"],
)
async def list_ollama_models() -> list[OllamaModelRead]:
    try:
        return await get_ollama_provider().list_models()
    except OllamaProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post(
    "/api/v1/ai-providers/ollama/test",
    response_model=OllamaConnectionRead,
    tags=["ai-providers"],
)
async def test_ollama_connection() -> OllamaConnectionRead:
    connected, models, error = await get_ollama_provider().test_connection()
    return OllamaConnectionRead(
        connected=connected,
        base_url=settings.ollama_base_url,
        configured_model=settings.ollama_model,
        available_models=models,
        error=error,
    )


@app.get(
    "/api/v1/ai-providers",
    response_model=list[AIProviderConfigRead],
    tags=["ai-providers"],
)
async def list_ai_provider_configs(
    session: AsyncSession = Depends(get_session),
) -> list[AIProviderConfig]:
    result = await session.scalars(
        select(AIProviderConfig).order_by(AIProviderConfig.created_at.asc())
    )
    return list(result)


@app.post(
    "/api/v1/ai-providers",
    response_model=AIProviderConfigRead,
    status_code=status.HTTP_201_CREATED,
    tags=["ai-providers"],
)
async def create_ai_provider_config(
    payload: AIProviderConfigCreate,
    session: AsyncSession = Depends(get_session),
) -> AIProviderConfig:
    config = AIProviderConfig(
        name=payload.name,
        provider=payload.provider,
        base_url=payload.base_url.rstrip("/"),
        model=payload.model,
        image_model=payload.image_model or None,
        encrypted_api_key=encrypt_api_key(payload.api_key),
    )
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config


@app.patch(
    "/api/v1/ai-providers/{provider_id}",
    response_model=AIProviderConfigRead,
    tags=["ai-providers"],
)
async def update_ai_provider_config(
    provider_id: uuid.UUID,
    payload: AIProviderConfigUpdate,
    session: AsyncSession = Depends(get_session),
) -> AIProviderConfig:
    config = await session.get(AIProviderConfig, provider_id)
    if config is None:
        raise HTTPException(status_code=404, detail="找不到 AI Provider 設定")
    changes = payload.model_dump(exclude_unset=True)
    if "api_key" in changes:
        config.encrypted_api_key = encrypt_api_key(changes.pop("api_key"))
    for field, value in changes.items():
        if field == "base_url" and isinstance(value, str):
            value = value.rstrip("/")
        setattr(config, field, value)
    await session.commit()
    await session.refresh(config)
    return config


@app.delete(
    "/api/v1/ai-providers/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["ai-providers"],
)
async def delete_ai_provider_config(
    provider_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    config = await session.get(AIProviderConfig, provider_id)
    if config is None:
        raise HTTPException(status_code=404, detail="找不到 AI Provider 設定")
    await session.delete(config)
    await session.commit()


@app.post(
    "/api/v1/ai-providers/{provider_id}/test",
    response_model=AIProviderConnectionRead,
    tags=["ai-providers"],
)
async def test_ai_provider_config(
    provider_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> AIProviderConnectionRead:
    config = await session.get(AIProviderConfig, provider_id)
    if config is None:
        raise HTTPException(status_code=404, detail="找不到 AI Provider 設定")
    try:
        if config.provider == "stable_diffusion":
            provider = LocalImageProvider(
                base_url=config.base_url,
                model=config.model,
                timeout_seconds=settings.ollama_timeout_seconds,
            )
        else:
            provider = build_ai_provider(
                provider_type=config.provider,
                base_url=config.base_url,
                model=config.model,
                api_key=decrypt_api_key(config.encrypted_api_key),
            )
        connected, models, error = await provider.test_connection()
    except (AIProviderError, ValueError) as exc:
        connected, models, error = False, [], str(exc)
    return AIProviderConnectionRead(
        connected=connected,
        provider=config.provider,
        model=config.model,
        available_models=models,
        error=error,
    )


@app.post(
    "/api/v1/sources/extract",
    response_model=SourceExtractionResponse,
    tags=["sources"],
)
async def extract_sources(files: list[UploadFile] = File(...)) -> SourceExtractionResponse:
    if not files or len(files) > 8:
        raise HTTPException(status_code=422, detail="一次請上傳 1 至 8 個檔案")
    results = []
    for upload in files:
        data = await upload.read()
        result = await asyncio.to_thread(
            extract_source_bytes, upload.filename or "未命名檔案", data
        )
        results.append(result)
    successful = [
        f"[{item.filename}]\n{item.text}" for item in results if item.status == "success"
    ]
    return SourceExtractionResponse(
        files=results,
        combined_text="\n\n".join(successful)[:60_000],
    )


class DeckGenerationFailure(Exception):
    def __init__(self, stage: str, message: str, status_code: int = 502):
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.status_code = status_code


async def _generate_outline(
    payload: GenerationRequest,
) -> tuple[PresentationOutline, str, str]:
    provider: AIProvider = get_ollama_provider()
    provider_type = "ollama"
    if payload.provider_id is not None:
        async with SessionLocal() as session:
            config = await session.get(AIProviderConfig, payload.provider_id)
        if config is None:
            raise DeckGenerationFailure("outline", "找不到選擇的 AI Provider", 404)
        try:
            provider = build_ai_provider(
                provider_type=config.provider,
                base_url=config.base_url,
                model=config.model,
                api_key=decrypt_api_key(config.encrypted_api_key),
            )
        except ValueError as exc:
            raise DeckGenerationFailure("outline", str(exc), 422) from exc
        provider_type = config.provider
    try:
        outline = await provider.generate_outline(payload)
    except AIProviderError as exc:
        logger.warning(
            "AI outline generation failed (provider=%s, model=%s): %s",
            provider_type,
            provider.model,
            exc,
        )
        raise DeckGenerationFailure("outline", str(exc)) from exc
    return outline, provider_type, provider.model


async def _generate_deck(
    payload: GenerationRequest,
) -> tuple[GeneratedDeck, str, str]:
    provider: AIProvider = get_ollama_provider()
    provider_type = "ollama"
    if payload.provider_id is not None:
        async with SessionLocal() as session:
            config = await session.get(AIProviderConfig, payload.provider_id)
        if config is None:
            raise DeckGenerationFailure("content", "找不到選擇的 AI Provider", 404)
        try:
            provider = build_ai_provider(
                provider_type=config.provider,
                base_url=config.base_url,
                model=config.model,
                api_key=decrypt_api_key(config.encrypted_api_key),
            )
        except ValueError as exc:
            raise DeckGenerationFailure("content", str(exc), 422) from exc
        provider_type = config.provider
    try:
        deck = await provider.generate_deck(payload)
    except AIProviderError as exc:
        logger.warning(
            "AI deck generation failed (provider=%s, model=%s): %s",
            provider_type,
            provider.model,
            exc,
        )
        raise DeckGenerationFailure("content", str(exc)) from exc

    if payload.generate_images:
        image_config = None
        ollama_image_provider = None
        if payload.image_provider_id is None:
            ollama_image_provider = get_ollama_provider()
            local_image_provider = None
            remote_image_provider = None
        else:
            async with SessionLocal() as session:
                image_config = await session.get(AIProviderConfig, payload.image_provider_id)
            if image_config is None:
                raise DeckGenerationFailure("images", "找不到圖片生成 Provider", 404)
            if image_config.provider not in {
                "ollama",
                "openai",
                "openai_compatible",
                "stable_diffusion",
            }:
                raise DeckGenerationFailure("images", "此 Provider 尚不支援圖片生成", 422)
            if image_config.provider in {"ollama", "openai_compatible"} and not image_config.image_model:
                raise DeckGenerationFailure(
                    "images", "此圖片 Provider 需要設定圖片模型", 422
                )
        if image_config is not None and image_config.provider == "ollama":
            ollama_image_provider = OllamaProvider(
                base_url=image_config.base_url,
                model=image_config.model,
                timeout_seconds=settings.ollama_timeout_seconds,
            )
            local_image_provider = None
            remote_image_provider = None
        elif image_config is not None and image_config.provider == "stable_diffusion":
            local_image_provider = LocalImageProvider(
                base_url=image_config.base_url,
                model=image_config.model,
                timeout_seconds=settings.ollama_timeout_seconds,
            )
            remote_image_provider = None
        elif image_config is not None:
            local_image_provider = None
            remote_image_provider = RemoteAIProvider(
                provider_type=image_config.provider,  # type: ignore[arg-type]
                base_url=image_config.base_url,
                model=image_config.model,
                api_key=decrypt_api_key(image_config.encrypted_api_key),
                timeout_seconds=settings.ollama_timeout_seconds,
            )
        generated = 0
        slides = []
        for slide in deck.slides:
            if (
                generated < payload.image_count
                and slide.kind not in {
                    "cover",
                    "section",
                    "comparison",
                    "quote",
                    "closing",
                }
            ):
                visual_prompt = slide.visual_prompt or f"{slide.title}。{slide.body}"
                prompt = (
                    f"{visual_prompt}. Purely visual editorial illustration for a presentation, "
                    "landscape composition, abstract or photographic scene, clean focal subject. "
                    "Do not draw words, letters, numbers, signs, labels, logos, screens, "
                    "packaging, captions, typography, or watermarks."
                )
                try:
                    if ollama_image_provider is not None:
                        image_data = await ollama_image_provider.generate_image(
                            prompt,
                            image_model=(
                                image_config.image_model
                                if image_config is not None
                                else settings.ollama_image_model
                            ),
                        )
                    elif local_image_provider is not None:
                        image_data = await local_image_provider.generate_image(prompt)
                    elif image_config is not None and image_config.image_model:
                        assert remote_image_provider is not None
                        image_data = await remote_image_provider.generate_image(
                            prompt,
                            image_model=image_config.image_model,
                        )
                    else:
                        assert remote_image_provider is not None
                        image_data = await remote_image_provider.generate_image_with_tool(prompt)
                except AIProviderError as exc:
                    logger.warning("AI image generation failed: %s", exc)
                    raise DeckGenerationFailure("images", str(exc)) from exc
                slide = slide.model_copy(update={"image_data": image_data})
                generated += 1
            slides.append(slide)
        deck = deck.model_copy(update={"slides": slides})

    return deck, provider_type, provider.model


async def _mark_generation_failed(
    presentation_id: uuid.UUID,
    failure: DeckGenerationFailure,
) -> None:
    async with SessionLocal() as session:
        presentation = await session.get(Presentation, presentation_id)
        if presentation is None:
            return
        presentation.status = PresentationStatus.FAILED
        presentation.failed_stage = failure.stage
        presentation.last_error = failure.message
        await session.commit()


async def _active_generation_job(
    session: AsyncSession, presentation_id: uuid.UUID
) -> GenerationJob | None:
    return await session.scalar(
        select(GenerationJob)
        .where(
            GenerationJob.presentation_id == presentation_id,
            GenerationJob.status.in_(["QUEUED", "RUNNING"]),
        )
        .order_by(GenerationJob.created_at.desc())
    )


def _generation_job_can_retry(
    job_status: str,
    presentation_status: PresentationStatus,
    position: int,
) -> bool:
    return (
        position == 1
        and job_status == "FAILED"
        and presentation_status == PresentationStatus.FAILED
    )


@app.get(
    "/api/v1/generation-jobs",
    response_model=list[GenerationJobSummaryRead],
    tags=["generation-jobs"],
)
async def list_generation_jobs(
    state: Literal["all", "active", "completed", "failed", "canceled"] = Query(
        default="all"
    ),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[GenerationJobSummaryRead]:
    ranked_jobs = (
        select(
            GenerationJob.id.label("job_id"),
            func.row_number()
            .over(
                partition_by=GenerationJob.presentation_id,
                order_by=(GenerationJob.created_at.desc(), GenerationJob.id.desc()),
            )
            .label("position"),
        )
        .subquery()
    )
    query = (
        select(
            GenerationJob,
            Presentation.title,
            Presentation.status,
            ranked_jobs.c.position,
        )
        .join(Presentation, Presentation.id == GenerationJob.presentation_id)
        .join(ranked_jobs, ranked_jobs.c.job_id == GenerationJob.id)
        .order_by(GenerationJob.created_at.desc())
        .limit(limit)
    )
    if state == "active":
        query = query.where(GenerationJob.status.in_(["QUEUED", "RUNNING"]))
    elif state == "completed":
        query = query.where(GenerationJob.status == "COMPLETED")
    elif state == "failed":
        query = query.where(GenerationJob.status == "FAILED")
    elif state == "canceled":
        query = query.where(GenerationJob.status == "CANCELED")
    rows = await session.execute(query)
    return [
        GenerationJobSummaryRead(
            **GenerationJobRead.model_validate(job).model_dump(),
            presentation_title=presentation_title,
            presentation_status=presentation_status,
            can_retry=_generation_job_can_retry(
                job.status, presentation_status, position
            ),
        )
        for job, presentation_title, presentation_status, position in rows
    ]


@app.post(
    "/api/v1/generation-jobs/outline",
    response_model=GenerationJobCreated,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["generation-jobs"],
)
async def create_outline_generation_job(
    payload: GenerationRequest,
    session: AsyncSession = Depends(get_session),
) -> GenerationJobCreated:
    presentation = Presentation(
        title=payload.topic[:180],
        language=payload.language,
        template=payload.template,
        status=PresentationStatus.GENERATING_CONTENT,
        source_text=payload.source_text,
        generation_settings=payload.model_dump(mode="json"),
    )
    session.add(presentation)
    await session.flush()
    job = GenerationJob(
        presentation_id=presentation.id,
        job_type="outline",
        status="QUEUED",
        stage="queued",
        progress=5,
        payload={"request": payload.model_dump(mode="json")},
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return GenerationJobCreated(
        presentation_id=presentation.id,
        job=GenerationJobRead.model_validate(job),
    )


@app.patch(
    "/api/v1/presentations/{presentation_id}/outline",
    response_model=PresentationOutline,
    tags=["generation-jobs"],
)
async def update_presentation_outline(
    presentation_id: uuid.UUID,
    payload: PresentationOutlineUpdate,
    session: AsyncSession = Depends(get_session),
) -> PresentationOutline:
    presentation = await session.get(Presentation, presentation_id)
    if presentation is None:
        raise HTTPException(status_code=404, detail="找不到簡報")
    if await _active_generation_job(session, presentation_id) is not None:
        raise HTTPException(status_code=409, detail="簡報仍有進行中的生成任務")
    outline = PresentationOutline.model_validate(payload.model_dump(mode="json"))
    if outline.items[0].kind != "cover" or outline.items[-1].kind != "closing":
        raise HTTPException(status_code=422, detail="大綱必須以封面開始並以結尾結束")
    presentation.title = outline.title
    presentation.language = outline.language
    presentation.outline = outline.model_dump(mode="json")
    presentation.status = PresentationStatus.DRAFT
    presentation.failed_stage = None
    presentation.last_error = None
    await session.commit()
    return outline


@app.post(
    "/api/v1/presentations/{presentation_id}/generation-jobs/content",
    response_model=GenerationJobRead,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["generation-jobs"],
)
async def create_content_generation_job(
    presentation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> GenerationJobRead:
    presentation = await session.scalar(
        select(Presentation)
        .where(Presentation.id == presentation_id)
        .with_for_update()
    )
    if presentation is None:
        raise HTTPException(status_code=404, detail="找不到簡報")
    if presentation.outline is None or presentation.generation_settings is None:
        raise HTTPException(status_code=409, detail="請先完成並儲存簡報大綱")
    if await _active_generation_job(session, presentation_id) is not None:
        raise HTTPException(status_code=409, detail="簡報仍有進行中的生成任務")
    job = GenerationJob(
        presentation_id=presentation.id,
        job_type="content",
        status="QUEUED",
        stage="queued",
        progress=5,
        payload={
            "request": copy.deepcopy(presentation.generation_settings),
            "outline": copy.deepcopy(presentation.outline),
        },
    )
    presentation.status = PresentationStatus.GENERATING_CONTENT
    presentation.confirmed_at = None
    session.add(job)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="簡報仍有進行中的生成任務"
        ) from exc
    await session.refresh(job)
    return GenerationJobRead.model_validate(job)


@app.get(
    "/api/v1/generation-jobs/{job_id}",
    response_model=GenerationJobRead,
    tags=["generation-jobs"],
)
async def get_generation_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> GenerationJobRead:
    job = await session.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="找不到生成任務")
    return GenerationJobRead.model_validate(job)


@app.post(
    "/api/v1/generation-jobs/{job_id}/cancel",
    response_model=GenerationJobRead,
    tags=["generation-jobs"],
)
async def cancel_generation_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> GenerationJobRead:
    job = await session.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="找不到生成任務")
    if job.status in {"COMPLETED", "FAILED", "CANCELED"}:
        return GenerationJobRead.model_validate(job)
    job.cancel_requested = True
    job.stage = "canceling"
    if job.status == "QUEUED":
        job.status = "CANCELED"
        job.stage = "canceled"
        job.finished_at = datetime.now(UTC)
        presentation = await session.get(Presentation, job.presentation_id)
        if presentation is not None:
            presentation.status = PresentationStatus.DRAFT
    await session.commit()
    await session.refresh(job)
    return GenerationJobRead.model_validate(job)


@app.post(
    "/api/v1/generate",
    response_model=GenerationResponse,
    tags=["generation"],
)
async def generate_presentation(payload: GenerationRequest) -> GenerationResponse:
    async with SessionLocal() as session:
        presentation = Presentation(
            title=payload.topic[:180],
            language=payload.language,
            template=payload.template,
            status=PresentationStatus.GENERATING_CONTENT,
            source_text=payload.source_text,
            generation_settings=payload.model_dump(mode="json"),
        )
        session.add(presentation)
        await session.commit()
        await session.refresh(presentation)
        presentation_id = presentation.id

    try:
        deck, provider_type, model = await _generate_deck(payload)
    except DeckGenerationFailure as exc:
        await _mark_generation_failed(presentation_id, exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    async with SessionLocal() as session:
        presentation = await session.get(Presentation, presentation_id)
        if presentation is None:
            raise HTTPException(status_code=404, detail="找不到生成中的簡報")
        content = deck.model_dump(mode="json")
        presentation.title = deck.title
        presentation.language = deck.language
        presentation.template = payload.template
        presentation.status = PresentationStatus.PREVIEW_READY
        presentation.content = content
        presentation.failed_stage = None
        presentation.last_error = None
        session.add(
            PresentationVersion(
                presentation_id=presentation.id,
                revision=presentation.revision,
                title=presentation.title,
                language=presentation.language,
                template=presentation.template,
                content=content,
                change_reason="generated",
            )
        )
        await session.commit()

    return GenerationResponse(
        **deck.model_dump(),
        provider=provider_type,
        model=model,
        presentation_id=presentation_id,
    )


@app.get("/health", response_model=HealthRead, tags=["system"])
async def health() -> HealthRead:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        return HealthRead(status="degraded", database="unavailable")
    return HealthRead(status="ok", database="postgresql")


@app.post(
    "/api/v1/presentations",
    response_model=PresentationRead,
    status_code=status.HTTP_201_CREATED,
    tags=["presentations"],
)
async def create_presentation(
    payload: PresentationCreate,
    session: AsyncSession = Depends(get_session),
) -> PresentationRead:
    presentation = Presentation(**payload.model_dump())
    session.add(presentation)
    await session.commit()
    await session.refresh(presentation)
    return _presentation_read(presentation)


@app.get(
    "/api/v1/presentations",
    response_model=list[PresentationRead],
    tags=["presentations"],
)
async def list_presentations(
    session: AsyncSession = Depends(get_session),
) -> list[PresentationRead]:
    result = await session.scalars(
        select(Presentation).order_by(Presentation.updated_at.desc())
    )
    return [_presentation_read(item) for item in result]


@app.post(
    "/api/v1/presentations/batch-delete",
    response_model=PresentationDeleteResult,
    tags=["presentations"],
)
async def batch_delete_presentations(
    payload: PresentationBatchDelete,
    session: AsyncSession = Depends(get_session),
) -> PresentationDeleteResult:
    result = await session.execute(
        delete(Presentation)
        .where(Presentation.id.in_(set(payload.ids)))
        .returning(Presentation.id)
    )
    deleted_ids = list(result.scalars())
    await session.commit()
    for presentation_id in deleted_ids:
        await asyncio.to_thread(
            remove_presentation_files, settings.presentation_storage_dir, presentation_id
        )
    return PresentationDeleteResult(deleted=len(deleted_ids))


@app.post(
    "/api/v1/presentations/{presentation_id}/render",
    response_model=PresentationRenderRead,
    tags=["presentations"],
)
async def render_presentation_output(
    presentation_id: uuid.UUID,
    file: UploadFile = File(...),
    template: str = Form(default="editorial", max_length=40),
    session: AsyncSession = Depends(get_session),
) -> PresentationRenderRead:
    presentation = await session.get(Presentation, presentation_id)
    if presentation is None:
        raise HTTPException(status_code=404, detail="找不到簡報")
    if not (file.filename or "").lower().endswith(".pptx"):
        raise HTTPException(status_code=422, detail="請上傳 PPTX 檔案")
    presentation.status = PresentationStatus.RENDERING
    presentation.confirmed_at = None
    await session.commit()
    data = await file.read()
    try:
        slide_count, previews = await asyncio.to_thread(
            render_presentation,
            settings.presentation_storage_dir,
            presentation_id,
            data,
        )
    except PresentationRenderError as exc:
        presentation.status = PresentationStatus.FAILED
        presentation.failed_stage = "render"
        presentation.last_error = str(exc)
        await session.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    presentation.status = PresentationStatus.PREVIEW_READY
    presentation.template = template
    presentation.last_rendered_revision = presentation.revision
    presentation.failed_stage = None
    presentation.last_error = None
    await session.commit()
    await session.refresh(presentation)
    version = int(presentation.updated_at.timestamp())
    return PresentationRenderRead(
        presentation_id=presentation_id,
        slide_count=slide_count,
        preview_urls=[
            f"/api/v1/presentations/{presentation_id}/preview/{index}?v={version}"
            for index, _ in enumerate(previews, start=1)
        ],
        pptx_url=f"/api/v1/presentations/{presentation_id}/download/pptx",
        pdf_url=f"/api/v1/presentations/{presentation_id}/download/pdf",
    )


@app.get(
    "/api/v1/presentations/{presentation_id}",
    response_model=PresentationDetailRead,
    tags=["presentations"],
)
async def get_presentation(
    presentation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> PresentationDetailRead:
    presentation = await session.get(Presentation, presentation_id)
    if presentation is None:
        raise HTTPException(status_code=404, detail="Presentation not found")
    preview_urls, pptx_url, pdf_url = _presentation_urls(presentation)
    summary = _presentation_read(presentation)
    return PresentationDetailRead(
        **summary.model_dump(),
        content=presentation.content,
        outline=presentation.outline,
        preview_urls=preview_urls,
        pptx_url=pptx_url,
        pdf_url=pdf_url,
    )


@app.get(
    "/api/v1/presentations/{presentation_id}/versions",
    response_model=list[PresentationVersionRead],
    tags=["presentations"],
)
async def list_presentation_versions(
    presentation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[PresentationVersionRead]:
    if await session.get(Presentation, presentation_id) is None:
        raise HTTPException(status_code=404, detail="找不到簡報")
    versions = await session.scalars(
        select(PresentationVersion)
        .where(PresentationVersion.presentation_id == presentation_id)
        .order_by(PresentationVersion.revision.desc())
    )
    return [
        PresentationVersionRead(
            id=version.id,
            revision=version.revision,
            title=version.title,
            language=version.language,
            template=version.template,
            change_reason=version.change_reason,
            created_at=version.created_at,
            slide_count=len((version.content or {}).get("slides", [])),
        )
        for version in versions
    ]


@app.get(
    "/api/v1/presentations/{presentation_id}/versions/{revision}",
    response_model=PresentationVersionDetailRead,
    tags=["presentations"],
)
async def get_presentation_version(
    presentation_id: uuid.UUID,
    revision: int,
    session: AsyncSession = Depends(get_session),
) -> PresentationVersionDetailRead:
    version = await session.scalar(
        select(PresentationVersion).where(
            PresentationVersion.presentation_id == presentation_id,
            PresentationVersion.revision == revision,
        )
    )
    if version is None:
        raise HTTPException(status_code=404, detail="找不到指定版本")
    content = GeneratedDeck.model_validate(version.content)
    return PresentationVersionDetailRead(
        id=version.id,
        revision=version.revision,
        title=version.title,
        language=version.language,
        template=version.template,
        change_reason=version.change_reason,
        created_at=version.created_at,
        slide_count=len(content.slides),
        content=content,
    )


@app.post(
    "/api/v1/presentations/{presentation_id}/versions/{revision}/restore",
    response_model=PresentationDetailRead,
    tags=["presentations"],
)
async def restore_presentation_version(
    presentation_id: uuid.UUID,
    revision: int,
    session: AsyncSession = Depends(get_session),
) -> PresentationDetailRead:
    presentation = await session.get(Presentation, presentation_id)
    if presentation is None:
        raise HTTPException(status_code=404, detail="找不到簡報")
    version = await session.scalar(
        select(PresentationVersion).where(
            PresentationVersion.presentation_id == presentation_id,
            PresentationVersion.revision == revision,
        )
    )
    if version is None:
        raise HTTPException(status_code=404, detail="找不到指定版本")
    content = GeneratedDeck.model_validate(copy.deepcopy(version.content))
    presentation.revision += 1
    presentation.title = content.title
    presentation.language = content.language
    presentation.template = version.template
    presentation.content = content.model_dump(mode="json")
    presentation.status = PresentationStatus.DRAFT
    presentation.confirmed_at = None
    presentation.failed_stage = None
    presentation.last_error = None
    presentation.failed_stage = None
    presentation.last_error = None
    session.add(
        PresentationVersion(
            presentation_id=presentation.id,
            revision=presentation.revision,
            title=presentation.title,
            language=presentation.language,
            template=presentation.template,
            content=presentation.content,
            change_reason=f"restored_from_{revision}",
        )
    )
    await session.commit()
    await session.refresh(presentation)
    summary = _presentation_read(presentation)
    return PresentationDetailRead(
        **summary.model_dump(),
        content=presentation.content,
        preview_urls=[],
        pptx_url=None,
        pdf_url=None,
    )


@app.post(
    "/api/v1/presentations/{presentation_id}/duplicate",
    response_model=PresentationDetailRead,
    status_code=status.HTTP_201_CREATED,
    tags=["presentations"],
)
async def duplicate_presentation(
    presentation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> PresentationDetailRead:
    source = await session.get(Presentation, presentation_id)
    if source is None:
        raise HTTPException(status_code=404, detail="找不到簡報")
    if source.content is None:
        raise HTTPException(status_code=409, detail="這份簡報還沒有可複製的內容")
    duplicated_deck = _duplicate_deck(source.title, source.content)
    duplicated_title = duplicated_deck.title
    content = duplicated_deck.model_dump(mode="json")
    duplicated = Presentation(
        title=duplicated_title,
        language=source.language,
        template=source.template,
        status=PresentationStatus.DRAFT,
        source_text=source.source_text,
        content=content,
        generation_settings=copy.deepcopy(source.generation_settings),
    )
    session.add(duplicated)
    await session.flush()
    session.add(
        PresentationVersion(
            presentation_id=duplicated.id,
            revision=duplicated.revision,
            title=duplicated.title,
            language=duplicated.language,
            template=duplicated.template,
            content=content,
            change_reason="duplicated",
        )
    )
    await session.commit()
    await session.refresh(duplicated)
    summary = _presentation_read(duplicated)
    return PresentationDetailRead(
        **summary.model_dump(),
        content=content,
        preview_urls=[],
        pptx_url=None,
        pdf_url=None,
    )


@app.post(
    "/api/v1/presentations/{presentation_id}/retry",
    response_model=GenerationJobRead,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["presentations"],
)
async def retry_presentation_generation(
    presentation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> GenerationJobRead:
    presentation = await session.scalar(
        select(Presentation)
        .where(Presentation.id == presentation_id)
        .with_for_update()
    )
    if presentation is None:
        raise HTTPException(status_code=404, detail="找不到簡報")
    if presentation.status != PresentationStatus.FAILED:
        raise HTTPException(status_code=409, detail="只有失敗的生成任務可以重試")
    if presentation.failed_stage == "render" and presentation.content is not None:
        raise HTTPException(
            status_code=409,
            detail="渲染失敗不需要重新呼叫 AI，請使用已儲存內容重新產生預覽",
        )
    if presentation.generation_settings is None:
        raise HTTPException(status_code=409, detail="這份簡報沒有可用的生成設定")
    if await _active_generation_job(session, presentation_id) is not None:
        raise HTTPException(status_code=409, detail="簡報仍有進行中的生成任務")
    request = GenerationRequest.model_validate(presentation.generation_settings)
    if presentation.outline is None:
        job_type = "outline"
        job_payload = {"request": request.model_dump(mode="json")}
    else:
        job_type = "content"
        job_payload = {
            "request": request.model_dump(mode="json"),
            "outline": copy.deepcopy(presentation.outline),
        }
    job = GenerationJob(
        presentation_id=presentation.id,
        job_type=job_type,
        status="QUEUED",
        stage="queued",
        progress=5,
        payload=job_payload,
    )
    presentation.status = PresentationStatus.GENERATING_CONTENT
    presentation.failed_stage = None
    presentation.last_error = None
    presentation.confirmed_at = None
    session.add(job)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="簡報仍有進行中的生成任務"
        ) from exc
    await session.refresh(job)
    return GenerationJobRead.model_validate(job)


@app.patch(
    "/api/v1/presentations/{presentation_id}/content",
    response_model=PresentationDetailRead,
    tags=["presentations"],
)
async def update_presentation_content(
    presentation_id: uuid.UUID,
    payload: PresentationContentUpdate,
    session: AsyncSession = Depends(get_session),
) -> PresentationDetailRead:
    presentation = await session.get(Presentation, presentation_id)
    if presentation is None:
        raise HTTPException(status_code=404, detail="找不到簡報")

    content = {
        "title": payload.title,
        "language": payload.language,
        "slides": [slide.model_dump(mode="json") for slide in payload.slides],
    }
    presentation.title = payload.title
    presentation.language = payload.language
    presentation.content = content
    presentation.revision += 1
    presentation.status = PresentationStatus.DRAFT
    presentation.confirmed_at = None
    session.add(
        PresentationVersion(
            presentation_id=presentation.id,
            revision=presentation.revision,
            title=presentation.title,
            language=presentation.language,
            template=presentation.template,
            content=content,
            change_reason="content_saved",
        )
    )
    await session.commit()
    await session.refresh(presentation)
    summary = _presentation_read(presentation)
    return PresentationDetailRead(
        **summary.model_dump(),
        content=presentation.content,
        preview_urls=[],
        pptx_url=None,
        pdf_url=None,
    )


@app.get(
    "/api/v1/presentations/{presentation_id}/preview/{slide_number}",
    response_class=FileResponse,
    tags=["presentations"],
)
async def get_presentation_preview(
    presentation_id: uuid.UUID,
    slide_number: int,
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    presentation = await session.get(Presentation, presentation_id)
    if presentation is None:
        raise HTTPException(status_code=404, detail="找不到簡報")
    if presentation.last_rendered_revision != presentation.revision:
        raise HTTPException(status_code=409, detail="簡報內容已修改，請先更新預覽")
    _, _, previews = presentation_asset_paths(
        settings.presentation_storage_dir, presentation_id
    )
    if slide_number < 1 or slide_number > len(previews):
        raise HTTPException(status_code=404, detail="找不到預覽頁面")
    return FileResponse(
        previews[slide_number - 1],
        media_type="image/png",
        headers={"Cache-Control": "no-cache"},
    )


@app.get(
    "/api/v1/presentations/{presentation_id}/download/pptx",
    response_class=FileResponse,
    tags=["presentations"],
)
async def download_presentation_pptx(
    presentation_id: uuid.UUID,
    animations: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    presentation = await session.get(Presentation, presentation_id)
    if presentation is None:
        raise HTTPException(status_code=404, detail="找不到簡報")
    _ensure_presentation_downloadable(presentation)
    pptx, _, _ = presentation_asset_paths(settings.presentation_storage_dir, presentation_id)
    if not pptx.exists():
        raise HTTPException(status_code=404, detail="PPTX 尚未完成")
    selected = pptx
    if animations:
        selected = pptx.with_name("presentation-animated.pptx")
        if not selected.exists() or selected.stat().st_mtime < pptx.stat().st_mtime:
            await asyncio.to_thread(add_fade_transitions, pptx, selected)
    return FileResponse(
        selected,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=f"{presentation_id}.pptx",
    )


@app.get(
    "/api/v1/presentations/{presentation_id}/download/pdf",
    response_class=FileResponse,
    tags=["presentations"],
)
async def download_presentation_pdf(
    presentation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    presentation = await session.get(Presentation, presentation_id)
    if presentation is None:
        raise HTTPException(status_code=404, detail="找不到簡報")
    _ensure_presentation_downloadable(presentation)
    _, pdf, _ = presentation_asset_paths(settings.presentation_storage_dir, presentation_id)
    if not pdf.exists():
        raise HTTPException(status_code=404, detail="PDF 尚未完成")
    return FileResponse(pdf, media_type="application/pdf", filename=f"{presentation_id}.pdf")


@app.delete(
    "/api/v1/presentations/{presentation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["presentations"],
)
async def delete_presentation(
    presentation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    presentation = await session.get(Presentation, presentation_id)
    if presentation is None:
        raise HTTPException(status_code=404, detail="找不到簡報")
    await session.delete(presentation)
    await session.commit()
    await asyncio.to_thread(
        remove_presentation_files, settings.presentation_storage_dir, presentation_id
    )


@app.post(
    "/api/v1/presentations/{presentation_id}/confirm",
    response_model=PresentationRead,
    tags=["presentations"],
)
async def confirm_presentation(
    presentation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> PresentationRead:
    presentation = await session.get(Presentation, presentation_id)
    if presentation is None:
        raise HTTPException(status_code=404, detail="Presentation not found")
    if presentation.status not in {
        PresentationStatus.PREVIEW_READY,
        PresentationStatus.COMPLETED,
    }:
        raise HTTPException(
            status_code=409,
            detail="Presentation must be preview-ready before confirmation",
        )
    if presentation.last_rendered_revision != presentation.revision:
        raise HTTPException(status_code=409, detail="簡報內容已修改，請先更新預覽")
    presentation.status = PresentationStatus.COMPLETED
    presentation.confirmed_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(presentation)
    return _presentation_read(presentation)
