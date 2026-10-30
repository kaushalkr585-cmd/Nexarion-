# syntax=docker/dockerfile:1
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package.json ./
RUN npm install --no-audit --prefer-offline || npm install

COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime

LABEL maintainer="NEXARION Core Team <team@nexarion.dev>"
LABEL description="NEXARION Multi-Agent AI Code Review Platform"
LABEL version="1.0.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000 \
    APP_NAME=nexarion \
    LOG_LEVEL=INFO

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

COPY pyproject.toml README.md ./
RUN pip install --upgrade pip && \
    pip install .

COPY src/ ./src/
COPY scripts/ ./scripts/

RUN pip install -e .

COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE ${PORT}

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD sh -c "uvicorn code_review.web.app:app --host 0.0.0.0 --port ${PORT}"
