"""
Единая точка запуска локального стрима.

Запускает Redis (Docker), Telegram-бот, chat_reader, podcaster, streamer, визуал (OBS Browser Source).

  python run.py

Переменные окружения — те же, что у run_local_supervisor.py (.env).
"""
from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Разумные значения по умолчанию для локального стрима
os.environ.setdefault("LOCAL_SUPERVISOR_AUTO_START", "1")
os.environ.setdefault("LOCAL_SUPERVISOR_MANAGE_DOCKER", "1")
os.environ.setdefault("LOCAL_CHAT_READER", "1")
os.environ.setdefault("LOCAL_PODCASTER", "1")
os.environ.setdefault("LOCAL_TELEGRAM_CONTROL", "1")
os.environ.setdefault("LOCAL_SUPERVISOR_RESET_TOPIC", "1")
os.environ.setdefault("VISUAL_ENABLED", "1")
os.environ.setdefault("VISUAL_MODE", "demo")
os.environ.setdefault("TTS_OUTPUT_MODE", "speaker")
os.environ.setdefault("TTS_OUTPUT_DIR", "output/tts")


async def main() -> None:
    from run_local_supervisor import main as supervisor_main

    await supervisor_main()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Стрим остановлен", file=sys.stderr)
