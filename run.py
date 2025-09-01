from podcast_generator.podcast_generator import PodcastGenerator
from podcast_generator.text_generator import LLMTextGenerator
from redis.redis_manager import RedisManager
from streamer.streamer import Streamer
import asyncio
import aiohttp

async def main():
    redis_manager = RedisManager()
    await redis_manager.connect()
    
    try:
        llm = LLMTextGenerator()
        podcast_generator = PodcastGenerator(llm, redis_manager)
        streamer = Streamer(redis_manager)
        
        async with aiohttp.ClientSession() as session:
            # Запускаем оба компонента параллельно
            await asyncio.gather(
                podcast_generator.run(session),
                streamer.run()
            )
    finally:
        await redis_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(main())




