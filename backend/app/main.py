from contextlib import asynccontextmanager
from datetime import UTC, datetime
import logging
import uuid

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .ai import AIProvider, AIProviderError, OllamaProvider, OllamaProviderError, RemoteAIProvider
from .database import Base, SessionLocal, engine, get_session
from .models import AIProviderConfig, Presentation, PresentationStatus
from .security import decrypt_api_key, encrypt_api_key
from .schemas import (
    AIProviderConfigCreate,
    AIProviderConfigRead,
    AIProviderConfigUpdate,
    AIProviderConnectionRead,
    AIProviderRead,
    GenerationRequest,
    GenerationResponse,
    HealthRead,
    OllamaConnectionRead,
    OllamaModelRead,
    PresentationCreate,
    PresentationRead,
)


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
            await connection.run_sync(Base.metadata.create_all)
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


@app.get(
    "/api/v1/ai-provider",
    response_model=AIProviderRead,
    tags=["ai-providers"],
)
async def get_ai_provider() -> AIProviderRead:
    return AIProviderRead(provider="ollama", model=settings.ollama_model)


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
    "/api/v1/generate",
    response_model=GenerationResponse,
    tags=["generation"],
)
async def generate_presentation(payload: GenerationRequest) -> GenerationResponse:
    provider: AIProvider = get_ollama_provider()
    provider_type = "ollama"
    if payload.provider_id is not None:
        async with SessionLocal() as session:
            config = await session.get(AIProviderConfig, payload.provider_id)
        if config is None:
            raise HTTPException(status_code=404, detail="找不到選擇的 AI Provider")
        try:
            provider = build_ai_provider(
                provider_type=config.provider,
                base_url=config.base_url,
                model=config.model,
                api_key=decrypt_api_key(config.encrypted_api_key),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        provider_type = config.provider
    try:
        deck = await provider.generate_deck(payload)
    except AIProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return GenerationResponse(
        **deck.model_dump(),
        provider=provider_type,
        model=provider.model,
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
) -> Presentation:
    presentation = Presentation(**payload.model_dump())
    session.add(presentation)
    await session.commit()
    await session.refresh(presentation)
    return presentation


@app.get(
    "/api/v1/presentations",
    response_model=list[PresentationRead],
    tags=["presentations"],
)
async def list_presentations(
    session: AsyncSession = Depends(get_session),
) -> list[Presentation]:
    result = await session.scalars(
        select(Presentation).order_by(Presentation.updated_at.desc())
    )
    return list(result)


@app.get(
    "/api/v1/presentations/{presentation_id}",
    response_model=PresentationRead,
    tags=["presentations"],
)
async def get_presentation(
    presentation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Presentation:
    presentation = await session.get(Presentation, presentation_id)
    if presentation is None:
        raise HTTPException(status_code=404, detail="Presentation not found")
    return presentation


@app.post(
    "/api/v1/presentations/{presentation_id}/confirm",
    response_model=PresentationRead,
    tags=["presentations"],
)
async def confirm_presentation(
    presentation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Presentation:
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
    presentation.status = PresentationStatus.COMPLETED
    presentation.confirmed_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(presentation)
    return presentation
