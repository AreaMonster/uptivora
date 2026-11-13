# Uptivora API + monitoring worker (one image, two commands).
#   docker build -t uptivora/api:0.1.0 backend
# The image contains no signing keys, no dev seed and no test or build tooling.
ARG PYTHON_IMAGE=python:3.12-slim

FROM ${PYTHON_IMAGE} AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /src
COPY pyproject.toml constraints.txt ./
# Install only the runtime dependencies listed in pyproject.toml, pinned by constraints.txt.
RUN python -c "import tomllib; d = tomllib.load(open('pyproject.toml', 'rb')); open('requirements.txt', 'w').write('\n'.join(d['project']['dependencies']))" \
 && python -m venv /opt/venv \
 && /opt/venv/bin/pip install -c constraints.txt -r requirements.txt \
 && (/opt/venv/bin/pip uninstall -y pip setuptools wheel >/dev/null 2>&1 || true)

FROM ${PYTHON_IMAGE} AS runtime
LABEL org.opencontainers.image.title="Uptivora API" \
      org.opencontainers.image.vendor="Uptivora"
RUN groupadd --gid 10001 uptivora \
 && useradd --uid 10001 --gid uptivora --no-create-home --shell /usr/sbin/nologin uptivora
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UPTIVORA_ENV=production
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
# Byte-compile once at build time: the container filesystem is read-only at runtime.
# /data: the licence signer's journal volume (new volumes inherit this ownership).
RUN python -m compileall -q /app/app /app/alembic  && mkdir -p /data && chown 10001:10001 /data
USER 10001:10001
EXPOSE 8000
# uvicorn must not rewrite the client address from X-Forwarded-For: the app does that
# itself and only trusts the proxies listed in UPTIVORA_TRUSTED_PROXIES.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--no-server-header"]
