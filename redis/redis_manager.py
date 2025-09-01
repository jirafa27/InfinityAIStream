import aioredis
from core.config import Config


class RedisManager:
    def __init__(self):
        self.redis_client = None
    
    async def connect(self):
        """Подключение к Redis"""
        redis_url = f"redis://{Config.REDIS_HOST}:{Config.REDIS_PORT}/{Config.REDIS_DB}"
        self.redis_client = aioredis.from_url(redis_url)
    
    async def disconnect(self):
        """Отключение от Redis"""
        if self.redis_client:
            await self.redis_client.close()

    async def get_podcast_message(self):
        return await self.redis_client.lpop('podcast_messages_queue')
    
    async def get_chat_message(self):
        return await self.redis_client.lpop('chat_messages_queue')
    
    async def add_podcast_message(self, message):
        await self.redis_client.rpush('podcast_messages_queue', message)
    
    async def add_chat_message(self, message):
        await self.redis_client.rpush('chat_messages_queue', message)


    async def get_podcast_messages_queue_length(self):
        return await self.redis_client.llen('podcast_messages_queue')
    
    async def get_chat_messages_queue_length(self):
        return await self.redis_client.llen('chat_messages_queue')
    

    async def add_reacted_to_chat_message(self, message):
        await self.redis_client.rpush('reacted_to_chat_messages_queue', message)

    async def get_reacted_to_chat_message(self):
        return await self.redis_client.lpop('reacted_to_chat_messages_queue')

    async def get_reacted_to_chat_messages_queue_length(self):
        return await self.redis_client.llen('reacted_to_chat_messages_queue')


    async def add_podcast_topic(self, topic):
        """Добавить новую тему в список"""
        await self.redis_client.lpush('podcast_topics', topic)
        await self.redis_client.ltrim('podcast_topics', 0, 100)

    async def get_podcast_topics(self):
        """Получить список тем"""
        return await self.redis_client.lrange('podcast_topics', 0, -1)