FROM node:24-alpine AS frontend-build
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
COPY tools/generate_release_manifest.mjs tools/build_release.mjs /tools/
ARG EVIDENCEGATE_RELEASE_ID
ARG EVIDENCEGATE_BUILD_SHA
ARG RAILWAY_GIT_COMMIT_SHA
RUN EVIDENCEGATE_BUILD_SHA=${EVIDENCEGATE_BUILD_SHA:-${RAILWAY_GIT_COMMIT_SHA:-unknown}} EVIDENCEGATE_RELEASE_ID=${EVIDENCEGATE_RELEASE_ID} npm run build

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY evidencegate ./evidencegate
COPY --from=frontend-build /evidencegate/api/static ./evidencegate/api/static
COPY tools ./tools
RUN python -m pip install --no-cache-dir ".[dga-m1]"

EXPOSE 8080
CMD ["sh", "-c", "uvicorn evidencegate.api.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
