import time
from dataclasses import dataclass, field

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


@dataclass
class AppMetrics:
    """In-process счётчики для /metrics."""

    started_at: float = field(default_factory=time.time)
    ai_requests_total: int = 0
    ai_errors_total: int = 0
    tts_replicas_total: int = 0
    tts_errors_total: int = 0
    ffmpeg_restarts_total: int = 0
    chat_events_total: int = 0
    chat_dropped_total: int = 0

    def uptime_seconds(self) -> int:
        return int(time.time() - self.started_at)

    def process_cpu_percent(self) -> float:
        if psutil is None:
            return 0.0
        return psutil.Process().cpu_percent(interval=0.0)

    def process_memory_mb(self) -> float:
        if psutil is None:
            return 0.0
        return psutil.Process().memory_info().rss / (1024 * 1024)

    def as_dict(self, extra: dict | None = None) -> dict:
        data = {
            "uptime_seconds": self.uptime_seconds(),
            "process_cpu_percent": round(self.process_cpu_percent(), 2),
            "process_memory_mb": round(self.process_memory_mb(), 2),
            "ai_requests_total": self.ai_requests_total,
            "ai_errors_total": self.ai_errors_total,
            "tts_replicas_total": self.tts_replicas_total,
            "tts_errors_total": self.tts_errors_total,
            "ffmpeg_restarts_total": self.ffmpeg_restarts_total,
            "chat_events_total": self.chat_events_total,
            "chat_dropped_total": self.chat_dropped_total,
        }
        if extra:
            data.update(extra)
        return data


metrics = AppMetrics()
