import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Конфигурация приложения."""

    # Профиль ресурсов VPS
    RESOURCE_PROFILE = os.getenv("RESOURCE_PROFILE", "normal").lower()

    # Twitch
    TWITCH_CHANNEL = os.getenv("TWITCH_CHANNEL")
    TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
    TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
    # Redis
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB = int(os.getenv("REDIS_DB", 0))
    REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "infinity_stream:")

    # LLM (OpenRouter / F5AI — OpenAI-compatible chat/completions)
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").lower()
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_API_URL = os.getenv(
        "OPENROUTER_API_URL", "https://openrouter.ai/api/v1"
    ).rstrip("/")
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL")
    OPENROUTER_HTTP_REFERER = os.getenv("OPENROUTER_HTTP_REFERER", "")
    OPENROUTER_APP_TITLE = os.getenv("OPENROUTER_APP_TITLE", "InfinityAIStream")

    F5AI_MODEL = os.getenv("F5AI_MODEL")
    F5AI_API_URL = os.getenv("F5AI_API_URL")
    F5AI_API_TOKEN = os.getenv("F5AI_API_TOKEN")

    AI_MAX_CONTEXT_MESSAGES = int(os.getenv("AI_MAX_CONTEXT_MESSAGES", 15))
    AI_MAX_INPUT_CHARS = int(os.getenv("AI_MAX_INPUT_CHARS", 12000))
    AI_MAX_OUTPUT_TOKENS = int(os.getenv("AI_MAX_OUTPUT_TOKENS", 1024))
    AI_MAX_CONCURRENCY = int(os.getenv("AI_MAX_CONCURRENCY", 2))
    AI_QUEUE_MAX_SIZE = int(os.getenv("AI_QUEUE_MAX_SIZE", 20))
    AI_REQUEST_TIMEOUT_SECONDS = int(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", 30))
    AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", 2))

    # Twitch chat limits
    CHAT_MAX_MESSAGE_LENGTH = int(os.getenv("CHAT_MAX_MESSAGE_LENGTH", 500))
    CHAT_RESPONSE_MAX_TOKENS = int(os.getenv("CHAT_RESPONSE_MAX_TOKENS", 120))
    CHAT_RESPONSE_MAX_CHARS = int(os.getenv("CHAT_RESPONSE_MAX_CHARS", 200))
    CHAT_RESPONSE_COOLDOWN_SECONDS = int(os.getenv("CHAT_RESPONSE_COOLDOWN_SECONDS", 15))
    CHAT_USER_COOLDOWN_SECONDS = int(os.getenv("CHAT_USER_COOLDOWN_SECONDS", 60))
    CHAT_MAX_EVENTS_PER_MINUTE = int(os.getenv("CHAT_MAX_EVENTS_PER_MINUTE", 100))
    CHAT_TTS_PRE_PAUSE_SECONDS = float(os.getenv("CHAT_TTS_PRE_PAUSE_SECONDS", "2"))
    CHAT_TTS_POST_PAUSE_SECONDS = float(os.getenv("CHAT_TTS_POST_PAUSE_SECONDS", "2"))
    CHAT_RETURN_TRANSITION = os.getenv(
        "CHAT_RETURN_TRANSITION", "Продолжим разбор цитат."
    ).strip()
    CHAT_POLL_INTERVAL_SECONDS = float(os.getenv("CHAT_POLL_INTERVAL_SECONDS", "0.2"))
    MONOLOGUE_MIN_INTERVAL_SECONDS = int(os.getenv("MONOLOGUE_MIN_INTERVAL_SECONDS", 90))

    # Wikiquote (ru.wikiquote.org)
    WIKIQUOTE_API_BASE = os.getenv(
        "WIKIQUOTE_API_BASE", "https://ru.wikiquote.org/w/api.php"
    )
    WIKIQUOTE_USER_AGENT = os.getenv(
        "WIKIQUOTE_USER_AGENT",
        "InfinityAIStream/1.0 (https://ru.wikiquote.org/; local Twitch stream bot)",
    )
    WIKIQUOTE_REQUEST_TIMEOUT_SECONDS = int(
        os.getenv("WIKIQUOTE_REQUEST_TIMEOUT_SECONDS", 20)
    )
    WIKIQUOTE_MAX_QUOTES = int(os.getenv("WIKIQUOTE_MAX_QUOTES", 8))
    WIKIQUOTE_MAX_QUOTE_CHARS = int(os.getenv("WIKIQUOTE_MAX_QUOTE_CHARS", 400))
    WIKIQUOTE_RANDOM_RETRIES = int(os.getenv("WIKIQUOTE_RANDOM_RETRIES", 6))
    WIKIQUOTE_RECENT_PAGES_LIMIT = int(os.getenv("WIKIQUOTE_RECENT_PAGES_LIMIT", 20))
    WIKIQUOTE_PERSON_CATEGORY = os.getenv(
        "WIKIQUOTE_PERSON_CATEGORY", "Категория:Персоналии по алфавиту"
    )
    WIKIQUOTE_PERSON_BATCH_SIZE = int(os.getenv("WIKIQUOTE_PERSON_BATCH_SIZE", 100))
    WIKIPEDIA_API_BASE = os.getenv(
        "WIKIPEDIA_API_BASE", "https://ru.wikipedia.org/w/api.php"
    )
    WIKIQUOTE_IMAGE_THUMB_SIZE = int(os.getenv("WIKIQUOTE_IMAGE_THUMB_SIZE", 800))
    WIKIQUOTE_COMMENTARY_MAX_CHARS = int(
        os.getenv("WIKIQUOTE_COMMENTARY_MAX_CHARS", 500)
    )
    WIKIQUOTE_COMMENTARY_MAX_TOKENS = int(
        os.getenv("WIKIQUOTE_COMMENTARY_MAX_TOKENS", 220)
    )
    WIKIQUOTE_PERSON_AI_FILTER = os.getenv("WIKIQUOTE_PERSON_AI_FILTER", "1") == "1"
    WIKIQUOTE_PERSON_FILTER_MAX_TOKENS = int(
        os.getenv("WIKIQUOTE_PERSON_FILTER_MAX_TOKENS", 8)
    )
    WIKIQUOTE_PERSON_FILTER_MAX_ATTEMPTS = int(
        os.getenv("WIKIQUOTE_PERSON_FILTER_MAX_ATTEMPTS", 12)
    )
    WIKIQUOTE_MANUAL_SEARCH_LIMIT = int(os.getenv("WIKIQUOTE_MANUAL_SEARCH_LIMIT", 8))
    WIKIQUOTE_MANUAL_PAGE_LIMIT = int(os.getenv("WIKIQUOTE_MANUAL_PAGE_LIMIT", 3))
    WIKIQUOTE_MANUAL_QUOTES_PER_PAGE = int(
        os.getenv("WIKIQUOTE_MANUAL_QUOTES_PER_PAGE", 8)
    )
    WIKIQUOTE_MANUAL_QUOTE_POOL_LIMIT = int(
        os.getenv("WIKIQUOTE_MANUAL_QUOTE_POOL_LIMIT", 24)
    )
    WIKIQUOTE_MANUAL_QUOTE_SELECT_MAX_TOKENS = int(
        os.getenv("WIKIQUOTE_MANUAL_QUOTE_SELECT_MAX_TOKENS", 120)
    )

    # TTS
    TTS_OUTPUT_MODE = os.getenv("TTS_OUTPUT_MODE", "speaker")
    TTS_OUTPUT_DIR = os.getenv("TTS_OUTPUT_DIR", "output/tts")
    TTS_SPEAKER = os.getenv("TTS_SPEAKER", "baya")
    TTS_SAMPLE_RATE = int(os.getenv("TTS_SAMPLE_RATE", "48000"))
    TTS_MAX_CONCURRENCY = int(os.getenv("TTS_MAX_CONCURRENCY", 1))
    TTS_QUEUE_MAX_SIZE = int(os.getenv("TTS_QUEUE_MAX_SIZE", 10))
    CHAT_TTS_QUEUE_MAX_SIZE = int(os.getenv("CHAT_TTS_QUEUE_MAX_SIZE", "40"))
    TTS_MAX_TEXT_LENGTH = int(os.getenv("TTS_MAX_TEXT_LENGTH", 0))
    TTS_CHUNK_MAX_LENGTH = int(os.getenv("TTS_CHUNK_MAX_LENGTH", 990))
    TTS_MAX_CHUNKS = int(os.getenv("TTS_MAX_CHUNKS", 3))
    TTS_CHUNK_PAUSE_SECONDS = float(os.getenv("TTS_CHUNK_PAUSE_SECONDS", 0.25))
    TTS_TIMEOUT_SECONDS = int(os.getenv("TTS_TIMEOUT_SECONDS", 45))
    TTS_TEMP_MAX_AGE_MINUTES = int(os.getenv("TTS_TEMP_MAX_AGE_MINUTES", 30))
    TTS_TEMP_MAX_SIZE_MB = int(os.getenv("TTS_TEMP_MAX_SIZE_MB", 300))

    STREAMER_POLL_INTERVAL = float(os.getenv("STREAMER_POLL_INTERVAL", "1.0"))

    # FFmpeg / stream (зарезервировано; RTMP пока не используется)
    STREAM_WIDTH = int(os.getenv("STREAM_WIDTH", 1280))
    STREAM_HEIGHT = int(os.getenv("STREAM_HEIGHT", 720))
    STREAM_FPS = int(os.getenv("STREAM_FPS", 20))
    STREAM_VIDEO_BITRATE = os.getenv("STREAM_VIDEO_BITRATE", "3000k")
    STREAM_AUDIO_BITRATE = os.getenv("STREAM_AUDIO_BITRATE", "128k")
    STREAM_X264_PRESET = os.getenv("STREAM_X264_PRESET", "ultrafast")

    # Visual (React + WebGL; OBS Browser Source)
    VISUAL_HOST = os.getenv("VISUAL_HOST", "127.0.0.1")
    VISUAL_PORT = int(os.getenv("VISUAL_PORT", 8765))
    VISUAL_URL = os.getenv(
        "VISUAL_URL",
        f"http://{os.getenv('VISUAL_HOST', '127.0.0.1')}:{int(os.getenv('VISUAL_PORT', 8765))}",
    )
    VISUAL_TARGET_FPS = int(os.getenv("VISUAL_TARGET_FPS", 30))
    VISUAL_COMPLEXITY = os.getenv("VISUAL_COMPLEXITY", "low")
    VISUAL_MODE = os.getenv("VISUAL_MODE", "demo").lower()
    VISUAL_PLAY_AUDIO = os.getenv("VISUAL_PLAY_AUDIO", "1") == "1"
    VISUAL_VOLUME_SMOOTHING = float(os.getenv("VISUAL_VOLUME_SMOOTHING", "0.18"))
    # Legacy (pygame; не используется React-визуалом)
    VISUAL_MAX_PARTICLES = int(os.getenv("VISUAL_MAX_PARTICLES", 500))
    VISUAL_WINDOW_TITLE = os.getenv("VISUAL_WINDOW_TITLE", "Infinity Fractal Avatar")
    VISUAL_MAX_PIXEL_RATIO = float(os.getenv("VISUAL_MAX_PIXEL_RATIO", "1.0"))

    # OBS WebSocket (OBS 28+: Tools → WebSocket Server Settings)
    OBS_ENABLED = os.getenv("OBS_ENABLED", "0") == "1"
    OBS_WEBSOCKET_HOST = os.getenv("OBS_WEBSOCKET_HOST", "127.0.0.1")
    OBS_WEBSOCKET_PORT = int(os.getenv("OBS_WEBSOCKET_PORT", 4455))
    OBS_WEBSOCKET_PASSWORD = os.getenv("OBS_WEBSOCKET_PASSWORD", "")
    OBS_HOTKEY_NAME = os.getenv("OBS_HOTKEY_NAME", "").strip()
    OBS_SCENE_NAME = os.getenv("OBS_SCENE_NAME", "").strip()
    OBS_SCENE_RETURN_TO = os.getenv("OBS_SCENE_RETURN_TO", "").strip()
    OBS_SIGNAL_DURATION = float(os.getenv("OBS_SIGNAL_DURATION", "2.5"))
    OBS_SIGNAL_COMMANDS = os.getenv(
        "OBS_SIGNAL_COMMANDS", "set_topic,start_stream,stop_stream"
    )
    OBS_AUTO_START_STREAM = os.getenv("OBS_AUTO_START_STREAM", "1") == "1"
    OBS_AUTO_STOP_STREAM = os.getenv("OBS_AUTO_STOP_STREAM", "1") == "1"

    # Supervisor
    LOCAL_SUPERVISOR_AUTO_START = os.getenv("LOCAL_SUPERVISOR_AUTO_START", "0") == "1"

    # Disk / logging
    MIN_FREE_DISK_GB = float(os.getenv("MIN_FREE_DISK_GB", 10))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # Health
    HEALTH_PORT = int(os.getenv("HEALTH_PORT", 8080))
    HEALTH_HOST = os.getenv("HEALTH_HOST", "0.0.0.0")

    HEARTBEAT_TIMEOUT_MINUTES = int(os.getenv("HEARTBEAT_TIMEOUT_MINUTES", 5))

    @classmethod
    def llm_provider(cls) -> str:
        if cls.LLM_PROVIDER in ("openrouter", "f5ai"):
            return cls.LLM_PROVIDER
        if cls.OPENROUTER_API_KEY and cls.OPENROUTER_MODEL:
            return "openrouter"
        return "f5ai"

    @classmethod
    def llm_api_url(cls) -> str:
        if cls.llm_provider() == "openrouter":
            if cls.OPENROUTER_API_URL.endswith("/chat/completions"):
                return cls.OPENROUTER_API_URL
            return f"{cls.OPENROUTER_API_URL}/chat/completions"
        return cls.F5AI_API_URL or ""

    @classmethod
    def llm_model(cls) -> str:
        if cls.llm_provider() == "openrouter":
            return cls.OPENROUTER_MODEL or ""
        return cls.F5AI_MODEL or ""

    @classmethod
    def llm_headers(cls) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if cls.llm_provider() == "openrouter":
            headers["Authorization"] = f"Bearer {cls.OPENROUTER_API_KEY}"
            if cls.OPENROUTER_HTTP_REFERER:
                headers["HTTP-Referer"] = cls.OPENROUTER_HTTP_REFERER
            if cls.OPENROUTER_APP_TITLE:
                headers["X-Title"] = cls.OPENROUTER_APP_TITLE
        else:
            headers["X-Auth-Token"] = cls.F5AI_API_TOKEN or ""
        return headers

    @classmethod
    def obs_signal_commands(cls) -> frozenset[str]:
        raw = cls.OBS_SIGNAL_COMMANDS.strip()
        if raw == "*":
            return frozenset({"*"})
        parts = {p.strip().lower().lstrip("/") for p in raw.split(",") if p.strip()}
        return frozenset(parts) if parts else frozenset({"set_topic", "start_stream"})

    @classmethod
    def apply_resource_profile(cls) -> None:
        """Подстраивает параметры под профиль low/normal."""
        if cls.RESOURCE_PROFILE != "low":
            return

        cls.STREAM_WIDTH = int(os.getenv("STREAM_WIDTH", 1280))
        cls.STREAM_HEIGHT = int(os.getenv("STREAM_HEIGHT", 720))
        cls.STREAM_FPS = int(os.getenv("STREAM_FPS", 15))
        cls.STREAM_VIDEO_BITRATE = os.getenv("STREAM_VIDEO_BITRATE", "2500k")
        cls.STREAM_X264_PRESET = os.getenv("STREAM_X264_PRESET", "ultrafast")
        cls.TTS_MAX_CONCURRENCY = int(os.getenv("TTS_MAX_CONCURRENCY", 1))
        cls.TTS_QUEUE_MAX_SIZE = min(cls.TTS_QUEUE_MAX_SIZE, int(os.getenv("TTS_QUEUE_MAX_SIZE", 6)))
        cls.AI_QUEUE_MAX_SIZE = min(cls.AI_QUEUE_MAX_SIZE, int(os.getenv("AI_QUEUE_MAX_SIZE", 10)))
        cls.VISUAL_MAX_PARTICLES = min(cls.VISUAL_MAX_PARTICLES, int(os.getenv("VISUAL_MAX_PARTICLES", 150)))
        cls.VISUAL_COMPLEXITY = os.getenv("VISUAL_COMPLEXITY", "low")


Config.apply_resource_profile()


def validate_config():
    """Проверяет наличие обязательных переменных окружения."""
    required_vars = [
        "TWITCH_CHANNEL",
        "TWITCH_CLIENT_ID",
        "TWITCH_CLIENT_SECRET",
    ]

    provider = Config.llm_provider()
    if provider == "openrouter":
        required_vars.extend(["OPENROUTER_API_KEY", "OPENROUTER_MODEL"])
    else:
        required_vars.extend(["F5AI_API_TOKEN", "F5AI_API_URL", "F5AI_MODEL"])

    missing = []
    for var in required_vars:
        if not getattr(Config, var):
            missing.append(var)

    if missing:
        raise ValueError(
            f"Отсутствуют обязательные переменные окружения: {', '.join(missing)}"
        )


validate_config()
