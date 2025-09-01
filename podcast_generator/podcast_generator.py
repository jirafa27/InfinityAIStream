import asyncio
import json
from podcast_generator.text_generator import LLMTextGenerator
from core.utils import transliterate_and_replace_symbols
from core.logger import logger
from redis.redis_manager import RedisManager
from podcast_generator.build_prompts import PromptsBuilder

class PodcastGenerator:
    """
    Генерирует реплики и добавляет их в очередь Redis.
    """
    def __init__(self, llm: LLMTextGenerator, redis_manager: RedisManager):
        self.llm = llm
        self.redis_manager = redis_manager
        self.prompts_builder = PromptsBuilder()


    async def run(self, session):
        """Основной цикл генерации подкастов"""
        current_topic = "Зачем философия современному человеку?"
        while True:
            logger.info(f"Генерация монолога на тему: {current_topic}")
            monologue = await self.generate_monologue(session, current_topic)
            monologue_sentences, current_topic = self.extract_new_topic_and_sentences(monologue)
            logger.info(f"Сгенерировано {len(monologue_sentences)} предложений")
            logger.info(f"Очередь сообщений в чате: {await self.redis_manager.get_chat_messages_queue_length()}")
            logger.info(f"Очередь сообщений в очереди для генерации монолога: {await self.redis_manager.get_podcast_messages_queue_length()}")
            for sentence in monologue_sentences:
                await self.redis_manager.add_podcast_message(sentence)
                while await self.redis_manager.get_chat_messages_queue_length() > 0:
                    msg_data = await self.redis_manager.get_chat_message()
                    await self.react_to_chat(msg_data, session, current_topic)
                await asyncio.sleep(1)
            await asyncio.sleep(1)
            logger.info(f"Завершена генерация монолога на тему: {current_topic}")
            while await self.redis_manager.get_podcast_messages_queue_length() >= 100:
                await asyncio.sleep(10)
                logger.info(f"Уже сгенерировано много предложений, ожидание освобождения очереди")

    async def generate_monologue(self, session, current_topic):
        """Генерирует монолог на указанную тему"""
        topics = await self.redis_manager.get_podcast_topics()
        prompt = self.prompts_builder.build_prompt_for_monologue(topics, current_topic) 
        text = await self.llm.generate_text(prompt, session)
        return text

    async def react_to_chat(self, msg_data, session, current_topic):
        """Добавляет в очередь Redis реакцию на сообщение в чате"""
        try:
            message = json.loads(msg_data['data'])
            author = message.get('author', 'Аноним')
            content = message.get('content', '')
            
            logger.info(f"Новое сообщение в чате от {author}: {content}")

            prompt = self.prompts_builder.build_prompt_for_comment(current_topic, content, author)
            response_message = await self.llm.generate_text(prompt, session)
            chat_message = f"{author} пишет в чате: {content}"
            response_message = transliterate_and_replace_symbols(response_message)
            await self.redis_manager.add_reacted_to_chat_message(chat_message)
            await self.redis_manager.add_reacted_to_chat_message(response_message)

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Ошибка обработки сообщения из чата: {e}")


    def extract_new_topic_and_sentences(self, text):
        """Извлекает новую тему и предложения для выступления из текста"""
        parts = text.split("НОВАЯ ТЕМА:")
        text_for_speaking = parts[0].strip()
        new_topic = parts[1].strip() if len(parts) > 1 else ""
        sentences = [s.strip()+"." for s in text_for_speaking.split('.') if s.strip()]
        return sentences, new_topic

