FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir \
    -i https://mirror2.chabokan.net/pypi/simple/ \
    --trusted-host mirror2.chabokan.net \
    -r /app/requirements.txt \
    || pip install --no-cache-dir -r /app/requirements.txt

COPY VERSION /app/VERSION
COPY backend/app /app/app
COPY backend/alembic /app/alembic
COPY backend/alembic.ini /app/alembic.ini

ENV PYTHONPATH=/app
ENV UPLOAD_DIR=/app/storage/uploads

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
