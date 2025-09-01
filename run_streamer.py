from redis.redis_manager import RedisManager
from streamer.streamer import Streamer

import asyncio

redis_manager = RedisManager()
streamer = Streamer(redis_manager)

async def main():
    await redis_manager.connect()
    await streamer.run()

if __name__ == "__main__":
    asyncio.run(main())