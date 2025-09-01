from core.logger import logger
from redis.redis_manager import RedisManager
from speech.speech_synthesizer import SpeechSynthesizer

class Streamer:
    """
    Берет сообщения из очередей Redis и синтезирует их в речь.
    """
    def __init__(self, redis_manager: RedisManager):
        self.redis_manager = redis_manager
        self.speech_synthesizer = SpeechSynthesizer()

    async def run(self):
        while True:
            # Сначала обрабатываем сообщения из очереди reacted_to_chat_messages_queue
            while await self.redis_manager.get_reacted_to_chat_messages_queue_length() > 0:
                logger.info(f"Обработка сообщений из очереди reacted_to_chat_messages_queue")
                msg_data = await self.redis_manager.get_reacted_to_chat_message()
                logger.info(f"Получено сообщение из очереди reacted_to_chat_messages_queue: {msg_data.decode('utf-8')}")
                if msg_data:
                    text = msg_data.decode('utf-8') if isinstance(msg_data, bytes) else msg_data
                    self.speech_synthesizer.synthesize_and_play(text)
            # Затем обрабатываем сообщения из очереди podcast_messages_queue
            if await self.redis_manager.get_podcast_messages_queue_length() > 0:
                msg_data = await self.redis_manager.get_podcast_message()
                logger.info(f"Получено сообщение из очереди podcast_messages_queue: {msg_data.decode('utf-8')}")
                if msg_data:
                    text = msg_data.decode('utf-8') if isinstance(msg_data, bytes) else msg_data
                    logger.info(f"Синтезируется сообщение: {text}")
                    self.speech_synthesizer.synthesize_and_play(text)
    
            logger.info(f"Очередь сообщений в очереди для генерации монолога: {await self.redis_manager.get_podcast_messages_queue_length()}")
            logger.info(f"Очередь сообщений в очереди для реакции на чат: {await self.redis_manager.get_reacted_to_chat_messages_queue_length()}")
            logger.info(f"Очередь сообщений в чате: {await self.redis_manager.get_chat_messages_queue_length()}")

            
