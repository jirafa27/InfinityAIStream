"""Точка входа: Twitch chat_reader (локально)."""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("HEALTH_PORT", "8082")

sys.path.insert(0, str(Path(__file__).resolve().parent / "chat"))

from chat_reader_bot import main  # noqa: E402

if __name__ == "__main__":
    asyncio.run(main())
