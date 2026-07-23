# Architecture

PPT Creator is a local-first presentation generation system. The browser manages the authoring workflow, FastAPI owns durable application state, and a separate worker executes expensive AI jobs.

## Runtime flow

```text
Browser (Next.js/vinext)
  ├─ create and edit presentations
  ├─ poll generation jobs
  └─ build editable PPTX content
          │
          ▼
FastAPI ─────────────── PostgreSQL
  ├─ presentation CRUD
  ├─ provider settings
  ├─ source extraction
  └─ render orchestration
          │
          ▼
Background worker ───── Ollama / cloud providers / Stable Diffusion
  ├─ outline generation
  ├─ batched slide generation
  ├─ cancellation
  └─ local model resource release
```

## Source boundaries

### Frontend

- `app/page.tsx`: application state and view orchestration. New domain logic must not be added here.
- `app/types.ts`: shared API and UI contracts.
- `app/provider-options.ts`: provider discovery and provider-specific UI metadata.
- `app/default-slides.ts`: deterministic starter deck content.
- `app/preferences.ts`: persisted interface preferences and translations.
- `app/generation-timing.ts`: pure time-formatting helpers.
- `app/presentation-builder.ts`: editable PPTX construction.
- `app/templates.ts`: presentation theme catalog.
- `app/globals.css`: global tokens and current component styles.

### Backend

- `backend/app/main.py`: FastAPI routes and dependency wiring.
- `backend/app/worker.py`: job claiming, cancellation, progress, batching, and cleanup.
- `backend/app/ai/`: provider adapters. Provider-specific HTTP details stay in this package.
- `backend/app/models.py`: SQLAlchemy persistence models.
- `backend/app/schemas.py`: public API contracts.
- `backend/app/rendering.py`: LibreOffice/PDF rendering.
- `backend/app/source_parser.py`: uploaded source extraction.
- `backend/alembic/`: ordered database migrations.

## Dependency rules

1. UI components may depend on pure helpers and types; pure helpers must not import UI components.
2. Provider adapters must not open database sessions.
3. Routes may coordinate services but must not contain provider-specific HTTP payloads.
4. Worker terminal paths—success, failure, and cancellation—must release local model resources.
5. API response changes require matching TypeScript contracts and tests.
6. Database schema changes require an Alembic migration.
7. Generated files, credentials, local databases, and model data must never enter Git.

## Refactor roadmap

The current behavior is stable, so remaining decomposition should happen through small pull requests:

1. Move each major view from `app/page.tsx` into `app/components/views/`.
2. Introduce a typed frontend API client under `app/services/`.
3. Move FastAPI route groups into `backend/app/routers/`.
4. Move presentation and generation orchestration into `backend/app/services/`.
5. Split `globals.css` by tokens, application shell, views, and slide rendering.

Each extraction must preserve API contracts and pass the full CI suite before the next module is moved.
