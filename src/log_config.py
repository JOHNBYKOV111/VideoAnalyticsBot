import logging
import os
import sys
import re
from logging.handlers import RotatingFileHandler

os.makedirs("logs", exist_ok=True)

# Откладываем чтение DEBUG до setup_logging (вызывается после load_dotenv!)
DEBUG = False

def _remove_emojis(text: str) -> str:
    """Удаляет только эмодзи, сохраняя кириллицу и ASCII"""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002702-\U000027B0"  # other
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE,
    )
    return emoji_pattern.sub(r'', text)

class SafeStreamHandler(logging.StreamHandler):
    """Handler, безопасный для любой кодировки терминала"""
    def __init__(self, stream=None):
        super().__init__(stream)
        self._is_utf8 = (getattr(stream, 'encoding', None) or 'utf-8').lower() in ('utf-8', 'utf8')
    
    def emit(self, record):
        try:
            msg = self.format(record)
            if not self._is_utf8:
                msg = _remove_emojis(msg)
            stream = self.stream
            stream.write(msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)

def setup_logging():
    global DEBUG
    DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)
    root_logger.handlers.clear()

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Создаём handler с текущим sys.stdout (без замены!)
    console_handler = SafeStreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if DEBUG else logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if not DEBUG:
        file_handler = RotatingFileHandler(
            'logs/bot.log',
            maxBytes=10*1024*1024,
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    init_msg = f"🚀 Logger initialized | DEBUG={DEBUG} | File logging={'ON' if not DEBUG else 'OFF'}"
    root_logger.info(init_msg)
    return root_logger

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

def log_startup_info(app_name: str = "Application"):
    """
    Записать информацию о запуске приложения
    """
    startup_symbol = "[START]" if sys.platform == "win32" else "🚀"
    root_logger = logging.getLogger()
    root_logger.info(f"{startup_symbol} {app_name} startup")
    root_logger.info(f"Platform: {sys.platform}")
    root_logger.info(f"Python version: {sys.version.split()[0]}")
    # Получаем DEBUG из окружения (на случай, если setup_logging уже вызван)
    debug_mode = os.getenv('DEBUG', 'false').lower() == 'true'
    root_logger.info(f"DEBUG mode: {debug_mode}")

def log_shutdown_info(app_name: str = "Application"):
    """
    Записать информацию о завершении приложения
    """
    shutdown_symbol = "[END]" if sys.platform == "win32" else "👋"
    root_logger = logging.getLogger()
    root_logger.info(f"{shutdown_symbol} {app_name} shutdown")