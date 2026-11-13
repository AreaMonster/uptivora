# Release process

## Versioning

`MAJOR.MINOR.PATCH`. The version lives in `backend/pyproject.toml` (and `version` in
`backend/app/core/config.py`, `frontend/package.json`). Licences are valid for every future
version, so a release must never require a new licence.

## Checklist

1. **Freeze** — all changes for the release merged to `main`; CI green.
2. **Tests** on a clean checkout:
   ```bash
   cd backend && .venv/Scripts/python -m ruff check . && .venv/Scripts/python -m pytest -q
   cd frontend && npx tsc --noEmit && npm run lint && npm run build
   ```
3. **Migrations** — every new Alembic revision tested on a copy of production data
   (`uptivora-backup verify` restores a dump; run `migrate` against it).
4. **Public keys** — `PRODUCTION_PUBLIC_KEYS` in `backend/app/licensing/keys.py` contains
   every active production key id. A release without them would reject all customer licences.
5. **Version bump** in the three files above, `docs/ROADMAP.md`/release notes updated,
   commit, tag `vX.Y.Z`.
6. **Build** from the tag:
   ```bash
   git checkout vX.Y.Z
   deploy/release/build.sh
   ```
   The script refuses a dirty tree, refuses if a key or secret file is tracked, builds both
   images with `--pull`, checks that the API image contains no development key, dev seed or
   tests, and writes `dist/uptivora-selfhosted-X.Y.Z.tar.gz` plus `SHA256SUMS`.
7. **Smoke test** the bundle on a fresh VM: `install.sh`, `docker compose up -d`, register,
   install a licence issued with the production key, add a monitor, receive a test alert,
   `uptivora-backup now` and `verify`.
8. **Upgrade test** — install the previous release, create data, upgrade to the new bundle
   following `docs/selfhosted/upgrade.md`.
9. **Publish** the bundle and checksum where customers download it (customer area / licence
   email). Release notes state: new features, fixes, required actions, PostgreSQL changes.
10. **Hosted** — deploy the same images to production ([hosted-deployment.md](hosted-deployment.md)).

## Hotfix

Branch from the release tag, fix, bump PATCH, run the full checklist (steps 2–10). Security
fixes are announced to licence holders by email with the affected versions.

## Never in a release

- the licence signing private key, `backend/.dev-keys/`, `tools/licensegen/` in an image
- `.env` files or anything from `secrets/`
- development seed data (`backend/app/devseed.py` is excluded by `.dockerignore`)
