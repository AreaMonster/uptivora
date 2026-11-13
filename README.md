# Uptivora

Website uptime and SSL monitoring, sold two ways:

* **Hosted** — monthly subscriptions on our infrastructure.
* **Self-hosted** — one-time lifetime licence; runs entirely on the customer's server, offline-verified.

No paid APIs, no runtime AI, no telemetry. Open-source stack: FastAPI · PostgreSQL ·
Next.js · Tailwind · Docker.

## Repository layout

```
backend/            FastAPI API + monitoring worker (Python 3.12)
  app/core/         config, DB, security primitives, SSRF guard
  app/models/       SQLAlchemy models (one schema for both editions)
  app/licensing/    licence format + offline verification (public keys only)
  alembic/          database migrations
  tests/            pytest suite (uses a real PostgreSQL)
frontend/           Next.js 16 web app (marketing site, auth, dashboard)
tools/licensegen/   OFFLINE licence signing CLI — never shipped
deploy/             Docker Compose files
docs/               architecture, editions & licensing, schema, roadmap, runbooks
```

## Development quick start (Windows, Git Bash)

Services (PostgreSQL on port 5433, Mailpit on 1025/8025):

```bash
docker compose -f deploy/docker-compose.dev.yml up -d
```

Backend (Python 3.12):

```bash
cd backend && py -3.12 -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
```

```bash
cd backend && cp ../.env.example .env && .venv/Scripts/alembic upgrade head && .venv/Scripts/python -m app.devseed
```

```bash
backend/.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --port 8000
```

Frontend (Node 20+), proxies `/api/*` to port 8000:

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:3000. The dev seed creates `demo@example.com` and the administrator `admin@example.com`
(passwords in `backend/app/devseed.py`; admin area at `/admin`).
The frontend npm scripts run Next.js with telemetry disabled (`frontend/scripts/next.mjs`). Captured emails: http://localhost:8025.

Monitoring worker (runs the checks, sends emails, housekeeping):

```bash
cd backend && .venv/Scripts/python -m app.worker
```

Tests:

```bash
cd backend && .venv/Scripts/python -m pytest -q
```

### Trying the self-hosted edition locally

Run a second instance with its own database (127.0.0.1 keeps its cookies apart from localhost):

```bash
docker exec uptivora-dev-db-1 createdb -U uptivora uptivora_selfhosted
```

```bash
cd backend && export UPTIVORA_ENV=development UPTIVORA_EDITION=selfhosted UPTIVORA_BILLING_PROVIDER=disabled UPTIVORA_DATABASE_URL=postgresql+asyncpg://uptivora:uptivora@localhost:5433/uptivora_selfhosted UPTIVORA_PUBLIC_URL=http://127.0.0.1:3001 && .venv/Scripts/alembic upgrade head && .venv/Scripts/python -m uvicorn app.main:app --port 8001
```

Start a worker with the same variables (`python -m app.worker`), then the web app:

```bash
cd frontend && UPTIVORA_API_INTERNAL_URL=http://localhost:8001 npm run build && UPTIVORA_EDITION=selfhosted npm run start -- -p 3001 -H 127.0.0.1
```

Open http://127.0.0.1:3001 — the first account becomes the administrator. Test licences:
`python -m licensegen issue --key ../../backend/.dev-keys/dev-private.pem --key-id dev ...`
in `tools/licensegen`.

## Documentation

* [Architecture & risks](docs/ARCHITECTURE.md)
* [Editions & licensing](docs/EDITIONS_AND_LICENSING.md)
* [Database schema](docs/DATABASE.md)
* [Roadmap](docs/ROADMAP.md)
* [Licence key operations](docs/LICENSE_KEY_OPERATIONS.md)
