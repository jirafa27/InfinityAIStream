from redis_client.stream_control_store import StreamControlStore
from stream_control.docker_compose_runner import DockerContainerRunner


class StreamControlService:
    """Оркестрация стрима: Docker (redis, bot, ai) + флаг для локального TTS/player."""

    def __init__(
        self,
        control_store: StreamControlStore,
        compose_runner: DockerContainerRunner,
    ) -> None:
        self._control = control_store
        self._compose = compose_runner

    async def start_stream(self) -> str:
        await self._compose.stop_docker_bot_if_local_chat()
        await self._compose.stop_docker_podcaster_if_local()
        ok, detail = await self._compose.start_backend()

        await self._control.set_running(True)

        from obs.obs_stream_service import ObsStreamService

        obs_note = await ObsStreamService().start_broadcast()

        docker_parts = ["redis"]
        local_parts = ["streamer"]
        if not self._compose.local_chat_reader:
            docker_parts.append("chat_reader")
        else:
            local_parts.append("chat_reader")
        if not self._compose.local_podcaster:
            docker_parts.append("podcaster")
        else:
            local_parts.append("podcaster")
        layout = (
            f"• Docker: {', '.join(docker_parts)}\n"
            f"• Локально: `python run_local_supervisor.py` "
            f"({', '.join(local_parts)})"
        )
        lines = [f"Стрим запущен.\n{layout}"]
        if not ok:
            lines.append(f"Docker (частично):\n{detail}")
        else:
            lines.append(detail)
        if obs_note:
            lines.append(obs_note)
        return "\n".join(lines)

    async def stop_stream(self) -> str:
        from obs.obs_stream_service import ObsStreamService

        obs_note = await ObsStreamService().stop_broadcast()
        await self._control.set_running(False)
        ok, detail = await self._compose.stop_backend()

        lines = [
            "Стрим остановлен.",
            "• Локальный supervisor остановит streamer и player",
        ]
        if not ok:
            lines.append(f"Docker:\n{detail}")
        else:
            lines.append(detail)
        if obs_note:
            lines.append(obs_note)
        return "\n".join(lines)

    async def status(self) -> str:
        running = await self._control.is_running()
        ps = await self._compose.ps()
        state = "включён" if running else "выключен"
        return f"Стрим: {state}\n\n{ps or '(docker compose ps пуст)'}"
