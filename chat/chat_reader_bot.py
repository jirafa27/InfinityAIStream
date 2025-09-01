import logging
import os
from twitchio.ext import commands
from core.config import Config
from twitch_token_manager import TokenManager
from redis.redis_manager import RedisManager

logger = logging.getLogger(__name__)

class ChatReaderBot(commands.Bot):
    """
    Класс для чтения сообщений из чата и добавления их в очередь Redis.
    """
    def __init__(self, redis_manager: RedisManager, token_manager: TokenManager):
        super().__init__(
            token=token_manager.get_token(),
            prefix='!',
            initial_channels=[Config.TWITCH_CHANNEL],
            client_id=token_manager.client_id,
            client_secret=token_manager.client_secret,
            bot_id=os.getenv('TWITCH_BOT_ID', token_manager.client_id)
        )
        self.token_manager = token_manager
        self.redis_manager = redis_manager

    async def event_ready(self):
        logger.info(f'Бот вошёл как {self.nick}')
        print(f'Бот вошёл как {self.nick}')

    async def event_message(self, message):
        if message.echo:
            return
        
        chat_message = {
            "author": message.author.name,
            "content": message.content
        }
        info = f"Новое сообщение в чате от {chat_message['author']}: {chat_message['content']}"
        logger.info(info)        
        self.redis_manager.add_chat_message(chat_message)

    async def start_bot(self):
        while True:
            try:
                await self.start()
                break
            except Exception as e:
                err = str(e).lower()
                if "invalid or unauthorized access token" in err:
                    print("Токен истёк или невалиден, обновляю...")
                    self.token_manager.refresh_twitch_token()
                    self.token = self.token_manager.get_token()
                else:
                    raise

def main():
    token_manager = TokenManager()
    redis_manager = RedisManager()
    bot = ChatReaderBot(redis_manager, token_manager)
    bot.run()

if __name__ == '__main__':
    main()

