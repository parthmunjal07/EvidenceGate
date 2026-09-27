FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY evidencegate ./evidencegate
COPY tools ./tools
RUN python -m pip install --no-cache-dir ".[dga-m1]"

EXPOSE 8080
CMD ["sh", "-c", "uvicorn evidencegate.api.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
