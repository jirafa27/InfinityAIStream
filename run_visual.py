"""
Визуальный фрактал для стрима: React + WebGL, сервер aiohttp.

Режимы (VISUAL_MODE):
  demo — автономная демонстрация (пробел = имитация речи)
  wav  — синхронизация с WAV из TTS_OUTPUT_DIR (TTS_OUTPUT_MODE=file)

Захват в OBS: Browser Source → VISUAL_URL (по умолчанию http://localhost:8765)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import subprocess
import sys
import webbrowser
from pathlib import Path

from core.config import Config

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent
DIST_DIR = PROJECT_DIR / "visual-web" / "dist"


def ensure_visual_build() -> None:
    if DIST_DIR.is_dir() and (DIST_DIR / "index.html").is_file():
        return

    visual_web = PROJECT_DIR / "visual-web"
    package_json = visual_web / "package.json"
    if not package_json.is_file():
        logger.error("Не найден visual-web/package.json")
        sys.exit(1)

    logger.info("Сборка visual-web (npm install && npm run build)…")
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    try:
        subprocess.run([npm, "install"], cwd=visual_web, check=True)
        subprocess.run([npm, "run", "build"], cwd=visual_web, check=True)
    except FileNotFoundError:
        logger.error(
            "Node.js/npm не найден. Установите Node.js или выполните вручную: "
            "cd visual-web && npm install && npm run build"
        )
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        logger.error("Ошибка сборки visual-web: %s", exc)
        sys.exit(1)


async def _run_server(open_browser: bool) -> None:
    from visual.server import serve_visual

    if open_browser:
        webbrowser.open(Config.VISUAL_URL)

    await serve_visual(Config.VISUAL_HOST, Config.VISUAL_PORT)


def main() -> None:
    parser = argparse.ArgumentParser(description="Infinity fractal visual server")
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Открыть браузер для локального превью",
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Не запускать npm build автоматически",
    )
    args = parser.parse_args()

    if not args.no_build:
        ensure_visual_build()

    logger.info(
        "Запуск визуала: %s, режим=%s, complexity=%s",
        Config.VISUAL_URL,
        Config.VISUAL_MODE,
        Config.VISUAL_COMPLEXITY,
    )
    if Config.VISUAL_MODE == "demo":
        logger.info("Демо: Пробел — речь, T/Y/G — состояния. OBS: Browser Source.")

    try:
        asyncio.run(_run_server(args.open_browser))
    except KeyboardInterrupt:
        logger.info("Визуал остановлен")


if __name__ == "__main__":
    main()
