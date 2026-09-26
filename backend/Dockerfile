FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# WeasyPrint uses native rendering libraries. Keep the image usable for the
# specified report engine; this is a simple deployable foundation, not a full
# production hardening profile.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libffi8 libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libgdk-pixbuf-2.0-0 \
    shared-mime-info && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install .

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
