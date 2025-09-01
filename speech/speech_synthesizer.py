import os
from core.logger import logger
import torch
import numpy as np
import sounddevice as sd

class SpeechSynthesizer:
    """Класс для синтеза речи с использованием Silero TTS."""
    
    # Статическая переменная для хранения экземпляра (Singleton)
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        """Реализует паттерн Singleton для повторного использования модели."""
        if cls._instance is None:
            cls._instance = super(SpeechSynthesizer, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(
        self,
        language: str = "ru",
        speaker: str = "baya",  # Доступные голоса: 'aidar', 'baya', 'kseniya', 'xenia', 'eugene'
        sample_rate: int = 8000  # Частота дискретизации, можно установить 8000, 24000 или 48000
    ):
        # Инициализируем только один раз (часть паттерна Singleton)
        if self._initialized:
            # Проверяем, нужно ли обновить параметры
            if (hasattr(self, 'speaker') and self.speaker != speaker and
                hasattr(self, 'available_speakers') and speaker in self.available_speakers):
                logger.info(f"Меняем голос с {self.speaker} на {speaker}")
                self.speaker = speaker
            return
            
        try:
            logger.info("Инициализация Silero SpeechSynthesizer...")
            
            # Определяем устройство (GPU/CPU)
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.language = language
            self.speaker = speaker
            self.sample_rate = sample_rate
            
            logger.info(f"Используется устройство: {self.device}")
            
            # Загружаем модель Silero TTS
            logger.info(f"Загрузка модели Silero TTS для языка {language}...")
            
            # Определяем репозиторий в зависимости от наличия подключения к интернету
            try:
                # Пробуем загрузить модель из онлайн-репозитория или кэша
                repo_or_dir = 'snakers4/silero-models'
                self.model, self.example_text = torch.hub.load(
                    repo_or_dir=repo_or_dir,
                    model='silero_tts',
                    language=self.language,
                    speaker='v3_1_ru',  # Версия модели
                    force_reload=False  # Используем кэш, если он есть
                )
            except Exception as e:
                logger.warning(f"Не удалось загрузить модель из онлайн-репозитория: {e}")
                # Если не удалось, загружаем из локальной копии, если она существует
                local_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "silero_tts")
                if os.path.exists(local_path):
                    logger.info(f"Пробуем загрузить модель из локального каталога: {local_path}")
                    self.model, self.example_text = torch.hub.load(
                        repo_or_dir=local_path,
                        model='silero_tts',
                        language=self.language,
                        speaker='v3_1_ru',
                        source='local'
                    )
                else:
                    raise Exception(f"Локальная копия модели не найдена в {local_path}")
            
            # Перемещаем модель на нужное устройство
            self.model.to(self.device)
            
            # Получаем список доступных голосов
            self.available_speakers = self.model.speakers
            
            logger.info(f"Доступные голоса: {self.available_speakers}")
            
            # Проверяем, доступен ли выбранный голос
            if self.speaker not in self.available_speakers:
                logger.warning(f"Выбранный голос {self.speaker} недоступен. Используется первый доступный голос: {self.available_speakers[0]}")
                self.speaker = self.available_speakers[0]
            
            logger.info(f"Модель Silero TTS успешно загружена, используется голос: {self.speaker}")
            
            self._initialized = True
        except Exception as e:
            logger.error(f"Ошибка при инициализации Silero TTS: {e}")
            raise
        

    def synthesize_and_play(self, text: str):
        """Синтезирует и воспроизводит текст с помощью Silero TTS."""
        try:
            logger.info(f"Синтезируем: {text}")
            
            # Ограничение по длине текста (рекомендуется для лучшего качества)
            max_length = 1000
            if len(text) > max_length:
                logger.warning(f"Текст слишком длинный ({len(text)} символов). Обрезаем до {max_length} символов.")
                text = text[:max_length]
            
            # Генерация аудио с помощью Silero
            audio = self.model.apply_tts(
                    text=text,
                speaker=self.speaker,
                sample_rate=self.sample_rate
            )
            
            # Преобразуем тензор в numpy массив для воспроизведения
            if self.device == "cuda":
                audio_array = audio.cpu().numpy()
            else:
                audio_array = audio.numpy()
            
            # Воспроизводим аудио
            sd.play(audio_array, self.sample_rate)
            sd.wait()
            logger.info("Воспроизведение завершено")
            return True
        except Exception as e:
            logger.error(f"Ошибка при синтезе или воспроизведении: {e}")
            return False
    
    def save_to_file(self, text: str, file_path: str):
        """Синтезирует текст и сохраняет его в WAV файл."""
        try:
            logger.info(f"Синтезируем текст в файл: {file_path}")
            
            # Генерация аудио
            audio = self.model.apply_tts(
                text=text,
                speaker=self.speaker,
                sample_rate=self.sample_rate
            )
            
            # Преобразуем тензор в numpy массив
            if self.device == "cuda":
                audio_array = audio.cpu().numpy()
            else:
                audio_array = audio.numpy()
                
            # Создаем директорию для файла, если она не существует
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
            
            # Сохраняем в WAV файл
            try:
                import scipy.io.wavfile as wavfile
                wavfile.write(file_path, self.sample_rate, (audio_array * 32767).astype(np.int16))
                logger.info(f"Аудио успешно сохранено в файл: {file_path}")
                return True
            except ImportError:
                logger.warning("Библиотека scipy не установлена, сохраняем через torchaudio")
                try:
                    import torchaudio
                    torchaudio.save(file_path, audio.unsqueeze(0), self.sample_rate)
                    logger.info(f"Аудио успешно сохранено в файл: {file_path}")
                    return True
                except ImportError:
                    logger.error("Не найдена ни scipy, ни torchaudio для сохранения аудио")
                    return False
        except Exception as e:
            logger.error(f"Ошибка при сохранении аудио в файл: {e}")
            return False

# Пример использования
if __name__ == "__main__":
    synthesizer = SpeechSynthesizer()
    synthesizer.synthesize_and_play("Привет! Это тестовое сообщение для проверки синтеза речи.")