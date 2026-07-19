from contextlib import asynccontextmanager
from datetime import UTC, datetime
import uuid

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .database import Base, engine, get_session
from .models import Presentation, PresentationStatus
from .schemas import HealthRead, PresentationCreate, PresentationRead


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
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


@app.get("/health", response_model=HealthRead, tags=["system"])
async def health(session: AsyncSession = Depends(get_session)) -> HealthRead:
    await session.execute(text("SELECT 1"))
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
