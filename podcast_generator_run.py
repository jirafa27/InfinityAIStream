from redis.redis_manager import RedisManager
from podcast_generator.podcast_generator import PodcastGenerator
from podcast_generator.text_generator import LLMTextGenerator   
import asyncio
import aiohttp 

redis_manager = RedisManager()
llm = LLMTextGenerator()    
podcast_generator = PodcastGenerator(llm, redis_manager)

async def main():
    await redis_manager.connect()
    async with aiohttp.ClientSession() as session:
        await podcast_generator.run(session)

if __name__ == "__main__":
    asyncio.run(main())