import aiohttp
import logging
from typing import Optional
import asyncio
import os
from core.config import Config


logger = logging.getLogger(__name__)


class LLMTextGenerator:
    """
    Генерирует текст на основе prompt с использованием F5AI API.
    Args:
        prompt: str - текст, на основе которого будет генерироваться текст
        session: aiohttp.ClientSession - сессия для выполнения запросов
    Returns:
        Optional[str] - сгенерированный текст или None, если произошла ошибка
    """
    def __init__(self):
        self.F5AI_API_TOKEN = Config.F5AI_API_TOKEN
        self.F5AI_MODEL = Config.F5AI_MODEL
        self.F5AI_API_URL = Config.F5AI_API_URL

    async def generate_text(self, prompt: str, session: aiohttp.ClientSession) -> Optional[str]:
        if not self.F5AI_API_URL:
            logger.error('F5AI_API_URL не установлен')
            return None
            
        headers = {
            'Content-Type': 'application/json',
            'X-Auth-Token': self.F5AI_API_TOKEN,
        }
        data = {
            'model': self.F5AI_MODEL,
            'max_tokens': 4000,
            'messages': [
                {'role': 'user', 'content': prompt}
            ]
        }
        retries = 0
        while retries < 5:
            try:
                async with session.post(self.F5AI_API_URL, headers=headers, json=data, timeout=30) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return result['choices'][0]['message']['content']
                    elif resp.status in (429, 502):
                        logger.warning(f'F5AI API вернул {resp.status}, попытка {retries+1}')
                        await asyncio.sleep(2 ** retries)
                        retries += 1
                    else:
                        logger.error(f'Ошибка F5AI API: {resp.status} {await resp.text()}')
                        break
            except asyncio.TimeoutError:
                logger.warning('Таймаут запроса к F5AI API, повтор...')
                await asyncio.sleep(2 ** retries)
                retries += 1
            except Exception as e:
                logger.error(f'Ошибка при запросе к F5AI API: {e}')
                break
        return None



if __name__ == '__main__':
    import asyncio
    async def main():
        text_generator = LLMTextGenerator()
        session = aiohttp.ClientSession()
        prompt = 'Ты - подкастер на твиче, который ведет бесконечный философский стрим. Сгенерируй текст на какую-либо тему по философии, а в конце припиши промпт для следующего запроса тебе, который я буду присылать тебе дальше. В итоге должен получиться связный и интересный текст.'
        result = await text_generator.generate_text(prompt, session)
        print(result)
    asyncio.run(main())