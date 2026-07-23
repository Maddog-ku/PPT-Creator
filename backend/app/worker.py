from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
import logging
import uuid

from sqlalchemy import select

from .ai import LocalImageProvider, OllamaProvider
from .config import get_settings
from .database import SessionLocal, engine
from .main import DeckGenerationFailure, _generate_deck, _generate_outline, get_ollama_provider
from .models import AIProviderConfig, GenerationJob, Presentation, PresentationStatus, PresentationVersion
from .schemas import GeneratedDeck, GenerationRequest, PresentationOutline


logger = logging.getLogger(__name__)
settings = get_settings()
CONTENT_BATCH_MAX_SLIDES = 10


class JobCanceled(Exception):
    pass


async def _job_cancel_requested(job_id: uuid.UUID) -> bool:
    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        return job is None or job.cancel_requested or job.status == "CANCELED"


async def _run_cancellable(job_id: uuid.UUID, operation):
    task = asyncio.create_task(operation)
    try:
        while True:
            done, _ = await asyncio.wait(
                {task}, timeout=settings.job_cancel_poll_seconds
            )
            if done:
                return task.result()
            if await _job_cancel_requested(job_id):
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                raise JobCanceled
    finally:
        if not task.done():
            task.cancel()


async def _release_local_resources(request: GenerationRequest) -> None:
    config_ids = {
        config_id
        for config_id in (request.provider_id, request.image_provider_id)
        if config_id is not None
    }
    configs: dict[uuid.UUID, AIProviderConfig] = {}
    if config_ids:
        async with SessionLocal() as session:
            configs = {
                config.id: config
                for config in await session.scalars(
                    select(AIProviderConfig).where(AIProviderConfig.id.in_(config_ids))
                )
            }

    ollama_models: set[tuple[str, str]] = set()
    stable_diffusion_endpoints: set[tuple[str, str]] = set()

    if request.provider_id is None:
        ollama_models.add((settings.ollama_base_url, settings.ollama_model))
    else:
        text_config = configs.get(request.provider_id)
        if text_config is not None and text_config.provider == "ollama":
            ollama_models.add((text_config.base_url, text_config.model))

    if request.generate_images:
        if request.image_provider_id is None:
            ollama_models.add(
                (settings.ollama_base_url, settings.ollama_image_model)
            )
        else:
            image_config = configs.get(request.image_provider_id)
            if image_config is not None and image_config.provider == "ollama":
                ollama_models.add(
                    (
                        image_config.base_url,
                        image_config.image_model or image_config.model,
                    )
                )
            elif (
                image_config is not None
                and image_config.provider == "stable_diffusion"
            ):
                stable_diffusion_endpoints.add(
                    (image_config.base_url, image_config.model)
                )

    for base_url, model in ollama_models:
        try:
            provider = OllamaProvider(
                base_url=base_url,
                model=model,
                timeout_seconds=settings.ollama_timeout_seconds,
            )
            await provider.release_model()
        except Exception as exc:
            logger.warning("Unable to release Ollama model %s: %s", model, exc)

    for base_url, model in stable_diffusion_endpoints:
        try:
            provider = LocalImageProvider(
                base_url=base_url,
                model=model,
                timeout_seconds=settings.ollama_timeout_seconds,
            )
            await provider.release_model()
        except Exception as exc:
            logger.warning(
                "Unable to unload Stable Diffusion checkpoint %s: %s",
                model,
                exc,
            )


async def _set_progress(job_id: uuid.UUID, progress: int, stage: str) -> None:
    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None:
            raise JobCanceled
        if job.cancel_requested:
            raise JobCanceled
        job.progress = progress
        job.stage = stage
        await session.commit()


def _request_with_confirmed_outline(
    request: GenerationRequest,
    outline: PresentationOutline,
    *,
    page_offset: int = 0,
    enforce_deck_boundaries: bool = True,
) -> GenerationRequest:
    outline_text = "\n".join(
        f"{page_offset + index + 1}. [{item.kind}] {item.title}：{item.objective}"
        for index, item in enumerate(outline.items)
    )
    batch_instruction = (
        ""
        if enforce_deck_boundaries
        else (
            f"\n這次只生成第 {page_offset + 1} 至 "
            f"{page_offset + len(outline.items)} 頁。"
            "不要補上不在本批大綱中的封面、章節或結尾。"
        )
    )
    return request.model_copy(
        update={
            "topic": (
                f"{request.topic}\n\n以下是使用者已確認的大綱，頁數、順序、標題與頁型都必須遵守：\n"
                f"{outline_text}{batch_instruction}"
            ),
            "slide_count": len(outline.items),
            "enforce_deck_boundaries": enforce_deck_boundaries,
        }
    )


def _apply_confirmed_outline(
    deck: GeneratedDeck, outline: PresentationOutline
) -> GeneratedDeck:
    if len(deck.slides) != len(outline.items):
        raise RuntimeError("生成內容頁數與已確認大綱不一致")
    slides = [
        slide.model_copy(
            update={
                "eyebrow": item.eyebrow,
                "title": item.title,
                "kind": item.kind,
            }
        )
        for slide, item in zip(deck.slides, outline.items, strict=True)
    ]
    return deck.model_copy(
        update={
            "title": outline.title,
            "language": outline.language,
            "slides": slides,
        }
    )


def _partition_outline(
    outline: PresentationOutline,
    max_batch_size: int = CONTENT_BATCH_MAX_SLIDES,
) -> list[tuple[int, PresentationOutline]]:
    if max_batch_size < 3:
        raise ValueError("內容批次至少需要容納 3 頁")
    total = len(outline.items)
    batch_count = max(1, (total + max_batch_size - 1) // max_batch_size)
    base_size, extra = divmod(total, batch_count)
    batches: list[tuple[int, PresentationOutline]] = []
    offset = 0
    for batch_index in range(batch_count):
        size = base_size + (1 if batch_index < extra else 0)
        items = outline.items[offset : offset + size]
        batches.append(
            (
                offset,
                outline.model_copy(update={"items": items}),
            )
        )
        offset += size
    return batches


async def _generate_content_in_batches(
    job_id: uuid.UUID,
    request: GenerationRequest,
    outline: PresentationOutline,
) -> tuple[GeneratedDeck, str, str]:
    batches = _partition_outline(outline)
    slides = []
    provider_type = ""
    model = ""
    remaining_images = request.image_count if request.generate_images else 0

    for batch_index, (offset, batch_outline) in enumerate(batches):
        batch_request = _request_with_confirmed_outline(
            request,
            batch_outline,
            page_offset=offset,
            enforce_deck_boundaries=len(batches) == 1,
        ).model_copy(
            update={
                "generate_images": remaining_images > 0,
                "image_count": max(1, remaining_images),
            }
        )
        batch_progress = 20 + int(68 * batch_index / len(batches))
        await _set_progress(job_id, batch_progress, "generating_content_batch")

        for attempt in range(2):
            try:
                generated, provider_type, model = await _run_cancellable(
                    job_id, _generate_deck(batch_request)
                )
                break
            except DeckGenerationFailure as exc:
                if attempt == 1 or exc.status_code < 500:
                    raise
                logger.warning(
                    "Content batch %s/%s failed; retrying once: %s",
                    batch_index + 1,
                    len(batches),
                    exc.message,
                )
                await _set_progress(
                    job_id, batch_progress, "retrying_content_batch"
                )

        batch_deck = _apply_confirmed_outline(generated, batch_outline)
        slides.extend(batch_deck.slides)
        remaining_images = max(
            0,
            remaining_images
            - sum(1 for slide in batch_deck.slides if slide.image_data),
        )
        await _set_progress(
            job_id,
            20 + int(68 * (batch_index + 1) / len(batches)),
            "generating_content_batch",
        )

    return (
        GeneratedDeck(
            title=outline.title,
            language=outline.language,
            slides=slides,
        ),
        provider_type,
        model,
    )


async def _complete_outline_job(
    job_id: uuid.UUID,
    outline: PresentationOutline,
    provider: str,
    model: str,
) -> None:
    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None or job.cancel_requested:
            raise JobCanceled
        presentation = await session.get(Presentation, job.presentation_id)
        if presentation is None:
            raise RuntimeError("找不到生成中的簡報")
        presentation.title = outline.title
        presentation.language = outline.language
        presentation.outline = outline.model_dump(mode="json")
        presentation.status = PresentationStatus.DRAFT
        presentation.failed_stage = None
        presentation.last_error = None
        job.status = "COMPLETED"
        job.stage = "outline_ready"
        job.progress = 100
        job.result = {"provider": provider, "model": model}
        job.finished_at = datetime.now(UTC)
        await session.commit()


async def _complete_content_job(
    job_id: uuid.UUID,
    deck,
    provider: str,
    model: str,
) -> None:
    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None or job.cancel_requested:
            raise JobCanceled
        presentation = await session.get(Presentation, job.presentation_id)
        if presentation is None:
            raise RuntimeError("找不到生成中的簡報")
        existing_version = await session.scalar(
            select(PresentationVersion).where(
                PresentationVersion.presentation_id == presentation.id,
                PresentationVersion.revision == presentation.revision,
            )
        )
        if existing_version is not None:
            presentation.revision += 1
        content = deck.model_dump(mode="json")
        presentation.title = deck.title
        presentation.language = deck.language
        presentation.content = content
        presentation.status = PresentationStatus.PREVIEW_READY
        presentation.confirmed_at = None
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
                change_reason="generated_from_outline",
            )
        )
        job.status = "COMPLETED"
        job.stage = "content_ready"
        job.progress = 100
        job.result = {"provider": provider, "model": model}
        job.finished_at = datetime.now(UTC)
        await session.commit()


async def _finish_canceled(job_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None:
            return
        job.status = "CANCELED"
        job.stage = "canceled"
        job.finished_at = datetime.now(UTC)
        presentation = await session.get(Presentation, job.presentation_id)
        if presentation is not None:
            presentation.status = PresentationStatus.DRAFT
        await session.commit()


async def _finish_failed(job_id: uuid.UUID, stage: str, message: str) -> None:
    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None:
            return
        job.status = "FAILED"
        job.stage = stage
        job.error = message
        job.finished_at = datetime.now(UTC)
        presentation = await session.get(Presentation, job.presentation_id)
        if presentation is not None:
            presentation.status = PresentationStatus.FAILED
            presentation.failed_stage = stage
            presentation.last_error = message
        await session.commit()


async def _process_job(job_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None:
            return
        payload = job.payload
        job_type = job.job_type
    request = GenerationRequest.model_validate(payload["request"])
    try:
        if job_type == "outline":
            await _set_progress(job_id, 20, "analyzing_sources")
            outline, provider, model = await _run_cancellable(
                job_id, _generate_outline(request)
            )
            await _set_progress(job_id, 90, "saving_outline")
            await _complete_outline_job(job_id, outline, provider, model)
        elif job_type == "content":
            outline = PresentationOutline.model_validate(payload["outline"])
            await _set_progress(job_id, 20, "preparing_content")
            deck, provider, model = await _run_cancellable(
                job_id, _generate_content_in_batches(job_id, request, outline)
            )
            await _set_progress(job_id, 92, "saving_content")
            await _complete_content_job(job_id, deck, provider, model)
        else:
            raise RuntimeError(f"不支援的任務類型：{job_type}")
    except JobCanceled:
        await _finish_canceled(job_id)
    except DeckGenerationFailure as exc:
        await _finish_failed(job_id, exc.stage, exc.message)
    except Exception as exc:
        logger.exception("Generation job %s failed", job_id)
        await _finish_failed(job_id, job_type, str(exc))
    finally:
        await _release_local_resources(request)


async def _claim_job() -> uuid.UUID | None:
    async with SessionLocal() as session:
        async with session.begin():
            job = await session.scalar(
                select(GenerationJob)
                .where(GenerationJob.status == "QUEUED")
                .order_by(GenerationJob.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            if job.cancel_requested:
                job.status = "CANCELED"
                job.stage = "canceled"
                job.finished_at = datetime.now(UTC)
                return None
            job.status = "RUNNING"
            job.stage = "starting"
            job.started_at = datetime.now(UTC)
            job.progress = max(job.progress, 10)
            job_id = job.id
        return job_id


async def _recover_interrupted_jobs() -> None:
    async with SessionLocal() as session:
        jobs = list(
            await session.scalars(
                select(GenerationJob).where(GenerationJob.status == "RUNNING")
            )
        )
        for job in jobs:
            if job.cancel_requested:
                job.status = "CANCELED"
                job.stage = "canceled"
                job.finished_at = datetime.now(UTC)
            else:
                job.status = "QUEUED"
                job.stage = "recovered"
                job.started_at = None
        await session.commit()


async def run_worker() -> None:
    await _recover_interrupted_jobs()
    logger.info("Generation worker started")
    try:
        while True:
            job_id = await _claim_job()
            if job_id is None:
                await asyncio.sleep(settings.job_poll_seconds)
                continue
            await _process_job(job_id)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())
