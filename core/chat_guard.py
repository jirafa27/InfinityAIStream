import hashlib
import time
from collections import deque

from core.config import Config
from core.logger import logger
from core.metrics import metrics


class ChatGuard:
    """Ограничение активности Twitch-чата."""

    def __init__(self) -> None:
        self._user_last_reply: dict[str, float] = {}
        self._global_last_reply = 0.0
        self._event_times: deque[float] = deque()
        self._recent_hashes: deque[str] = deque(maxlen=200)
        self._recent_hash_set: set[str] = set()

    def _trim_events(self, now: float) -> None:
        cutoff = now - 60.0
        while self._event_times and self._event_times[0] < cutoff:
            self._event_times.popleft()

    def _remember_hash(self, digest: str) -> None:
        if digest in self._recent_hash_set:
            return
        if len(self._recent_hashes) == self._recent_hashes.maxlen:
            old = self._recent_hashes.popleft()
            self._recent_hash_set.discard(old)
        self._recent_hashes.append(digest)
        self._recent_hash_set.add(digest)

    def should_accept(self, author: str, content: str) -> bool:
        now = time.time()
        content = (content or "").strip()
        if not content:
            return False

        if len(content) > Config.CHAT_MAX_MESSAGE_LENGTH:
            content = content[: Config.CHAT_MAX_MESSAGE_LENGTH]

        digest = hashlib.sha256(f"{author}:{content}".encode()).hexdigest()
        if digest in self._recent_hash_set:
            metrics.chat_dropped_total += 1
            return False

        self._trim_events(now)
        if len(self._event_times) >= Config.CHAT_MAX_EVENTS_PER_MINUTE:
            metrics.chat_dropped_total += 1
            logger.warning("Превышен лимит событий чата в минуту")
            return False

        self._event_times.append(now)
        self._remember_hash(digest)
        metrics.chat_events_total += 1
        return True

    def can_respond_to_user(self, author: str) -> bool:
        now = time.time()
        if now - self._global_last_reply < Config.CHAT_RESPONSE_COOLDOWN_SECONDS:
            return False
        last_user = self._user_last_reply.get(author, 0.0)
        if now - last_user < Config.CHAT_USER_COOLDOWN_SECONDS:
            return False
        return True

    def mark_responded(self, author: str) -> None:
        now = time.time()
        self._global_last_reply = now
        self._user_last_reply[author] = now

    def is_chat_busy(self) -> bool:
        self._trim_events(time.time())
        threshold = max(10, Config.CHAT_MAX_EVENTS_PER_MINUTE // 2)
        return len(self._event_times) >= threshold


chat_guard = ChatGuard()
