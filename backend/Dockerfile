FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /build/requirements.txt
RUN pip install --no-cache-dir --prefix=/install \
    -i https://mirror2.chabokan.net/pypi/simple/ \
    --trusted-host mirror2.chabokan.net \
    -r /build/requirements.txt \
    || pip install --no-cache-dir --prefix=/install -r /build/requirements.txt

FROM python:3.12-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 aiws \
    && useradd --uid 10001 --gid aiws --home /app --shell /sbin/nologin aiws

COPY --from=builder /install /usr/local
COPY VERSION /app/VERSION
COPY backend/app /app/app
COPY backend/alembic /app/alembic
COPY backend/alembic.ini /app/alembic.ini

RUN mkdir -p /app/storage/uploads && chown -R aiws:aiws /app

ENV PYTHONPATH=/app
ENV UPLOAD_DIR=/app/storage/uploads
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

USER aiws
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
