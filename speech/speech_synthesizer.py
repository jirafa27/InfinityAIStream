import asyncio
import math
import os
import wave
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import torch

from core.config import Config
from core.disk_guard import DiskGuard
from core.logger import logger
from core.metrics import metrics

from core.text_split import split_sentences
from speech.audio_player import apply_edge_fade, play_audio, stop_audio


def split_text_for_tts(
    text: str,
    *,
    max_chunk: int | None = None,
    max_parts: int | None = None,
) -> list[str]:
    """Делит длинный текст на 2–3 части по границам предложений (лимит Silero ~1000)."""
    text = (text or "").strip()
    if not text:
        return []

    chunk_limit = max_chunk or Config.TTS_CHUNK_MAX_LENGTH
    parts_limit = max_parts or Config.TTS_MAX_CHUNKS

    if len(text) <= chunk_limit:
        return [text]

    n_parts = min(parts_limit, max(2, math.ceil(len(text) / chunk_limit)))
    target_size = math.ceil(len(text) / n_parts)
    sentences = split_sentences(text)

    chunks: list[str] = []
    buffer: list[str] = []
    buffer_len = 0

    def flush() -> None:
        nonlocal buffer, buffer_len
        if buffer:
            chunks.append(" ".join(buffer))
            buffer = []
            buffer_len = 0

    for sentence in sentences:
        if len(sentence) > chunk_limit:
            flush()
            chunks.extend(_hard_split_text(sentence, chunk_limit))
            continue

        extra = len(sentence) + (1 if buffer else 0)
        if buffer and buffer_len + extra > chunk_limit:
            flush()

        if (
            buffer
            and buffer_len >= target_size
            and len(chunks) < n_parts - 1
        ):
            flush()

        buffer.append(sentence)
        buffer_len += extra

    flush()

    chunks = _merge_chunks(chunks, parts_limit, chunk_limit)
    chunks = _enforce_chunk_limit(chunks, chunk_limit)

    logger.info(
        "Текст %s символов разбит на %s частей для TTS",
        len(text),
        len(chunks),
    )
    return chunks


def _hard_split_text(text: str, max_len: int) -> list[str]:
    parts: list[str] = []
    rest = text.strip()
    while rest:
        if len(rest) <= max_len:
            parts.append(rest)
            break
        cut = rest.rfind(" ", 0, max_len + 1)
        if cut <= 0:
            cut = max_len
        parts.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    return parts


def _merge_chunks(chunks: list[str], max_parts: int, chunk_limit: int) -> list[str]:
    merged = list(chunks)
    while len(merged) > max_parts:
        best_idx = min(
            range(len(merged) - 1),
            key=lambda i: len(merged[i]) + len(merged[i + 1]),
        )
        combined = f"{merged[best_idx]} {merged[best_idx + 1]}"
        if len(combined) > chunk_limit:
            break
        merged = (
            merged[:best_idx] + [combined] + merged[best_idx + 2 :]
        )
    return merged


def _enforce_chunk_limit(chunks: list[str], chunk_limit: int) -> list[str]:
    result: list[str] = []
    for chunk in chunks:
        if len(chunk) <= chunk_limit:
            result.append(chunk)
        else:
            result.extend(_hard_split_text(chunk, chunk_limit))
    return result


class SpeechSynthesizer:
    """Класс для синтеза речи с использованием Silero TTS."""

    _instance = None
    _executor = ThreadPoolExecutor(max_workers=Config.TTS_MAX_CONCURRENCY)

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SpeechSynthesizer, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        language: str = "ru",
        speaker: str | None = None,
        sample_rate: int | None = None,
    ):
        speaker = speaker or Config.TTS_SPEAKER
        sample_rate = sample_rate or Config.TTS_SAMPLE_RATE

        if self._initialized:
            if (
                hasattr(self, "speaker")
                and self.speaker != speaker
                and hasattr(self, "available_speakers")
                and speaker in self.available_speakers
            ):
                logger.info(f"Меняем голос с {self.speaker} на {speaker}")
                self.speaker = speaker
            return

        try:
            logger.info("Инициализация Silero SpeechSynthesizer...")
            self.device = "cpu"
            self.language = language
            self.speaker = speaker
            self.sample_rate = sample_rate
            self._file_sequence = 0

            logger.info(f"Используется устройство: {self.device}")
            logger.info(f"Загрузка модели Silero TTS для языка {language}...")

            os.environ.setdefault("TQDM_DISABLE", "1")

            try:
                self.model, self.example_text = torch.hub.load(
                    repo_or_dir="snakers4/silero-models",
                    model="silero_tts",
                    language=self.language,
                    speaker="v3_1_ru",
                    force_reload=False,
                    trust_repo=True,
                    verbose=False,
                    progress=False,
                )
            except Exception as e:
                logger.warning(
                    f"Не удалось загрузить модель из онлайн-репозитория: {e}"
                )
                local_path = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)), "models", "silero_tts"
                )
                if os.path.exists(local_path):
                    logger.info(
                        f"Пробуем загрузить модель из локального каталога: {local_path}"
                    )
                    self.model, self.example_text = torch.hub.load(
                        repo_or_dir=local_path,
                        model="silero_tts",
                        language=self.language,
                        speaker="v3_1_ru",
                        source="local",
                        verbose=False,
                        progress=False,
                    )
                else:
                    raise Exception(f"Локальная копия модели не найдена в {local_path}")

            self.model.to(self.device)
            self.available_speakers = self.model.speakers
            logger.info(f"Доступные голоса: {self.available_speakers}")

            if self.speaker not in self.available_speakers:
                logger.warning(
                    f"Выбранный голос {self.speaker} недоступен. "
                    f"Используется первый доступный голос: {self.available_speakers[0]}"
                )
                self.speaker = self.available_speakers[0]

            logger.info(
                f"Модель Silero TTS успешно загружена, используется голос: {self.speaker}"
            )
            self._initialized = True
        except Exception as e:
            logger.error(f"Ошибка при инициализации Silero TTS: {e}")
            raise

    def _truncate_text(self, text: str) -> str:
        max_length = Config.TTS_MAX_TEXT_LENGTH
        if max_length <= 0:
            return text
        if len(text) > max_length:
            logger.warning(
                f"Текст слишком длинный ({len(text)} символов). "
                f"Обрезаем до {max_length} символов."
            )
            return text[:max_length]
        return text

    def _synthesize_audio(self, text: str) -> np.ndarray:
        text = self._truncate_text(text)
        audio = self.model.apply_tts(
            text=text, speaker=self.speaker, sample_rate=self.sample_rate
        )
        if self.device == "cuda":
            samples = audio.cpu().numpy()
        else:
            samples = audio.numpy()
        return apply_edge_fade(samples, self.sample_rate)

    def _concat_audio(self, parts: list[np.ndarray]) -> np.ndarray:
        if not parts:
            return np.array([], dtype=np.float32)
        if len(parts) == 1:
            return parts[0]
        pause = np.zeros(
            int(self.sample_rate * Config.TTS_CHUNK_PAUSE_SECONDS),
            dtype=np.float32,
        )
        segments: list[np.ndarray] = []
        for index, audio in enumerate(parts):
            segments.append(audio)
            if index < len(parts) - 1:
                segments.append(pause)
        return np.concatenate(segments)

    def _next_output_path(self) -> str:
        self._file_sequence += 1
        filename = f"{self._file_sequence:08d}.wav"
        return os.path.join(Config.TTS_OUTPUT_DIR, filename)

    def _write_wav_atomic(self, file_path: str, audio_array: np.ndarray) -> None:
        if DiskGuard.low_disk_mode():
            raise OSError("Недостаточно места на диске для TTS-файла")
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        part_path = f"{file_path}.part"
        audio_int16 = (audio_array * 32767).astype(np.int16)
        with wave.open(part_path, "w") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(audio_int16.tobytes())
        os.replace(part_path, file_path)

    def _log_synthesis(self, text: str, chunks: list[str]) -> None:
        if len(chunks) == 1:
            logger.info("Синтезируем: %s", text)
            return
        for index, chunk in enumerate(chunks, start=1):
            logger.info("Синтезируем часть %s/%s: %s", index, len(chunks), chunk)

    def synthesize_to_file(self, text: str) -> str | None:
        """Синтезирует текст и сохраняет WAV. Возвращает путь к файлу."""
        try:
            chunks = split_text_for_tts(text)
            if not chunks:
                return None
            self._log_synthesis(text, chunks)
            audio_array = self._concat_audio(
                [self._synthesize_audio(chunk) for chunk in chunks]
            )
            file_path = self._next_output_path()
            self._write_wav_atomic(file_path, audio_array)
            metrics.tts_replicas_total += 1
            logger.info(f"Аудио сохранено: {file_path}")
            return file_path
        except Exception as e:
            metrics.tts_errors_total += 1
            logger.error(f"Ошибка при синтезе в файл: {e}")
            return None

    def synthesize_and_play(self, text: str) -> bool:
        """Синтезирует и воспроизводит на колонках (локальный режим)."""
        try:
            chunks = split_text_for_tts(text)
            if not chunks:
                return False
            self._log_synthesis(text, chunks)
            audio_array = self._concat_audio(
                [self._synthesize_audio(chunk) for chunk in chunks]
            )
            play_audio(audio_array, self.sample_rate)
            metrics.tts_replicas_total += 1
            logger.info("Воспроизведение завершено")
            return True
        except Exception as e:
            metrics.tts_errors_total += 1
            logger.error(f"Ошибка при синтезе или воспроизведении: {e}")
            return False

    def stop_playback(self) -> None:
        """Прерывает текущее воспроизведение (приоритет чата)."""
        stop_audio()

    def _synthesis_timeout(self, text: str) -> float:
        chunks = split_text_for_tts(text)
        return Config.TTS_TIMEOUT_SECONDS * max(1, len(chunks))

    async def synthesize_to_file_async(self, text: str) -> str | None:
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(self._executor, self.synthesize_to_file, text),
            timeout=self._synthesis_timeout(text),
        )

    async def synthesize_and_play_async(self, text: str) -> bool:
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(self._executor, self.synthesize_and_play, text),
            timeout=self._synthesis_timeout(text),
        )
