from speech.speech_synthesizer import SpeechSynthesizer
from core.logger import logger
import time

def main():
    """Пример использования синтезатора речи."""
    
    # Тест специализированной русской модели tacotron2
    logger.info("Запуск тестового синтеза речи на русском языке со специализированной моделью...")
    start_time = time.time()
    
    synthesizer = SpeechSynthesizer()  # Используем русскую tacotron2 модель
    text = "Привет! Это тестовое сообщение для проверки синтеза речи. Пурум пурум пурум. Поговорила я еще что-нибудь."
    synthesizer.synthesize_and_play(text)
    
    logger.info(f"Тест синтеза речи на русском языке завершен за {time.time() - start_time:.2f} секунд")
    

if __name__ == "__main__":
    main()
