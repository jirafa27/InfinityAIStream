import asyncio
import logging
import re

import requests

from core.app_state import app_state
from core.chat_guard import chat_guard
from core.config import Config
from core.health_server import HealthServer
from core.logger import logger as app_logger
from core.shutdown import shutdown
from redis_client.redis_manager import RedisManager
from redis_client.chat_outbound_store import ChatOutboundStore
from redis_client.topic_apply import apply_topic_with_interrupt
from redis_client.topic_control_store import TopicControlStore
from twitch_irc import TwitchIrcReader
from twitch_token_manager import TokenManager

logger = logging.getLogger(__name__)

# Twitch перехватывает /команды и не отправляет их в IRC — только ! ? . или без префикса
_SET_TOPIC_RE = re.compile(r"^[!?.]?set_topic(?:\s+(.+))?$", re.IGNORECASE)


def _match_set_topic_command(content: str) -> tuple[bool, str]:
    match = _SET_TOPIC_RE.match(content.strip())
    if not match:
        return False, ""
    topic = (match.group(1) or "").strip()[:500]
    return True, topic


def _validate_token(token: str) -> dict | None:
    try:
        resp = requests.get(
            "https://id.twitch.tv/oauth2/validate",
            headers={"Authorization": f"OAuth {token}"},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        return resp.json()
    except requests.RequestException as exc:
        logger.warning("Не удалось проверить Twitch token: %s", exc)
        return None


class ChatReaderService:
    def __init__(self, redis_manager: RedisManager, token_manager: TokenManager):
        self.redis_manager = redis_manager
        self.topic_store = TopicControlStore(redis_manager.redis_client)
        self.chat_outbound = ChatOutboundStore(redis_manager.redis_client)
        self._token_manager = token_manager
        self._irc: TwitchIrcReader | None = None

    async def _reply_in_chat(self, text: str) -> None:
        if not self._irc:
            return
        try:
            await self._irc.send_channel_message(text)
        except Exception as exc:
            logger.warning("Не удалось отправить сообщение в Twitch: %s", exc)

    async def _on_message(self, author: str, content: str, message_id: str = "") -> None:
        if not app_state.accept_new_events or app_state.shutting_down:
            return
        if not content.strip():
            return

        is_set_topic, topic = _match_set_topic_command(content)
        if is_set_topic:
            if not topic:
                logger.info("Пустой set_topic от %s", author)
                await self._reply_in_chat(
                    "Использование: !set_topic Ваш текст темы "
                    "(слэш / не работает в Twitch-чате)"
                )
                return
            dropped = await apply_topic_with_interrupt(
                self.topic_store,
                self.redis_manager,
                topic,
                announce_in_chat=True,
            )
            logger.info(
                "Тема из Twitch [%s]: %s (очередь монолога: -%s)",
                author,
                topic,
                dropped,
            )
            app_state.touch_heartbeat()
            return

        if not chat_guard.should_accept(author, content):
            logger.debug("Сообщение от %s отфильтровано chat_guard", author)
            return

        chat_message = {
            "author": author,
            "content": content[: Config.CHAT_MAX_MESSAGE_LENGTH],
        }
        if message_id:
            chat_message["id"] = message_id
        logger.info("Чат Twitch [%s]: %s", author, chat_message["content"])
        app_state.touch_heartbeat()
        await self.redis_manager.add_chat_message(chat_message)

    async def _outbound_loop(self) -> None:
        interval = Config.STREAMER_POLL_INTERVAL
        while not app_state.shutting_down:
            try:
                if not self._irc:
                    await asyncio.sleep(interval)
                    continue
                text = await self.chat_outbound.pop_message()
                if text:
                    await self._reply_in_chat(text)
                    await asyncio.sleep(0.4)
                else:
                    await asyncio.sleep(interval)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Ошибка отправки в Twitch-чат: %s", exc)
                await asyncio.sleep(interval)

    async def run(self) -> None:
        outbound_task = asyncio.create_task(self._outbound_loop())
        try:
            await self._run_irc()
        finally:
            outbound_task.cancel()
            try:
                await outbound_task
            except asyncio.CancelledError:
                pass

    async def _run_irc(self) -> None:
        while not app_state.shutting_down:
            token = self._token_manager.get_token()
            if not token:
                logger.error(
                    "TWITCH_ACCESS_TOKEN не задан (.env.twitch). "
                    "Получите на https://twitchtokengenerator.com (scopes: chat:read chat:edit)"
                )
                await asyncio.sleep(30)
                continue

            info = _validate_token(token)
            if info is None:
                if self._token_manager.refresh_token:
                    logger.warning("Twitch token невалиден, обновляю…")
                    try:
                        self._token_manager.refresh_twitch_token()
                    except Exception as exc:
                        logger.error("Не удалось обновить token: %s", exc)
                        await asyncio.sleep(30)
                    continue
                logger.error("Twitch token невалиден. Обновите .env.twitch")
                await asyncio.sleep(30)
                continue

            nick = (info.get("login") or Config.TWITCH_CHANNEL).lower()
            logger.info(
                "Twitch IRC: login=%s scopes=%s channel=#%s",
                nick,
                info.get("scopes"),
                Config.TWITCH_CHANNEL,
            )

            self._irc = TwitchIrcReader(
                token=token,
                nick=nick,
                channel=Config.TWITCH_CHANNEL,
                on_message=self._on_message,
            )
            app_state.twitch_connected = True
            print(f"Чат Twitch активен: #{Config.TWITCH_CHANNEL}")

            try:
                await self._irc.run()
            except asyncio.CancelledError:
                break
            finally:
                app_state.twitch_connected = False
                if self._irc:
                    self._irc.stop()
                    self._irc = None

            if not app_state.shutting_down:
                await asyncio.sleep(5)


async def main() -> None:
    app_state.role = "chat_reader"
    token_manager = TokenManager()
    redis_manager = RedisManager()
    await redis_manager.connect()

    health = HealthServer(redis_manager)
    await health.start()

    shutdown.register(health.stop)
    shutdown.register(redis_manager.disconnect)

    service = ChatReaderService(redis_manager, token_manager)
    reader_task = asyncio.create_task(service.run())
    shutdown_task = asyncio.create_task(app_state.wait_shutdown())

    loop = asyncio.get_event_loop()
    shutdown.install_signal_handlers(loop)

    done, pending = await asyncio.wait(
        [reader_task, shutdown_task],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    await shutdown.run("bot-stop")
    app_logger.info("Chat reader остановлен")


if __name__ == "__main__":
    asyncio.run(main())
