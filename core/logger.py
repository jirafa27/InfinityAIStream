import logging
import os
import sys


class Logger:
    """
    Класс для централизованной настройки единого логгера приложения.
    """
    _logger = None
    DEFAULT_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()    
    DEFAULT_LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
    
    @classmethod
    def get_logger(cls):
        """
        Получение глобального логгера.
        
        Returns:
            logging.Logger: Настроенный объект логгера
        """
        if cls._logger is not None:
            return cls._logger
        
        logger = logging.getLogger('app')
        
        log_level = cls.DEFAULT_LOG_LEVEL
        
        if isinstance(log_level, str):
            numeric_level = getattr(logging, log_level)
            logger.setLevel(numeric_level)
        else:
            logger.setLevel(log_level)
        
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        formatter = logging.Formatter(cls.DEFAULT_LOG_FORMAT)
        
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        cls._logger = logger
        return logger
    
    @classmethod
    def set_level(cls, level):
        """
        Устанавливает указанный уровень логирования.
        
        Args:
            level: Уровень логирования (строка или константа logging)
        """
        logger = cls.get_logger()
        
        if isinstance(level, str):
            numeric_level = getattr(logging, level.upper())
        else:
            numeric_level = level
            
        logger.setLevel(numeric_level)
    
    @classmethod
    def add_file_handler(cls, file_path, format_str=None):
        """
        Добавляет файловый хендлер к логгеру.
        
        Args:
            file_path (str): Путь к файлу для записи логов
            format_str (str, optional): Формат сообщений лога
        """
        logger = cls.get_logger()
        formatter = logging.Formatter(format_str or cls.DEFAULT_LOG_FORMAT)
        has_handler = any(
            isinstance(h, logging.FileHandler) and h.baseFilename == os.path.abspath(file_path)
            for h in logger.handlers
        )
        if not has_handler:
            file_handler = logging.FileHandler(file_path, encoding='utf-8')
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)


logger = Logger.get_logger()