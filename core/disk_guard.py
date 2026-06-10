import shutil
import time
from pathlib import Path

from core.config import Config
from core.logger import logger


class DiskGuard:
    """Проверка свободного места и очистка временных TTS-файлов."""

    _low_disk_mode = False
    _last_warning_at = 0.0

    @classmethod
    def _disk_usage_path(cls, path: str | None = None) -> str:
        """Путь для shutil.disk_usage — существующий (Windows падает на несуществующих)."""
        target = Path(path or Config.TTS_OUTPUT_DIR or ".")
        check = target if target.is_absolute() else Path.cwd() / target
        while not check.exists():
            parent = check.parent
            if parent == check:
                return str(Path.cwd())
            check = parent
        return str(check)

    @classmethod
    def free_disk_gb(cls, path: str | None = None) -> float:
        try:
            usage = shutil.disk_usage(cls._disk_usage_path(path))
            return usage.free / (1024**3)
        except OSError:
            return 0.0

    @classmethod
    def is_low_disk(cls, path: str | None = None) -> bool:
        free_gb = cls.free_disk_gb(path)
        low = free_gb < Config.MIN_FREE_DISK_GB
        if low and not cls._low_disk_mode:
            cls._low_disk_mode = True
            cls._log_critical(free_gb)
        elif not low:
            cls._low_disk_mode = False
        return low

    @classmethod
    def low_disk_mode(cls) -> bool:
        cls.is_low_disk()
        return cls._low_disk_mode

    @classmethod
    def _log_critical(cls, free_gb: float) -> None:
        now = time.time()
        if now - cls._last_warning_at < 60:
            return
        cls._last_warning_at = now
        logger.critical(
            "Мало свободного места на диске: %.1f GB (минимум %.1f GB). "
            "Временные файлы и монологи отключены.",
            free_gb,
            Config.MIN_FREE_DISK_GB,
        )

    @classmethod
    def cleanup_tts_directory(cls, directory: str | None = None) -> int:
        """Удаляет старые WAV и ограничивает размер каталога."""
        target_dir = Path(directory or Config.TTS_OUTPUT_DIR)
        if not target_dir.is_dir():
            return 0

        now = time.time()
        max_age = Config.TTS_TEMP_MAX_AGE_MINUTES * 60
        max_bytes = Config.TTS_TEMP_MAX_SIZE_MB * 1024 * 1024
        removed = 0

        files = sorted(
            (p for p in target_dir.iterdir() if p.suffix == ".wav"),
            key=lambda p: p.stat().st_mtime,
        )

        total_size = sum(p.stat().st_size for p in files)

        for file_path in files:
            stat = file_path.stat()
            too_old = now - stat.st_mtime > max_age
            over_quota = total_size > max_bytes
            if too_old or over_quota or cls.low_disk_mode():
                try:
                    size = stat.st_size
                    file_path.unlink(missing_ok=True)
                    total_size -= size
                    removed += 1
                except OSError as exc:
                    logger.warning("Не удалось удалить %s: %s", file_path, exc)

        return removed
