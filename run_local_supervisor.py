"""
Локальный supervisor: Docker (redis, podcaster) + streamer/player + опционально chat_reader.
Следит за флагом infinity_stream:control:stream_running в Redis.
"""
import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

from core.config import Config
from core.utils import is_tcp_port_in_use
from redis_client.redis_manager import RedisManager
from redis_client.stream_control_store import StreamControlStore
from core.worker_epoch import bump_stream_epoch
from redis_client.stream_reset import reset_stream_on_start
from stream_control.docker_compose_runner import DockerContainerRunner

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent
POLL_INTERVAL = float(os.getenv("LOCAL_SUPERVISOR_POLL_INTERVAL", "2.0"))
REDIS_RETRY_SECONDS = float(os.getenv("LOCAL_SUPERVISOR_REDIS_RETRY_SECONDS", "30"))
MANAGE_DOCKER = os.getenv("LOCAL_SUPERVISOR_MANAGE_DOCKER", "1") == "1"
LOCAL_CHAT_READER = os.getenv("LOCAL_CHAT_READER", "1") == "1"
LOCAL_PODCASTER = os.getenv("LOCAL_PODCASTER", "1") == "1"
LOCAL_TELEGRAM_CONTROL = os.getenv("LOCAL_TELEGRAM_CONTROL", "0") == "1"
VISUAL_ENABLED = os.getenv("VISUAL_ENABLED", "0") == "1"
LOCAL_SUPERVISOR_AUTO_START = os.getenv("LOCAL_SUPERVISOR_AUTO_START", "0") == "1"
LOCAL_HEALTH_PORT_STREAMER = int(os.getenv("LOCAL_HEALTH_PORT_STREAMER", "8080"))
LOCAL_HEALTH_PORT_PODCASTER = int(os.getenv("LOCAL_HEALTH_PORT_PODCASTER", "8081"))
LOCAL_HEALTH_PORT_CHAT_READER = int(os.getenv("LOCAL_HEALTH_PORT_CHAT_READER", "8082"))


async def _connect_redis() -> tuple[RedisManager, StreamControlStore]:
    """Подключается к Redis с повторными попытками (ждёт Docker)."""
    host = os.getenv("LOCAL_REDIS_HOST", os.getenv("REDIS_HOST", "localhost"))
    port = os.getenv("REDIS_PORT", "6379")
    os.environ["REDIS_HOST"] = host

    deadline = asyncio.get_event_loop().time() + REDIS_RETRY_SECONDS
    last_error: Exception | None = None

    while asyncio.get_event_loop().time() < deadline:
        manager = RedisManager()
        try:
            await manager.connect()
            await manager.redis_client.ping()
            store = StreamControlStore(manager.redis_client)
            logger.info("Redis доступен: %s:%s", host, port)
            return manager, store
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Redis %s:%s недоступен (%s). Повтор через 2 с… "
                "Поднимите: docker compose --profile local-redis up -d redis",
                host,
                port,
                exc,
            )
            await asyncio.sleep(2)

    raise ConnectionError(
        f"Не удалось подключиться к Redis {host}:{port} за {REDIS_RETRY_SECONDS:.0f} с"
    ) from last_error


class LocalProcessGroup:
    def __init__(
        self,
        *,
        local_chat_reader: bool,
        local_podcaster: bool,
        local_telegram: bool,
    ) -> None:
        self._local_chat_reader = local_chat_reader
        self._local_podcaster = local_podcaster
        self._local_telegram = local_telegram
        self._telegram_skip_logged = False
        self._visual_port_external = False
        self._chat_reader_port_external = False
        self._streamer: subprocess.Popen | None = None
        self._player: subprocess.Popen | None = None
        self._chat_reader: subprocess.Popen | None = None
        self._podcaster: subprocess.Popen | None = None
        self._visual: subprocess.Popen | None = None
        self._telegram: subprocess.Popen | None = None

    @staticmethod
    def _telegram_configured() -> bool:
        return bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip()) and bool(
            os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").strip()
        )

    def ensure_telegram(self) -> None:
        if not self._local_telegram:
            return
        if not self._telegram_configured():
            if not self._telegram_skip_logged:
                logger.warning(
                    "Telegram-бот не запущен: задайте TELEGRAM_BOT_TOKEN и "
                    "TELEGRAM_ALLOWED_USER_IDS в .env"
                )
                self._telegram_skip_logged = True
            return
        if self._telegram is not None and self._telegram.poll() is None:
            return
        logger.info("Запуск run_telegram_control.py (Telegram-бот)")
        self._telegram = subprocess.Popen(
            [sys.executable, "run_telegram_control.py"],
            cwd=PROJECT_DIR,
            env=self._local_env(),
        )

    @staticmethod
    def _local_env(*, health_port: int | None = None) -> dict[str, str]:
        env = os.environ.copy()
        env["REDIS_HOST"] = os.getenv("LOCAL_REDIS_HOST", "localhost")
        if health_port is not None:
            env["HEALTH_PORT"] = str(health_port)
        return env

    def _tts_env(self) -> dict[str, str]:
        env = self._local_env(health_port=LOCAL_HEALTH_PORT_STREAMER)
        env.setdefault("TTS_OUTPUT_MODE", "speaker")
        env.setdefault("TTS_OUTPUT_DIR", "output/tts")
        return env

    def start(self) -> None:
        if self._local_chat_reader and (
            self._chat_reader is None or self._chat_reader.poll() is not None
        ):
            health_host = os.getenv("HEALTH_HOST", "0.0.0.0")
            if is_tcp_port_in_use(health_host, LOCAL_HEALTH_PORT_CHAT_READER):
                if not self._chat_reader_port_external:
                    logger.info(
                        "Порт %s занят — chat_reader уже работает, не перезапускаю",
                        LOCAL_HEALTH_PORT_CHAT_READER,
                    )
                    self._chat_reader_port_external = True
            else:
                self._chat_reader_port_external = False
                logger.info("Запуск run_chat_reader.py (локальный Twitch bot)")
                self._chat_reader = subprocess.Popen(
                    [sys.executable, "run_chat_reader.py"],
                    cwd=PROJECT_DIR,
                    env=self._local_env(health_port=LOCAL_HEALTH_PORT_CHAT_READER),
                )

        if self._local_podcaster and (
            self._podcaster is None or self._podcaster.poll() is not None
        ):
            logger.info("Запуск podcast_generator_run.py (локальная генерация)")
            self._podcaster = subprocess.Popen(
                [sys.executable, "podcast_generator_run.py"],
                cwd=PROJECT_DIR,
                env=self._local_env(health_port=LOCAL_HEALTH_PORT_PODCASTER),
            )

        env = self._tts_env()
        file_mode = env.get("TTS_OUTPUT_MODE", "speaker") == "file"

        if self._streamer is None or self._streamer.poll() is not None:
            mode = "file → player" if file_mode else "speaker (сразу в колонки)"
            logger.info("Запуск run_streamer.py (%s)", mode)
            self._streamer = subprocess.Popen(
                [sys.executable, "run_streamer.py"],
                cwd=PROJECT_DIR,
                env=env,
            )
        visual_plays_audio = (
            VISUAL_ENABLED and os.getenv("VISUAL_MODE", "demo") == "wav"
            and os.getenv("VISUAL_PLAY_AUDIO", "1") == "1"
        )
        if (
            file_mode
            and not visual_plays_audio
            and (self._player is None or self._player.poll() is not None)
        ):
            logger.info("Запуск run_player.py")
            self._player = subprocess.Popen(
                [sys.executable, "run_player.py"],
                cwd=PROJECT_DIR,
                env=env,
            )
        elif visual_plays_audio and self._player is not None and self._player.poll() is None:
            logger.info("VISUAL_PLAY_AUDIO=1 — player не нужен, останавливаю")
            self._stop_proc("player", self._player)
            self._player = None
        elif not file_mode and self._player is not None and self._player.poll() is None:
            logger.info("TTS_OUTPUT_MODE=speaker — player не нужен, останавливаю")
            self._stop_proc("player", self._player)
            self._player = None

        if VISUAL_ENABLED and (self._visual is None or self._visual.poll() is not None):
            visual_host = os.getenv("VISUAL_HOST", "127.0.0.1")
            visual_port = int(os.getenv("VISUAL_PORT", "8765"))
            if is_tcp_port_in_use(visual_host, visual_port):
                if not self._visual_port_external:
                    logger.info(
                        "Порт %s:%s занят — visual уже работает, не перезапускаю",
                        visual_host,
                        visual_port,
                    )
                    self._visual_port_external = True
            else:
                self._visual_port_external = False
                logger.info(
                    "Запуск run_visual.py (жидкость React → OBS Browser Source: %s)",
                    os.getenv("VISUAL_URL", "http://127.0.0.1:8765"),
                )
                self._visual = subprocess.Popen(
                    [sys.executable, "run_visual.py"],
                    cwd=PROJECT_DIR,
                    env=self._local_env(),
                )
        elif not VISUAL_ENABLED and self._visual is not None and self._visual.poll() is None:
            self._stop_proc("visual", self._visual)
            self._visual = None

    @staticmethod
    def _stop_proc(name: str, proc: subprocess.Popen) -> None:
        logger.info("Останавливаю %s (pid %s)", name, proc.pid)
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()

    def stop_stream(self) -> None:
        procs = (
            ("chat_reader", self._chat_reader),
            ("podcaster", self._podcaster),
            ("streamer", self._streamer),
            ("player", self._player),
            ("visual", self._visual),
        )
        for name, proc in procs:
            if proc is None or proc.poll() is not None:
                continue
            self._stop_proc(name, proc)
        self._chat_reader = None
        self._podcaster = None
        self._streamer = None
        self._player = None
        self._visual = None
        self._visual_port_external = False
        self._chat_reader_port_external = False

    def stop(self) -> None:
        self.stop_stream()
        if self._telegram is not None and self._telegram.poll() is None:
            self._stop_proc("telegram", self._telegram)
        self._telegram = None


async def _start_docker(docker: DockerContainerRunner) -> None:
    await docker.stop_docker_bot_if_local_chat()
    await docker.stop_docker_podcaster_if_local()
    await docker.stop_docker_telegram_if_local()
    ok, detail = await docker.start_backend()
    if ok:
        logger.info("Docker backend:\n%s", detail)
    else:
        missing: list[str] = []
        if not docker.local_chat_reader:
            missing.append("chat_reader")
        if not docker.local_podcaster:
            missing.append("podcaster")
        logger.error(
            "Не удалось поднять Docker (%s):\n%s\n"
            "Создайте контейнеры: docker compose --profile local-redis "
            "--profile app up -d --build",
            ", ".join(missing) or "backend",
            detail,
        )
        if not docker.local_chat_reader and "chat_reader" in missing:
            logger.warning(
                "Twitch-чат: Docker-бот недоступен — будет использован "
                "локальный run_chat_reader.py (LOCAL_CHAT_READER=1)."
            )


async def _stop_docker(docker: DockerContainerRunner) -> None:
    ok, detail = await docker.stop_backend()
    if ok:
        logger.info("Docker backend остановлен:\n%s", detail)
    else:
        logger.warning("Ошибка остановки Docker:\n%s", detail)


async def _start_stream(
    docker: DockerContainerRunner | None,
    processes: LocalProcessGroup,
    redis_manager: RedisManager,
) -> None:
    await bump_stream_epoch(redis_manager)
    processes.stop_stream()
    await reset_stream_on_start(redis_manager)
    if docker is not None:
        await _start_docker(docker)
    processes.start()


async def _stop_stream(
    docker: DockerContainerRunner | None,
    processes: LocalProcessGroup,
) -> None:
    if Config.OBS_ENABLED and Config.OBS_AUTO_STOP_STREAM:
        try:
            from obs.obs_stream_service import ObsStreamService

            note = await ObsStreamService().stop_broadcast()
            if note:
                logger.info(note)
        except Exception as exc:
            logger.warning("OBS StopStream при остановке supervisor: %s", exc)
    processes.stop_stream()
    if docker is not None:
        await _stop_docker(docker)


async def main() -> None:
    os.environ.setdefault("TTS_OUTPUT_MODE", "speaker")
    os.environ.setdefault("TTS_OUTPUT_DIR", "output/tts")

    redis_manager, control = await _connect_redis()
    processes = LocalProcessGroup(
        local_chat_reader=LOCAL_CHAT_READER,
        local_podcaster=LOCAL_PODCASTER,
        local_telegram=LOCAL_TELEGRAM_CONTROL,
    )
    docker: DockerContainerRunner | None = None
    if MANAGE_DOCKER:
        try:
            docker = DockerContainerRunner(
                local_chat_reader=LOCAL_CHAT_READER,
                local_podcaster=LOCAL_PODCASTER,
            )
            docker_parts: list[str] = ["redis"]
            local_parts: list[str] = ["streamer"]
            if LOCAL_TELEGRAM_CONTROL:
                local_parts.append("telegram")
            if not LOCAL_CHAT_READER:
                docker_parts.append("chat_reader")
            else:
                local_parts.append("chat_reader")
            if not LOCAL_PODCASTER:
                docker_parts.append("podcaster")
            else:
                local_parts.append("podcaster")
            logger.info(
                "Docker: %s; локально: %s",
                ", ".join(docker_parts),
                ", ".join(local_parts),
            )
        except Exception as exc:
            logger.error(
                "Docker недоступен (%s). Установите Docker Desktop и "
                "выполните: pip install docker",
                exc,
            )
    else:
        logger.info("Docker: LOCAL_SUPERVISOR_MANAGE_DOCKER=0 — только локальные процессы")

    logger.info(
        "Supervisor: poll %.1fs",
        POLL_INTERVAL,
    )

    was_running = False
    if LOCAL_SUPERVISOR_AUTO_START:
        await control.set_running(True)
        logger.info("LOCAL_SUPERVISOR_AUTO_START=1 — пайплайн включён")
        await _start_stream(docker, processes, redis_manager)
        was_running = True
        if Config.OBS_ENABLED and Config.OBS_AUTO_START_STREAM:
            try:
                from obs.obs_stream_service import ObsStreamService

                note = await ObsStreamService().start_broadcast()
                if note:
                    logger.info(note)
            except Exception as exc:
                logger.warning("OBS StartStream при автостарте supervisor: %s", exc)

    try:
        while True:
            processes.ensure_telegram()
            running = await control.is_running()
            if running and not was_running:
                await _start_stream(docker, processes, redis_manager)
            elif not running and was_running:
                await _stop_stream(docker, processes)
            elif running:
                processes.start()
            was_running = running
            await asyncio.sleep(POLL_INTERVAL)
    except asyncio.CancelledError:
        pass
    finally:
        if was_running:
            await _stop_stream(docker, processes)
        processes.stop()
        await redis_manager.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Supervisor остановлен")
