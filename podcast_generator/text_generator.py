import asyncio
import logging
from typing import Optional

import aiohttp

from core.config import Config
from core.metrics import metrics

logger = logging.getLogger(__name__)


class LLMTextGenerator:
    """Генерирует текст через OpenRouter или F5AI (OpenAI-compatible API)."""

    _semaphore: asyncio.Semaphore | None = None

    def __init__(self):
        self._provider = Config.llm_provider()
        self._api_url = Config.llm_api_url()
        self._model = Config.llm_model()
        self._headers = Config.llm_headers()
        logger.info("LLM: %s, model=%s", self._provider, self._model)
        if LLMTextGenerator._semaphore is None:
            LLMTextGenerator._semaphore = asyncio.Semaphore(Config.AI_MAX_CONCURRENCY)

    @classmethod
    def _truncate_prompt(cls, prompt: str) -> str:
        if len(prompt) <= Config.AI_MAX_INPUT_CHARS:
            return prompt
        logger.warning(
            "Промпт обрезан: %s -> %s символов",
            len(prompt),
            Config.AI_MAX_INPUT_CHARS,
        )
        return prompt[: Config.AI_MAX_INPUT_CHARS]

    async def generate_text(
        self,
        prompt: str,
        session: aiohttp.ClientSession,
        *,
        max_tokens: int | None = None,
    ) -> Optional[str]:
        if not self._api_url:
            logger.error("LLM API URL не установлен (provider=%s)", self._provider)
            return None

        prompt = self._truncate_prompt(prompt)
        data = {
            "model": self._model,
            "max_tokens": max_tokens if max_tokens is not None else Config.AI_MAX_OUTPUT_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
        }

        async with self._semaphore:
            metrics.ai_requests_total += 1
            retries = 0
            while retries <= Config.AI_MAX_RETRIES:
                try:
                    async with session.post(
                        self._api_url,
                        headers=self._headers,
                        json=data,
                        timeout=Config.AI_REQUEST_TIMEOUT_SECONDS,
                    ) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            return result["choices"][0]["message"]["content"]
                        if resp.status in (429, 500, 502, 503, 504):
                            metrics.ai_errors_total += 1
                            logger.warning(
                                "%s API вернул %s, попытка %s/%s",
                                self._provider,
                                resp.status,
                                retries + 1,
                                Config.AI_MAX_RETRIES + 1,
                            )
                            if retries >= Config.AI_MAX_RETRIES:
                                break
                            await asyncio.sleep(2**retries)
                            retries += 1
                            continue
                        metrics.ai_errors_total += 1
                        logger.error(
                            "Ошибка %s API: %s %s",
                            self._provider,
                            resp.status,
                            await resp.text(),
                        )
                        break
                except asyncio.TimeoutError:
                    metrics.ai_errors_total += 1
                    logger.warning(
                        "Таймаут запроса к %s (%ss), попытка %s/%s",
                        self._provider,
                        Config.AI_REQUEST_TIMEOUT_SECONDS,
                        retries + 1,
                        Config.AI_MAX_RETRIES + 1,
                    )
                    if retries >= Config.AI_MAX_RETRIES:
                        break
                    await asyncio.sleep(2**retries)
                    retries += 1
                except Exception as e:
                    metrics.ai_errors_total += 1
                    logger.error("Ошибка при запросе к %s API: %s", self._provider, e)
                    break

        return None
