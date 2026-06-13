import asyncio
import html
import logging
import os
import socket
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

from redis_client.chat_notify_store import ChatNotifyStore
from redis_client.redis_manager import RedisManager
from redis_client.stream_control_store import StreamControlStore
from redis_client.topic_apply import (
    apply_random_authors_with_interrupt,
    apply_topic_if_quotes_available,
)
from podcast_generator.manual_topic_preflight import manual_topic_rejection_message
from podcast_generator.topic_rules import is_random_author_mode
from redis_client.topic_control_store import TopicControlStore
from obs.obs_signal_service import ObsSignalService
from stream_control.docker_compose_runner import DockerContainerRunner
from stream_control.stream_control_service import StreamControlService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _poll_retry_seconds() -> float:
    return float(os.getenv("TELEGRAM_POLL_RETRY_SECONDS", "15"))


_LOCAL_PROXIES: tuple[tuple[int, str], ...] = (
    (10808, "socks5"),  # v2rayN
    (7891, "socks5"),   # Clash
    (1080, "socks5"),
    (7890, "http"),     # Clash HTTP
)


def _probe_local_proxy() -> str | None:
    for port, scheme in _LOCAL_PROXIES:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return f"{scheme}://127.0.0.1:{port}"
        except OSError:
            continue
    return None


def _telegram_proxy() -> str | None:
    explicit = os.getenv("TELEGRAM_PROXY", "").strip()
    if explicit:
        return explicit
    if os.getenv("TELEGRAM_AUTO_PROXY", "0") == "1":
        return _probe_local_proxy()
    return None


def _setup_asyncio() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _create_bot(token: str) -> Bot:
    proxy = _telegram_proxy()
    if proxy:
        logger.info("Telegram API через proxy: %s", proxy)
        return Bot(token=token, session=AiohttpSession(proxy=proxy))
    logger.warning(
        "Telegram без прокси — если api.telegram.org недоступен, "
        "задайте TELEGRAM_PROXY=socks5://127.0.0.1:10808 в .env"
    )
    return Bot(token=token)


def _configure_redis_host() -> None:
    host = os.getenv("LOCAL_REDIS_HOST") or os.getenv("REDIS_HOST", "localhost")
    os.environ["REDIS_HOST"] = host
    logger.info("Redis: %s:%s", host, os.getenv("REDIS_PORT", "6379"))


async def _poll_with_retry(bot: Bot, dp: Dispatcher) -> None:
    while True:
        try:
            await dp.start_polling(bot)
            return
        except TelegramNetworkError as exc:
            delay = _poll_retry_seconds()
            logger.warning(
                "Telegram API недоступен (%s), повтор через %ss",
                exc,
                delay,
            )
            await asyncio.sleep(delay)


def _allowed_user_ids() -> set[int]:
    raw = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")
    return {int(x.strip()) for x in raw.split(",") if x.strip().isdigit()}


def _guard(message: Message, allowed: set[int]) -> bool:
    user = message.from_user
    if user is None or user.id not in allowed:
        return False
    return True


async def _notify_allowed_users(
    bot: Bot,
    allowed: set[int],
    text: str,
    parse_mode: str | None = None,
) -> None:
    for user_id in allowed:
        try:
            await bot.send_message(user_id, text, parse_mode=parse_mode)
        except Exception as exc:
            logger.warning("Не удалось отправить user %s: %s", user_id, exc)


async def _format_chat_notification(data: dict) -> str:
    author = html.escape(data.get("author", "Аноним"))
    content = html.escape(data.get("content", ""))
    response = html.escape(data.get("response", "") or "—")
    max_response = int(os.getenv("TELEGRAM_CHAT_RESPONSE_MAX_CHARS", "3000"))
    if len(response) > max_response:
        response = response[: max_response - 1] + "…"
    return (
        f"<b>Чат Twitch</b>\n\n"
        f"<b>{author}</b>:\n{content}\n\n"
        f"<b>Ответ бота:</b>\n{response}"
    )


async def _chat_notify_loop(
    bot: Bot,
    allowed: set[int],
    chat_notify: ChatNotifyStore,
) -> None:
    if os.getenv("TELEGRAM_CHAT_NOTIFY", "1") != "1":
        return
    interval = float(os.getenv("TELEGRAM_CHAT_POLL_INTERVAL", "2.0"))
    while True:
        try:
            data = await chat_notify.pop_notification()
            if data:
                text = await _format_chat_notification(data)
                await _notify_allowed_users(bot, allowed, text, parse_mode="HTML")
            else:
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Ошибка chat notify loop: %s", exc)
            await asyncio.sleep(interval)


async def _topic_notify_loop(
    bot: Bot,
    allowed: set[int],
    topic_store: TopicControlStore,
) -> None:
    """Забирает новые темы из Redis и шлёт в Telegram."""
    interval = float(os.getenv("TELEGRAM_TOPIC_POLL_INTERVAL", "2.0"))
    while True:
        try:
            topic = await topic_store.pop_notification()
            if topic:
                await _notify_allowed_users(
                    bot, allowed, f"Текущая страница: {topic}",
                )
            else:
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Ошибка topic notify loop: %s", exc)
            await asyncio.sleep(interval)


def _command_name(message: Message) -> str:
    raw = message.text or ""
    if not raw.startswith("/"):
        return ""
    return raw.split(maxsplit=1)[0].split("@")[0]


async def main() -> None:
    load_dotenv()
    _configure_redis_host()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан")

    allowed = _allowed_user_ids()
    if not allowed:
        raise ValueError("TELEGRAM_ALLOWED_USER_IDS не задан")

    redis_manager = RedisManager()
    await redis_manager.connect()

    service = StreamControlService(
        StreamControlStore(redis_manager.redis_client),
        DockerContainerRunner(),
    )
    topic_store = TopicControlStore(redis_manager.redis_client)
    chat_notify = ChatNotifyStore(redis_manager.redis_client)
    obs_signals = ObsSignalService()

    bot = _create_bot(token)
    dp = Dispatcher()

    @dp.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        if not _guard(message, allowed):
            await message.answer("Доступ запрещён. Проверьте TELEGRAM_ALLOWED_USER_IDS.")
            return
        await message.answer(
            "Команды:\n"
            "/start_stream — запуск стрима\n"
            "/stop_stream — остановка\n"
            "/status — состояние контейнеров\n"
            "/page — текущая страница викицитат\n"
            "/set_topic Название — запросить страницу с Викицитат"
        )

    @dp.message(Command("start_stream"))
    async def cmd_start_stream(message: Message) -> None:
        if not _guard(message, allowed):
            return
        await message.answer("Запускаю стрим…")
        text = await service.start_stream()
        await message.answer(text[:4000])
        obs_signals.signal_telegram_command(_command_name(message))

    @dp.message(Command("stop_stream"))
    async def cmd_stop_stream(message: Message) -> None:
        if not _guard(message, allowed):
            return
        await message.answer("Останавливаю стрим…")
        text = await service.stop_stream()
        await message.answer(text[:4000])
        obs_signals.signal_telegram_command(_command_name(message))

    @dp.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        if not _guard(message, allowed):
            return
        text = await service.status()
        await message.answer(f"<pre>{text[:3800]}</pre>", parse_mode="HTML")

    @dp.message(Command("topic"))
    async def cmd_topic(message: Message) -> None:
        if not _guard(message, allowed):
            return
        current = await topic_store.get_current_topic()
        pending = await topic_store.get_pending_topic()
        manual = await topic_store.get_manual_person()
        lines = [f"На экране:\n{current or '—'}"]
        if manual and await topic_store.is_manual_topic_active():
            lines.append(f"\nЗапрошен автор:\n{manual}")
        if pending:
            lines.append(f"\nОжидает применения:\n{pending}")
        elif not manual:
            lines.append("\nСледующая не задана — будет случайная страница викицитат.")
        await message.answer("\n".join(lines))

    @dp.message(Command("page"))
    async def cmd_page(message: Message) -> None:
        await cmd_topic(message)

    @dp.message(Command("set_topic"))
    async def cmd_set_topic(message: Message) -> None:
        if not _guard(message, allowed):
            return
        raw = message.text or ""
        parts = raw.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await message.answer(
                "Использование:\n/set_topic Название страницы на Викицитатах"
            )
            return
        topic = parts[1].strip()[:500]
        if is_random_author_mode(topic):
            dropped = await apply_random_authors_with_interrupt(
                topic_store, redis_manager
            )
            logger.info("Сброс автора из Telegram (очередь: -%s)", dropped)
            await message.answer("Снова случайные авторы.")
            obs_signals.signal_telegram_command(_command_name(message))
            return
        applied, dropped, reason = await apply_topic_if_quotes_available(
            topic_store, redis_manager, topic
        )
        if not applied:
            logger.info(
                "Страница из Telegram отклонена (%s): %s",
                reason,
                topic,
            )
            await message.answer(manual_topic_rejection_message(topic, reason))
            return
        logger.info("Страница из Telegram: %s (очередь: -%s)", topic, dropped)
        await message.answer(
            f"Запрошена случайная цитата:\n<b>{topic}</b>\n\n"
            "Следующий монолог — случайная цитата этого автора.",
            parse_mode="HTML",
        )
        obs_signals.signal_telegram_command(_command_name(message))

    notify_task = asyncio.create_task(
        _topic_notify_loop(bot, allowed, topic_store),
        name="topic-notify",
    )
    chat_notify_task = asyncio.create_task(
        _chat_notify_loop(bot, allowed, chat_notify),
        name="chat-notify",
    )
    logger.info("Telegram control bot запущен")
    if obs_signals.enabled:
        logger.info(
            "OBS WebSocket: %s:%s (команды: %s)",
            os.getenv("OBS_WEBSOCKET_HOST", "127.0.0.1"),
            os.getenv("OBS_WEBSOCKET_PORT", "4455"),
            os.getenv("OBS_SIGNAL_COMMANDS", "set_topic,start_stream,stop_stream"),
        )
    try:
        await _poll_with_retry(bot, dp)
    finally:
        notify_task.cancel()
        chat_notify_task.cancel()
        for task in (notify_task, chat_notify_task):
            try:
                await task
            except asyncio.CancelledError:
                pass
        await bot.session.close()
        await redis_manager.disconnect()


if __name__ == "__main__":
    _setup_asyncio()
    asyncio.run(main())
