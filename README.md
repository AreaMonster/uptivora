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
frontend/           Next.js app (Phase 2)
tools/licensegen/   OFFLINE licence signing CLI — never shipped
deploy/             Docker Compose files
docs/               architecture, editions & licensing, schema, roadmap, runbooks
```

## Development quick start (Windows, Git Bash)

```bash
docker compose -f deploy/docker-compose.dev.yml up -d
```

```bash
cd backend && py -3.12 -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
```

```bash
cd backend && cp ../.env.example .env && .venv/Scripts/alembic upgrade head
```

```bash
cd backend && .venv/Scripts/python -m pytest -q
```

Mailpit (captured dev email) runs at http://localhost:8025.

## Documentation

* [Architecture & risks](docs/ARCHITECTURE.md)
* [Editions & licensing](docs/EDITIONS_AND_LICENSING.md)
* [Database schema](docs/DATABASE.md)
* [Roadmap](docs/ROADMAP.md)
* [Licence key operations](docs/LICENSE_KEY_OPERATIONS.md)
