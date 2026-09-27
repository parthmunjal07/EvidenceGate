FROM node:22-alpine AS frontend-build
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
ARG EVIDENCEGATE_BUILD_SHA=unknown
ENV VITE_EVIDENCEGATE_BUILD_SHA=${EVIDENCEGATE_BUILD_SHA}
RUN npm run build

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
ARG EVIDENCEGATE_BUILD_SHA=unknown
ENV EVIDENCEGATE_BUILD_SHA=${EVIDENCEGATE_BUILD_SHA}
WORKDIR /app

COPY pyproject.toml README.md ./
COPY evidencegate ./evidencegate
COPY --from=frontend-build /ui/dist ./evidencegate/api/static
COPY tools ./tools
RUN python -m pip install --no-cache-dir ".[dga-m1]"

EXPOSE 8080
CMD ["sh", "-c", "uvicorn evidencegate.api.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
