"""Простое чтение Twitch-чата через IRC (без EventSub / TwitchIO)."""

from __future__ import annotations

import asyncio
import logging
import re
import ssl
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

IRC_HOST = "irc.chat.twitch.tv"
IRC_PORT = 6697

# @tags :user!user@user.tmi.twitch.tv PRIVMSG #channel :text
_PRIVMSG = re.compile(
    r"^@(?P<tags>[^ ]+) :(?P<user>[^!]+)![^ ]+ PRIVMSG #(?P<channel>[^ ]+) :(?P<text>.+)$"
)
_PRIVMSG_PLAIN = re.compile(
    r"^:(?P<user>[^!]+)![^ ]+ PRIVMSG #(?P<channel>[^ ]+) :(?P<text>.+)$"
)


def _display_name(tags: str) -> str:
    for part in tags.split(";"):
        if part.startswith("display-name="):
            name = part.split("=", 1)[1]
            return name.strip()
    return ""


def _tag_value(tags: str, name: str) -> str:
    prefix = f"{name}="
    for part in tags.split(";"):
        if part.startswith(prefix):
            return part[len(prefix) :].strip()
    return ""


MessageHandler = Callable[[str, str, str], Awaitable[None]]


class TwitchIrcReader:
    def __init__(
        self,
        *,
        token: str,
        nick: str,
        channel: str,
        on_message: MessageHandler,
        reconnect_delay: float = 5.0,
    ) -> None:
        self._token = token
        self._nick = nick.lower()
        self._channel = channel.lstrip("#").lower()
        self._on_message = on_message
        self._reconnect_delay = reconnect_delay
        self._writer: asyncio.StreamWriter | None = None
        self._running = False

    async def _send(self, line: str) -> None:
        if not self._writer:
            return
        self._writer.write(f"{line}\r\n".encode("utf-8"))
        await self._writer.drain()

    async def send_channel_message(self, text: str) -> None:
        if not text.strip():
            return
        await self._send(f"PRIVMSG #{self._channel} :{text.strip()}")

    async def _handle_line(self, raw: str) -> None:
        if raw.startswith("PING"):
            await self._send("PONG :tmi.twitch.tv")
            return

        match = _PRIVMSG.match(raw) or _PRIVMSG_PLAIN.match(raw)
        if not match:
            return

        author = _display_name(match.groupdict().get("tags") or "") or match.group("user")
        content = match.group("text").strip()
        tags = match.groupdict().get("tags") or ""
        msg_id = _tag_value(tags, "id")
        if content:
            await self._on_message(author, content, msg_id)

    async def _session(self) -> None:
        ssl_ctx = ssl.create_default_context()
        reader, writer = await asyncio.open_connection(
            IRC_HOST, IRC_PORT, ssl=ssl_ctx
        )
        self._writer = writer

        await self._send(f"PASS oauth:{self._token}")
        await self._send(f"NICK {self._nick}")
        await self._send("CAP REQ :twitch.tv/tags twitch.tv/commands")
        await self._send(f"JOIN #{self._channel}")

        logger.info("IRC: подключён к #%s как %s", self._channel, self._nick)

        while self._running:
            line = await reader.readline()
            if not line:
                raise ConnectionError("IRC-соединение закрыто")
            await self._handle_line(line.decode("utf-8", errors="ignore").strip())

    async def run(self) -> None:
        self._running = True
        while self._running:
            try:
                await self._session()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("IRC: %s — переподключение через %.0f с", exc, self._reconnect_delay)
                await asyncio.sleep(self._reconnect_delay)
            finally:
                if self._writer:
                    self._writer.close()
                    try:
                        await self._writer.wait_closed()
                    except Exception:
                        pass
                    self._writer = None

    def stop(self) -> None:
        self._running = False
        if self._writer:
            self._writer.close()
