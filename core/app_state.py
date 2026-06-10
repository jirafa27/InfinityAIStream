import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class AppState:
    """Общее состояние процесса для health/metrics и graceful shutdown."""

    role: str = "unknown"
    started_at: float = field(default_factory=time.time)
    twitch_connected: bool = False
    ffmpeg_running: bool = False
    shutting_down: bool = False
    accept_new_events: bool = True
    monologues_enabled: bool = True
    last_heartbeat: float = field(default_factory=time.time)
    ai_queue_size: int = 0
    tts_queue_size: int = 0
    _shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)

    def touch_heartbeat(self) -> None:
        self.last_heartbeat = time.time()

    def request_shutdown(self) -> None:
        self.shutting_down = True
        self.accept_new_events = False
        self.monologues_enabled = False
        self._shutdown_event.set()

    async def wait_shutdown(self) -> None:
        await self._shutdown_event.wait()

    def uptime_seconds(self) -> int:
        return int(time.time() - self.started_at)


app_state = AppState()
