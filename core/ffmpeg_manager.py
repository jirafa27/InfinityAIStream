import os
import signal
import sys
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows / non-Unix
    fcntl = None

from core.config import Config
from core.logger import logger
from core.metrics import metrics

_LOCK_PATH = Path("/tmp/infinity_stream_ffmpeg.lock")
_PID_PATH = Path("/tmp/infinity_stream_ffmpeg.pid")

_RESTART_WINDOW_SECONDS = 600
_RESTART_MAX_COUNT = 5
_RESTART_COOLDOWN_SECONDS = 900


class FFmpegManager:
    """
    Один экземпляр FFmpeg с PID-lock и защитой от restart loop.
    RTMP пока не подключён — менеджер готов к интеграции.
    """

    def __init__(self) -> None:
        self._process = None
        self._lock_fd: int | None = None
        self._restart_times: list[float] = []
        self._cooldown_until = 0.0

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def in_cooldown(self) -> bool:
        return time.time() < self._cooldown_until

    def _acquire_lock(self) -> bool:
        if fcntl is None:
            if _LOCK_PATH.exists():
                logger.error("FFmpeg lock уже существует")
                return False
            _LOCK_PATH.touch()
            return True
        _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(_LOCK_PATH), os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            logger.error("FFmpeg уже запущен в другом процессе (lock занят)")
            return False
        self._lock_fd = fd
        return True

    def _release_lock(self) -> None:
        if self._lock_fd is not None and fcntl is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                os.close(self._lock_fd)
            except OSError:
                pass
            self._lock_fd = None
        _LOCK_PATH.unlink(missing_ok=True)
        _PID_PATH.unlink(missing_ok=True)

    def _record_restart(self) -> None:
        now = time.time()
        self._restart_times = [
            t for t in self._restart_times if now - t <= _RESTART_WINDOW_SECONDS
        ]
        self._restart_times.append(now)
        metrics.ffmpeg_restarts_total += 1
        if len(self._restart_times) >= _RESTART_MAX_COUNT:
            self._cooldown_until = now + _RESTART_COOLDOWN_SECONDS
            logger.critical(
                "FFmpeg перезапускался %s раз за %s мин — пауза %s мин",
                len(self._restart_times),
                _RESTART_WINDOW_SECONDS // 60,
                _RESTART_COOLDOWN_SECONDS // 60,
            )

    def build_command(self, rtmp_url: str) -> list[str]:
        return [
            "ffmpeg",
            "-re",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{Config.STREAM_WIDTH}x{Config.STREAM_HEIGHT}",
            "-r", str(Config.STREAM_FPS),
            "-i", "pipe:0",
            "-f", "s16le",
            "-ar", "48000",
            "-ac", "2",
            "-i", "pipe:3",
            "-c:v", "libx264",
            "-preset", Config.STREAM_X264_PRESET,
            "-b:v", Config.STREAM_VIDEO_BITRATE,
            "-maxrate", Config.STREAM_VIDEO_BITRATE,
            "-bufsize", "6000k",
            "-g", str(Config.STREAM_FPS * 2),
            "-c:a", "aac",
            "-b:a", Config.STREAM_AUDIO_BITRATE,
            "-reconnect", "1",
            "-reconnect_at_eof", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-f", "flv",
            rtmp_url,
        ]

    def stop(self, timeout: float = 10.0) -> None:
        if self._process is None:
            self._release_lock()
            return
        if self._process.poll() is None:
            self._process.send_signal(signal.SIGTERM)
            try:
                self._process.wait(timeout=timeout)
            except Exception:
                self._process.kill()
        self._process = None
        self._release_lock()

    def status_dict(self) -> dict:
        return {
            "ffmpeg_running": self.running,
            "ffmpeg_cooldown": self.in_cooldown,
            "ffmpeg_restarts_recent": len(self._restart_times),
        }


ffmpeg_manager = FFmpegManager()
