# Production image for the WhollyMath FastAPI backend on AWS ECS Fargate
# (ARM64/Graviton). The target platform is chosen by the builder
# (`docker buildx build --platform linux/arm64 ...`), so we do NOT hardcode
# --platform here — the same Dockerfile builds for amd64 locally too.
FROM python:3.12-slim

# Fail fast on errors and stream logs straight to CloudWatch (no buffering).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# uv: the project's dependency manager. Pinned for reproducible builds.
RUN pip install --no-cache-dir uv==0.11.7

WORKDIR /app

# Put the project venv that `uv sync` creates on PATH so `alembic` and
# `uvicorn` resolve without `uv run`.
ENV PATH="/app/.venv/bin:$PATH"

# --- Dependency layer (cached unless the lockfile or manifest changes) ---
# Copy only the manifests first, then install third-party deps WITHOUT the
# project itself. This layer is reused across code-only changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# --- Project layer ---
# Copy the application source (includes app/helpneed/artifacts/helpneed_v1.joblib,
# which is loaded at boot), the Alembic migrations, and alembic.ini. Then install
# the project (`app` package) into the venv.
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini ./alembic.ini
RUN uv sync --frozen --no-dev

# Entrypoint: assembles DATABASE_URL, runs `alembic upgrade head`, then uvicorn.
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Run as a non-root user (security best practice). The created user owns /app so
# the venv and source are readable/executable at runtime.
RUN groupadd --system --gid 1000 appuser \
    && useradd --system --uid 1000 --gid 1000 --no-create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
