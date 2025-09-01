import time
from core.logger import logger
from speech.speech_synthesizer import SpeechSynthesizer
from transliterate import translit

def main():
    """Тест синтеза речи с Silero TTS"""
    logger.info("Тестирование Silero TTS...")
    
    # Измеряем время инициализации
    start_time = time.time()
    synthesizer = SpeechSynthesizer()
    init_time = time.time() - start_time
    logger.info(f"Инициализация заняла {init_time:.2f} секунд")

    
    # Тестовые фразы разной длины
    test_texts = [
        "Привет! Это тестовая фраза для Silero TTS.",
        "Модель Silero TTS предназначена для работы с русским языком и имеет очень хорошее качество произношения.",
        "Она значительно быстрее многих альтернативных решений и хорошо работает даже на процессоре."
    ]
    
    test_texts = [translit(text, "ru") for text in test_texts]

    print(test_texts)


    # Запускаем тесты для всех фраз
    for i, text in enumerate(test_texts):
        logger.info(f"\nТест {i+1}: \"{text}\"")
        start_time = time.time()
        synthesizer.synthesize_and_play(text)
        synthesis_time = time.time() - start_time
        logger.info(f"Синтез и воспроизведение заняли {synthesis_time:.2f} секунд")
    
    # Получаем доступные голоса
    synthesizer = SpeechSynthesizer()
    available_voices = synthesizer.available_speakers
    logger.info(f"Доступные голоса: {available_voices}")
    
    # Тест для разных голосов (используем только доступные)
    test_voices = ["baya", "kseniya", "xenia", "aidar"]
    voices_to_test = [v for v in test_voices if v in available_voices]
    
    if not voices_to_test:
        voices_to_test = available_voices[:2] if len(available_voices) >= 2 else available_voices
        
    text = "Этот текст читается разными голосами Silero TTS."
    
    for voice in voices_to_test:
        try:
            logger.info(f"\nТестирование голоса: {voice}")
            # Создаем новый экземпляр для каждого голоса, чтобы обойти ограничения Singleton
            synthesizer = SpeechSynthesizer(speaker=voice)
            synthesizer.synthesize_and_play(text)
            # Принудительная пауза между голосами
            time.sleep(1)
        except Exception as e:
            logger.error(f"Ошибка при тестировании голоса {voice}: {e}")
            
    # Проверка смены голоса в рамках одного экземпляра
    if len(voices_to_test) >= 2:
        logger.info("\nТест смены голоса без пересоздания объекта:")
        synthesizer = SpeechSynthesizer(speaker=voices_to_test[0])
        synthesizer.synthesize_and_play("Говорю первым голосом")
        
        # Создаем новый экземпляр с другим голосом, но из-за Singleton должен использоваться тот же объект
        synthesizer2 = SpeechSynthesizer(speaker=voices_to_test[1]) 
        synthesizer2.synthesize_and_play("А теперь говорю другим голосом")
    
    logger.info("\nТестирование Silero TTS завершено")

if __name__ == "__main__":
    main()
