# InfinityAIStream — Twitch философ-бот

## Описание

Асинхронный Twitch-бот, который комментирует сообщения в чате как философ, озвучивает их через Silero TTS и периодически говорит монологи, если в чате тишина.

## Запуск (рекомендуется): Docker + локальный TTS

**Docker** — Redis, Twitch-бот, AI:

```powershell
docker compose --profile local-redis --profile app up --build -d
```

**Telegram-бот** — лучше **локально** (Docker часто не видит `api.telegram.org` без VPN/прокси):

```powershell
pip install -r requirements.telegram.txt
python run_telegram_control.py
```

**Локально** — supervisor: Docker (chat + AI) + TTS в колонки:

```powershell
pip install -r requirements.txt
python run_local_supervisor.py
```

Supervisor по флагу в Redis поднимает `infinity_stream-bot`, `infinity_stream-ai`, `infinity_stream-redis` и локальный streamer. TG `/start_stream` только выставляет флаг (или дублирует старт Docker).

Профили в `docker-compose.yml`:

| Профиль | Сервисы |
|---------|---------|
| `local-redis` | Redis (порт 6379 на хост) |
| `app` | chat_reader, podcaster |
| `control` | telegram_control |
| `docker-tts` | streamer в Docker (если TTS не локально) |

## Запуск рядом с CreativeTrace

InfinityAIStream — **отдельный Compose-проект** (`COMPOSE_PROJECT_NAME=infinity_stream`). Он не трогает контейнеры, volumes и сети CreativeTrace.

### Рекомендуемые ресурсы сервера

| Профиль | VPS | Для CreativeTrace + ОС | Для стримера (суммарно) |
|---------|-----|------------------------|-------------------------|
| `normal` | 4 vCPU / 8 GB | ~1–1.5 CPU, ~3 GB RAM | ~4.75 CPU limit*, ~3.5 GB RAM limit* |
| `low` | 2 vCPU / 4 GB | ~0.75 CPU, ~2.5 GB RAM | ~1.25 CPU, ~1.5 GB RAM |

\* Лимиты Docker — верхняя граница; все контейнеры редко потребляют максимум одновременно.

### Лимиты контейнеров (профиль `normal`)

| Сервис | CPU | RAM |
|--------|-----|-----|
| `chat_reader` (stream-bot) | 0.50 | 512 MB |
| `podcaster` (stream-ai) | 0.50 | 512 MB |
| `streamer` (stream-tts) | 1.00 | 1536 MB |
| `redis` (опционально) | 0.25 | 128 MB |

FFmpeg и Chromium в текущей версии **не используются**; настройки и менеджер FFmpeg подготовлены для будущего RTMP.

### Подготовка

```bash
cp .env.example .env
# Заполните Twitch и F5AI/Gemini секреты в .env
```

**Общий Redis CreativeTrace** (рекомендуется):

```env
REDIS_HOST=host.docker.internal   # или IP хоста на Linux
REDIS_PORT=6379
REDIS_DB=1
REDIS_KEY_PREFIX=infinity_stream:
COMPOSE_PROFILES=app
```

**Локальный Redis** (изолированный стенд):

```env
REDIS_HOST=redis
COMPOSE_PROFILES=local-redis,app
```

### Команды запуска и мониторинга

```bash
docker compose --env-file .env up -d
docker compose ps
docker compose logs -f --tail=100
docker stats
curl http://localhost:8080/health
curl http://localhost:8080/metrics
```

Healthcheck внутри каждого контейнера: `GET /health` (без вызова Gemini).

### Смена профиля ресурсов

1. В `.env` установите `RESOURCE_PROFILE=low` или `normal`.
2. Для профиля `low` раскомментируйте блок лимитов Docker в `.env.example` / `.env` (см. `STREAM_*_CPUS`, `STREAM_*_MEM_LIMIT`).
3. Перезапустите только стример:

```bash
docker compose --env-file .env up -d
```

### Признаки нехватки ресурсов

- `docker stats` — контейнеры упираются в CPU/RAM limit.
- `GET /health` возвращает `"status": "degraded"`.
- В логах: `Мало свободного места на диске`, `TTS timeout`, `F5AI API вернул 429`.
- OOM kill в `dmesg` / `docker compose logs`.

### Безопасная остановка только стримера

```bash
cd /path/to/InfinityAIStream
docker compose --env-file .env stop
docker compose --env-file .env down
```

Не используйте `docker system prune`, `docker volume prune` и `docker compose down` в каталоге CreativeTrace.

Graceful shutdown (30 с): прекращение приёма событий → завершение AI/TTS → очистка WAV → закрытие Redis.

## Другие режимы

Только Redis:

```powershell
docker compose --profile local-redis up redis -d
```

TTS в Docker (без локального streamer):

```powershell
docker compose --profile local-redis --profile docker-tts up -d
```

Всё локально (кроме Redis):

```powershell
docker compose --profile local-redis up redis -d
pip install -r requirements.txt
python run.py
```

## Переменные окружения

Полный список — в `.env.example`. Основные группы:

| Группа | Примеры |
|--------|---------|
| Ресурсы | `RESOURCE_PROFILE`, `STREAM_*_CPUS`, `STREAM_*_MEM_LIMIT` |
| Redis | `REDIS_HOST`, `REDIS_KEY_PREFIX` |
| AI | `AI_MAX_CONCURRENCY`, `AI_QUEUE_MAX_SIZE` |
| TTS | `TTS_QUEUE_MAX_SIZE`, `TTS_TEMP_MAX_SIZE_MB` |
| Чат | `CHAT_RESPONSE_COOLDOWN_SECONDS`, `MONOLOGUE_MIN_INTERVAL_SECONDS` |
| Диск | `MIN_FREE_DISK_GB`, `LOG_LEVEL` |

## TTS

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `TTS_OUTPUT_MODE` | `speaker` | `file` — WAV, `speaker` — колонки |
| `TTS_OUTPUT_DIR` | `output/tts` | Каталог WAV |
| `TTS_SPEAKER` | `eugene` | Голос Silero |
| `TTS_SAMPLE_RATE` | `48000` | Частота дискретизации |
