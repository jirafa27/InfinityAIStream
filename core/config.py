import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Конфигурация приложения"""
    
    # Twitch настройки
    TWITCH_CHANNEL = os.getenv('TWITCH_CHANNEL')
    TWITCH_CLIENT_ID = os.getenv('TWITCH_CLIENT_ID')
    TWITCH_CLIENT_SECRET = os.getenv('TWITCH_CLIENT_SECRET')
    
    # Redis настройки
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_DB = int(os.getenv('REDIS_DB', 0))
    
    # LLM настройки
    F5AI_MODEL = os.getenv('F5AI_MODEL')
    F5AI_API_URL = os.getenv('F5AI_API_URL')
    F5AI_API_TOKEN = os.getenv('F5AI_API_TOKEN')
    
    # Константы
    HEARTBEAT_TIMEOUT_MINUTES = int(os.getenv('HEARTBEAT_TIMEOUT_MINUTES', 5))


def validate_config():
    """Проверяет наличие обязательных переменных окружения"""
    required_vars = [
        'TWITCH_CHANNEL',
        'TWITCH_CLIENT_ID', 
        'TWITCH_CLIENT_SECRET',
        'F5AI_API_TOKEN',
        'F5AI_API_URL',
        'F5AI_MODEL'
    ]
    
    missing = []
    for var in required_vars:
        if not getattr(Config, var):
            missing.append(var)
    
    if missing:
        raise ValueError(f"Отсутствуют обязательные переменные окружения: {', '.join(missing)}")


# Валидируем конфигурацию при импорте
validate_config()

