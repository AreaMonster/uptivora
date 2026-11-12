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

Open http://localhost:3000. The dev seed creates `demo@example.com` (password in
`backend/app/devseed.py`). Captured emails: http://localhost:8025.

Optional background worker (sends queued emails):

```bash
cd backend && .venv/Scripts/python -m app.worker
```

Tests:

```bash
cd backend && .venv/Scripts/python -m pytest -q
```

## Documentation

* [Architecture & risks](docs/ARCHITECTURE.md)
* [Editions & licensing](docs/EDITIONS_AND_LICENSING.md)
* [Database schema](docs/DATABASE.md)
* [Roadmap](docs/ROADMAP.md)
* [Licence key operations](docs/LICENSE_KEY_OPERATIONS.md)
