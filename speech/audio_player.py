import logging
import os
import threading
import time
import wave

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

FADE_MS = 35.0


def apply_edge_fade(
    audio: np.ndarray,
    sample_rate: int,
    fade_ms: float = FADE_MS,
) -> np.ndarray:
    """Сглаживает начало/конец сигнала, чтобы убрать щелчки на стыках."""
    if audio.size == 0:
        return audio

    samples = int(sample_rate * fade_ms / 1000.0)
    if samples <= 0:
        return audio

    n = min(samples, audio.size // 2)
    if n <= 0:
        return audio

    out = np.asarray(audio, dtype=np.float32).copy()
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    out[:n] *= ramp
    out[-n:] *= ramp[::-1]
    return out


class _PersistentPlayer:
    """Один OutputStream на процесс — без щелчков при смене предложений."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stream: sd.OutputStream | None = None
        self._sample_rate: int | None = None
        self._stop_requested = False

    def _close_stream(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass
        self._stream = None
        self._sample_rate = None

    def _ensure_stream(self, sample_rate: int) -> None:
        if self._stream is not None and self._sample_rate == sample_rate:
            return
        self._close_stream()
        self._stream = sd.OutputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
        )
        self._stream.start()
        self._sample_rate = sample_rate

    def stop(self) -> None:
        """Прерывает текущий клип, поток остаётся открытым — без щелчка на стыке."""
        self._stop_requested = True

    def play(self, audio: np.ndarray, sample_rate: int) -> None:
        faded = apply_edge_fade(np.asarray(audio, dtype=np.float32), sample_rate)
        if faded.size == 0:
            return

        self._stop_requested = False
        chunk_samples = max(1, int(sample_rate * 0.1))
        pos = 0
        while pos < faded.size:
            if self._stop_requested:
                return
            chunk = faded[pos : pos + chunk_samples]
            with self._lock:
                if self._stop_requested:
                    return
                self._ensure_stream(sample_rate)
                assert self._stream is not None
                self._stream.write(chunk)
            pos += chunk_samples


_player = _PersistentPlayer()


def play_audio(audio: np.ndarray, sample_rate: int) -> None:
    _player.play(audio, sample_rate)


def stop_audio() -> None:
    """Принудительная остановка (прерывание очереди)."""
    _player.stop()


def get_next_wav(directory: str) -> str | None:
    """Возвращает путь к самому старому готовому WAV (по имени файла)."""
    if not os.path.isdir(directory):
        return None

    wav_files = sorted(
        f for f in os.listdir(directory) if f.endswith(".wav") and not f.endswith(".part")
    )
    if not wav_files:
        return None
    return os.path.join(directory, wav_files[0])


def play_wav(file_path: str) -> None:
    with wave.open(file_path, "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32767.0

    play_audio(audio, sample_rate)


def run_playback_loop(directory: str, poll_interval: float = 0.05) -> None:
    """Последовательно воспроизводит WAV из каталога и удаляет после проигрывания."""
    os.makedirs(directory, exist_ok=True)
    logger.info(f"Ожидание WAV в {os.path.abspath(directory)}")

    while True:
        file_path = get_next_wav(directory)
        if file_path is None:
            time.sleep(poll_interval)
            continue

        try:
            logger.info(f"Воспроизведение: {file_path}")
            play_wav(file_path)
            os.remove(file_path)
            logger.info(f"Удалён: {file_path}")
        except Exception as e:
            logger.error(f"Ошибка воспроизведения {file_path}: {e}")
            time.sleep(poll_interval)
