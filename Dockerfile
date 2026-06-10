# Лёгкий образ для chat_reader и podcaster (без TTS и apt-зависимостей)
FROM python:3.12-slim

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

COPY requirements.base.txt .
RUN pip install --no-cache-dir --default-timeout=120 --retries 5 -r requirements.base.txt

COPY . .

RUN useradd -m appuser && chown -R appuser /app
USER appuser
