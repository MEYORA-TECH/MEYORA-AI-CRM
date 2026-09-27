# Meyora API. Runs anywhere that runs containers (Azure Container Apps, Render, Fly, Cloud Run, a VPS).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # The embedding model is baked into the image here, so a new container never downloads it.
    EMBEDDING_CACHE_DIR=/app/models

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Pre-download the embedding model (~90 MB) at build time.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/app/models').embed(['ok'])"

COPY . .

RUN useradd --create-home --uid 10001 app && chown -R app /app/models
USER app

EXPOSE 8000
# Migrations are not run here: the app's database role can't change tables (by design).
# Run them with the owner role (scripts/setup_database.py), or set MIGRATE_ON_START=true
# together with ALEMBIC_DATABASE_URL=<owner connection URL>.
CMD ["sh", "-c", "if [ \"$MIGRATE_ON_START\" = \"true\" ]; then alembic upgrade head; fi && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*' --timeout-graceful-shutdown 20"]
