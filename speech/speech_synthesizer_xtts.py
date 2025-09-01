import os
from core.logger import logger
import torch
import numpy as np
import sounddevice as sd
from TTS.api import TTS

class SpeechSynthesizer:
    """Класс для синтеза речи с использованием TTS."""
    
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
        model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2",  # Используем XTTS_v2 с поддержкой русского
        speaker: str = "Ana Florence",  # Стандартный голос для моделей
        language: str = "ru",
        speaker_wav: str = None,  # Опциональный путь к файлу с образцом голоса
    ):
        # Инициализируем только один раз (часть паттерна Singleton)
        if self._initialized:
            return
            
        try:
            logger.info("Инициализация SpeechSynthesizer...")
            # Определяем устройство (GPU/CPU)
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.language = language
            
            # Устанавливаем переменные окружения для автоматического согласия с лицензией
            os.environ["COQUI_TOS_AGREED"] = "1"
            
            logger.info(f"Используется устройство: {self.device}")
            
            # Используем специализированную русскую модель tacotron2
            logger.info(f"Используется модель {model_name} со специализацией для русского языка")
            
            # Создаем TTS объект с выбранной моделью
            logger.info(f"Создание объекта TTS с моделью {model_name}...")
            self.tts = TTS(model_name=model_name, progress_bar=False, gpu=(self.device == "cuda"))
            logger.info("Объект TTS успешно создан")
            
            self._initialized = True
        except Exception as e:
            logger.error(f"Ошибка при инициализации SpeechSynthesizer: {e}")
            raise
        
        # Настройка голоса и файла с образцом
        self.speaker = speaker
        
        # Проверяем наличие файла с образцом голоса
        self.speaker_wav = None
        if speaker_wav and os.path.exists(speaker_wav):
            self.speaker_wav = speaker_wav
            logger.info(f"Найден файл с образцом голоса: {self.speaker_wav}")
        
        if self.speaker_wav:
            logger.info(f"Будет использоваться клонирование голоса из файла (медленнее, но индивидуальнее)")
        else:
            logger.info(f"Используется встроенный голос: {self.speaker}")

    def synthesize_and_play(self, text: str):
        """Синтезирует и воспроизводит текст."""
        try:
            logger.info(f"Синтезируем: {text}")
            
            # Генерация аудио с помощью TTS
            # Базовые параметры для синтеза
            kwargs = {
                "text": text,
                "language": self.language
            }
            
            # Выбираем между клонированием голоса или использованием встроенного голоса
            if self.speaker_wav and os.path.exists(self.speaker_wav):
                kwargs["speaker_wav"] = self.speaker_wav
                logger.info(f"Используется клонирование голоса из файла: {self.speaker_wav}")
            else:
                kwargs["speaker"] = self.speaker
                logger.info(f"Используется встроенный голос: {self.speaker}")
            
            # Генерируем аудио с правильными параметрами
            audio_data = self.tts.tts(**kwargs)
            
            # Воспроизводим аудио
            audio_array = np.array(audio_data)
            sd.play(audio_array, self.tts.synthesizer.output_sample_rate)
            sd.wait()
            logger.info("Воспроизведение завершено")
        except Exception as e:
            logger.error(f"Ошибка при синтезе или воспроизведении: {e}")
