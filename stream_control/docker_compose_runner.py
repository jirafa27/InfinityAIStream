import asyncio
import os

import docker
from docker.errors import NotFound


class DockerContainerRunner:
    """Старт/стоп контейнеров backend (redis, chat_reader, podcaster)."""

    def __init__(
        self,
        *,
        local_chat_reader: bool | None = None,
        local_podcaster: bool | None = None,
    ) -> None:
        self._client = docker.from_env()
        project = os.getenv("COMPOSE_PROJECT_NAME", "infinity_stream")
        if local_chat_reader is None:
            local_chat_reader = os.getenv("LOCAL_CHAT_READER", "0") == "1"
        if local_podcaster is None:
            local_podcaster = os.getenv("LOCAL_PODCASTER", "0") == "1"
        self._local_chat_reader = local_chat_reader
        self._local_podcaster = local_podcaster
        names = [f"{project}-redis"]
        if not self._local_chat_reader:
            names.append(f"{project}-bot")
        if not self._local_podcaster:
            names.append(f"{project}-ai")
        self._containers = tuple(names)

    @property
    def local_chat_reader(self) -> bool:
        return self._local_chat_reader

    @property
    def local_podcaster(self) -> bool:
        return self._local_podcaster

    async def _container_action(self, action: str) -> tuple[bool, str]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._run_action, action)

    def _run_action(self, action: str) -> tuple[bool, str]:
        lines: list[str] = []
        ok = True
        for name in self._containers:
            try:
                container = self._client.containers.get(name)
            except NotFound:
                ok = False
                lines.append(
                    f"{name}: не найден — выполните на хосте:\n"
                    "docker compose --profile local-redis --profile app "
                    "--profile control up -d --build"
                )
                continue
            try:
                if action == "start":
                    if container.status != "running":
                        container.start()
                        lines.append(f"{name}: started")
                    else:
                        lines.append(f"{name}: already running")
                else:
                    if container.status == "running":
                        container.stop(timeout=30)
                        lines.append(f"{name}: stopped")
                    else:
                        lines.append(f"{name}: already stopped")
            except docker.errors.DockerException as exc:
                ok = False
                lines.append(f"{name}: {exc}")
        return ok, "\n".join(lines)

    async def start_backend(self) -> tuple[bool, str]:
        return await self._container_action("start")

    async def stop_backend(self) -> tuple[bool, str]:
        # redis оставляем — нужен TG-боту и локальному streamer
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._stop_app_only)

    def _stop_app_only(self) -> tuple[bool, str]:
        lines: list[str] = []
        ok = True
        stop_names = self._containers[1:]
        for name in stop_names:
            try:
                container = self._client.containers.get(name)
                if container.status == "running":
                    container.stop(timeout=30)
                    lines.append(f"{name}: stopped")
                else:
                    lines.append(f"{name}: already stopped")
            except NotFound:
                ok = False
                lines.append(f"{name}: не найден")
            except docker.errors.DockerException as exc:
                ok = False
                lines.append(f"{name}: {exc}")
        return ok, "\n".join(lines) or "OK"

    async def stop_docker_bot_if_local_chat(self) -> None:
        """Останавливает Docker-бота, если chat_reader запускается локально."""
        if not self._local_chat_reader:
            return
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._stop_container, "bot")

    async def stop_docker_podcaster_if_local(self) -> None:
        """Останавливает Docker-podcaster, если генерация запускается локально."""
        if not self._local_podcaster:
            return
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._stop_container, "ai")

    async def stop_docker_telegram_if_local(self) -> None:
        """Останавливает Docker Telegram-бота, если control запускается локально."""
        if os.getenv("LOCAL_TELEGRAM_CONTROL", "0") != "1":
            return
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._stop_container, "tg")

    def _stop_container(self, suffix: str) -> None:
        project = os.getenv("COMPOSE_PROJECT_NAME", "infinity_stream")
        name = f"{project}-{suffix}"
        try:
            container = self._client.containers.get(name)
            if container.status == "running":
                container.stop(timeout=15)
        except NotFound:
            pass

    async def ps(self) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._format_ps)

    def _format_ps(self) -> str:
        lines: list[str] = []
        for name in self._containers:
            try:
                c = self._client.containers.get(name)
                lines.append(f"{name}: {c.status}")
            except NotFound:
                lines.append(f"{name}: not created")
        return "\n".join(lines)
