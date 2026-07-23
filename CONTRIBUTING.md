# Contributing

## Local setup

Requirements:

- Node.js 22.13 or newer
- Python 3.13
- Docker Desktop with Docker Compose
- Ollama for local generation

Copy `.env.example` to `.env`, replace `AI_CONFIG_SECRET`, then start the full stack:

```bash
./scripts/start.sh
```

## Checks

Frontend:

```bash
npm ci
npm run check
```

Backend:

```bash
python -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -e "./backend[dev]"
cd backend
python -m pytest -q
```

Docker:

```bash
docker compose build web api worker
```

## Pull requests

- Keep a pull request focused on one concern.
- Add or update tests for behavior changes.
- Document API and environment changes.
- Never commit `.env`, API keys, generated presentations, database files, or model data.
- UI changes must be checked in light/dark mode and both interface languages.
- Changes to generation jobs must cover success, failure, cancellation, and resource cleanup.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for module boundaries and the staged refactor roadmap.
