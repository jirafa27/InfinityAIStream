# Используем официальный образ Python 3.11
FROM python:3.11-slim-bullseye

ENV PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Устанавливаем системные зависимости для sounddevice
RUN apt-get update && apt-get install -y --no-install-recommends \
    libportaudio2 \
    libasound2-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Копируем и устанавливаем Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем приложение
COPY . .

# Добавляем непривилегированного пользователя (для безопасности)
RUN useradd -m appuser && chown -R appuser /app
USER appuser
