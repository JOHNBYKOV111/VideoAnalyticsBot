import os
from dotenv import load_dotenv

load_dotenv()

# 🔥 Telegram Bot
BOT_TOKEN = os.getenv('BOT_TOKEN')

# 🔥 GigaChat API
GIGACHAT_CLIENT_ID = os.getenv('GIGACHAT_CLIENT_ID')
GIGACHAT_CLIENT_SECRET = os.getenv('GIGACHAT_CLIENT_SECRET')
GIGACHAT_AVAILABLE = bool(GIGACHAT_CLIENT_ID and GIGACHAT_CLIENT_SECRET)

# 🔥 PostgreSQL
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5432))
POSTGRES_DB = os.getenv('POSTGRES_DB', 'video_stats')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', '')

# 🔥 DB_CONFIG (для database_manager.py)
DB_CONFIG = {
    'host': POSTGRES_HOST,
    'port': POSTGRES_PORT,
    'database': POSTGRES_DB,
    'user': POSTGRES_USER,
    'password': POSTGRES_PASSWORD
}

# 🔥 DEBUG (критично для log_config.py!)
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'

# 🔥 Логирование (дополнительно)
LOG_LEVEL = 'DEBUG' if DEBUG else 'INFO'
LOG_DIR = 'logs'

# 🔥 Проверка конфигурации (при запуске)
print(f"🚀 Config loaded:")
print(f"   Bot token: {'✅' if BOT_TOKEN else '❌'}")
print(f"   GigaChat: {'✅' if GIGACHAT_AVAILABLE else '❌'}")
print(f"   PostgreSQL: {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
print(f"   DEBUG mode: {DEBUG}")
