import asyncio
import os
import sys
from datetime import datetime
from typing import Optional, Dict, Any, List

# ========== КРИТИЧЕСКИЙ ФИКС ДЛЯ ОТНОСИТЕЛЬНЫХ ИМПОРТОВ ==========
# Принудительно устанавливаем пакет для относительных импортов
__package__ = "src"

# Добавляем родительскую директорию в sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
# ================================================================

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import BotCommand
from dotenv import load_dotenv
import logging
import importlib

# Загружаем переменные окружения
load_dotenv()

# Инициализация логирования ДО любых других импортов из проекта
from .log_config import setup_logging, log_startup_info, log_shutdown_info

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)

# ========== КОНСТАНТЫ КОМАНД ==========
# Вынесено в отдельный модуль для удобства поддержки
BOT_COMMANDS: List[Dict[str, str]] = [
    # Базовые команды
    {"command": "start", "description": "Начало работы"},
    {"command": "help", "description": "Помощь по базовым командам"},
    {"command": "stats", "description": "Полная базовая статистика"},
    # Команды AI
    {"command": "aispravka", "description": "AI справка"},
    {"command": "analiz", "description": "Анализ креатора по ID"},
    {"command": "top3", "description": "Топ-3 по метрике"},
    {"command": "extremes", "description": "Мин/макс значения"},
    {"command": "analizvideo", "description": "Видео по просмотрам"},
    # Команды DateAI
    {"command": "today", "description": "Статистика за сегодня"},
    {"command": "yesterday", "description": "Статистика за вчера"},
    {"command": "week", "description": "Статистика за неделю"},
    {"command": "month", "description": "Статистика за месяц"},
    {"command": "custom", "description": "Кастомный период"},
    {"command": "creators", "description": "Список креаторов"},
    {"command": "creator", "description": "Статистика по креатору"},
    {"command": "ask", "description": "Задать вопрос AI"},
    {"command": "system", "description": "Системная информация"},
]

# ========== КОНФИГУРАЦИЯ ==========
# Глобальные переменные будут
BOT_TOKEN: Optional[str] = None
TARGET_YEAR: int = datetime.now().year  # Значение по умолчанию
DB_CONFIG: Dict[str, Any] = {}

# ========== ОСНОВНОЙ КЛАСС ПРИЛОЖЕНИЯ ==========
class TelegramBotApp:
    def __init__(self):
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self.db_manager = None
        self.ai_manager = None
        self.date_ai_manager = None
        self.is_initialized = False
        self.is_polling = False
        
    def _load_configuration(self) -> None:
        """Загрузка конфигурации из переменных окружения"""
        global BOT_TOKEN, TARGET_YEAR, DB_CONFIG
        
        # Загрузка BOT_TOKEN
        BOT_TOKEN = os.getenv("BOT_TOKEN")
        
        # Загрузка TARGET_YEAR с обработкой ошибок
        target_year_str = os.getenv("TARGET_YEAR")
        if target_year_str:
            try:
                TARGET_YEAR = int(target_year_str)
                if TARGET_YEAR < 2020 or TARGET_YEAR > 2100:
                    raise ValueError(f"Некорректный целевой год: {TARGET_YEAR}")
            except ValueError as e:
                logger.warning(f"⚠️ Некорректное значение TARGET_YEAR: {e}")
                logger.warning(f"⚠️ Используется текущий год: {datetime.now().year}")
                TARGET_YEAR = datetime.now().year
        else:
            TARGET_YEAR = datetime.now().year
        
        # Загрузка конфигурации базы данных
        DB_CONFIG = {
            'host': os.getenv("DB_HOST", "localhost"),
            'port': int(os.getenv("DB_PORT", "5432")),
            'database': os.getenv("DB_NAME", "your_database"),
            'user': os.getenv("DB_USER", "your_user"),
            'password': os.getenv("DB_PASSWORD", "your_password")
        }
    
    async def _validate_configuration(self) -> None:
        """Проверка корректности конфигурации"""
        logger.info("🔍 Проверка конфигурации...")
        
        # Проверка обязательных переменных окружения
        required_vars = ["BOT_TOKEN"]
        missing_vars = []
        
        for var in required_vars:
            value = os.getenv(var)
            if not value or value.strip() == "":
                missing_vars.append(var)
        
        if missing_vars:
            raise ValueError(f"❌ Отсутствуют обязательные переменные окружения: {', '.join(missing_vars)}")
        
        # Проверка BOT_TOKEN
        if not BOT_TOKEN or BOT_TOKEN.strip() == "":
            raise ValueError("❌ BOT_TOKEN не может быть пустым")
        
        # Проверка формата BOT_TOKEN (базовая проверка)
        if ":" not in BOT_TOKEN:
            logger.warning("⚠️ BOT_TOKEN может иметь неверный формат")
        
        # Логирование конфигурации (без паролей)
        safe_config = DB_CONFIG.copy()
        safe_config['password'] = '***' if DB_CONFIG['password'] and DB_CONFIG['password'] != "your_password" else 'не задан'
        
        logger.info(f"📋 Конфигурация БД: {safe_config}")
        logger.info(f"🎯 Целевой год: {TARGET_YEAR}")
        
        # Предупреждение о целевом годе
        current_year = datetime.now().year
        if TARGET_YEAR != current_year:
            logger.warning(f"⚠️ Целевой год ({TARGET_YEAR}) отличается от текущего ({current_year})")
        
        # Проверка наличия .env файла
        if not os.path.exists('.env'):
            logger.warning("⚠️ Файл .env не найден. Используются значения по умолчанию.")
    
    async def _initialize_managers(self) -> None:
        """Инициализация менеджеров"""
        try:
            # Отложенный импорт для избежания циклических зависимостей
            from .managers.database_manager import VideoDatabaseManager
            from .managers.ai_manager import AIManager
            from .managers.date_ai_manager import DateAIManager
            
            logger.info("🔄 Инициализация менеджеров...")
            
            # Формирование строки подключения к БД
            db_url = (
                f"postgresql://{DB_CONFIG['user']}:"
                f"{DB_CONFIG['password']}@"
                f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
            )
            
            # Логирование безопасного URL (без пароля)
            safe_db_url = (
                f"postgresql://{DB_CONFIG['user']}:***@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
            )
            logger.info(f"📡 URL подключения к БД: {safe_db_url}")
            
            # Инициализация Database Manager
            self.db_manager = VideoDatabaseManager(db_url=db_url, cache_ttl=300)
            
            # Проверка подключения к БД
            db_connected = await self.db_manager.connect()
            if not db_connected:
                logger.error("❌ Не удалось подключиться к базе данных")
                raise ConnectionError("Не удалось установить соединение с базой данных")
            
            # Проверка доступности таблиц
            if not await self.db_manager.test_connection(check_tables=True):
                logger.warning("⚠️ Некоторые таблицы могут отсутствовать в базе данных")
            
            logger.info("✅ DatabaseManager инициализирован")
            
            # Инициализация AI Manager
            self.ai_manager = AIManager(db_url=db_url)
            
            # Проверка доступности AI сервиса (если метод существует)
            if hasattr(self.ai_manager, 'health_check'):
                try:
                    await self.ai_manager.health_check()
                    logger.info("✅ AIManager проверка пройдена")
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка при проверке AIManager: {e}")
            
            logger.info("✅ AIManager инициализирован")
            
            # Инициализация DateAI Manager
            gigachat_secret = os.getenv("GIGACHAT_SECRET")
            self.date_ai_manager = DateAIManager(
                db_config=DB_CONFIG,
                gigachat_secret=gigachat_secret
            )
            
            # Проверка инициализации DateAI Manager
            if hasattr(self.date_ai_manager, 'initialize'):
                try:
                    await self.date_ai_manager.initialize()
                    logger.info("✅ DateAIManager инициализирован")
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка при инициализации DateAIManager: {e}")
            
            logger.info("✅ DateAIManager инициализирован")
            
        except ImportError as e:
            logger.error(f"❌ Ошибка импорта модулей менеджеров: {e}")
            logger.error("Проверьте наличие файлов managers/database_manager.py, managers/ai_manager.py и managers/date_ai_manager.py")
            raise
        except KeyError as e:
            logger.error(f"❌ Отсутствует ключ в конфигурации БД: {e}")
            logger.error("Проверьте корректность DB_CONFIG в файле .env")
            raise
        except ConnectionError as e:
            logger.error(f"❌ Ошибка подключения к базе данных: {e}")
            logger.error("Проверьте параметры подключения в файле .env")
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка при инициализации менеджеров: {e}")
            raise
    
    async def _initialize_handlers(self) -> None:
        """Инициализация обработчиков"""
        try:
            logger.info("🔄 Регистрация обработчиков...")
            
            # Создаем список для отслеживания загруженных обработчиков
            loaded_handlers = []
            
            # === Подключаем AI роутер ===
            ai_handler_sources = [
                (".handlers.ai_handlers", "router"),
            ]
            
            ai_router = None
            for module_path, router_name in ai_handler_sources:
                try:
                    module = importlib.import_module(module_path, package="src")
                    ai_router = getattr(module, router_name, None)
                    if ai_router:
                        logger.info(f"✅ Найден AI роутер в {module_path}")
                        break
                except ImportError:
                    continue
            
            if ai_router:
                self.dp.include_router(ai_router)
                loaded_handlers.append("ai_handlers")
                logger.info("✅ AI роутер подключен (до base_handlers)")
            else:
                logger.warning("⚠️ AI роутер не найден")
            
            # === Подключаем базовые обработчики ===
            handler_sources = [
                (".handlers.base_handlers", "router"),
            ]
            
            base_router = None
            for module_path, router_name in handler_sources:
                try:
                    module = importlib.import_module(module_path, package="src")
                    base_router = getattr(module, router_name, None)
                    if base_router:
                        logger.info(f"✅ Найден базовый роутер в {module_path}")
                        break
                except ImportError:
                    continue
            
            if not base_router:
                raise ImportError("Не удалось найти базовые обработчики")
            
            self.dp.include_router(base_router)
            loaded_handlers.append("base_handlers")
            logger.info("✅ Базовый роутер подключен (после ai_handlers)")
            
            # === Подключаем DateAI обработчики ===
            try:
                from .handlers.date_ai_handlers import create_date_ai_handlers
                date_ai_handlers_obj = await create_date_ai_handlers(self.date_ai_manager)
                if date_ai_handlers_obj:
                    self.dp.include_router(date_ai_handlers_obj.get_router())
                    loaded_handlers.append("date_ai_handlers")
                    logger.info("✅ DateAI обработчики зарегистрированы")
                else:
                    logger.warning("⚠️ DateAI обработчики не инициализированы")
            except ImportError as e:
                logger.warning(f"⚠️ Не удалось загрузить DateAI обработчики: {e}")
            
            logger.info(f"✅ Загружено обработчиков: {len(loaded_handlers)} ({', '.join(loaded_handlers)})")
                
        except Exception as e:
            logger.error(f"❌ Ошибка при регистрации обработчиков: {e}")
            raise
    
    async def _setup_bot_commands(self) -> None:
        """Настройка команд бота"""
        try:
            bot_commands = [BotCommand(**cmd) for cmd in BOT_COMMANDS]
            await self.bot.set_my_commands(bot_commands)
            logger.info(f"✅ Установлено {len(bot_commands)} команд бота")
            
            # Логирование команд для отладки
            if logger.isEnabledFor(10):
                for cmd in bot_commands:
                    logger.debug(f"  /{cmd.command} - {cmd.description}")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка при установке команд бота: {e}")
            # Не прерываем запуск, так как команды - не критичная функциональность
    
    async def setup(self) -> None:
        """Инициализация бота и диспетчера"""
        try:
            log_startup_info()
            logger.info("=" * 50)
            
            # Загрузка конфигурации
            self._load_configuration()
            
            # Проверка конфигурации
            await self._validate_configuration()
            
            # Создание бота
            session = AiohttpSession()
            self.bot = Bot(
                token=BOT_TOKEN,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
                session=session
            )
            logger.info("✅ Бот создан")
            
            # Создание диспетчера с памятью для FSM
            storage = MemoryStorage()
            self.dp = Dispatcher(storage=storage)
            logger.info("✅ Диспетчер создан")
            
            # Инициализация менедежеров
            await self._initialize_managers()
            
            # Инициализация обработчиков
            await self._initialize_handlers()
            
            # Настройка команд бота
            await self._setup_bot_commands()
            
            self.is_initialized = True
            logger.info("=" * 50)
            logger.info("✅ Приложение успешно инициализировано!")
            logger.info("=" * 50)
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при инициализации: {e}")
            await self.shutdown()
            raise
    
    async def run(self) -> None:
        """Запуск поллинга"""
        if not self.is_initialized:
            logger.error("❌ Приложение не инициализировано!")
            return
        
        logger.info("🚀 Запуск бота...")
        logger.info(f"🎯 Целевой год: {TARGET_YEAR}")
        logger.info("=" * 50)
        
        try:
            self.is_polling = True
            await self.dp.start_polling(
                self.bot, 
                allowed_updates=self.dp.resolve_used_update_types(),
                polling_timeout=30,
                close_bot_session_on_shutdown=False
            )
        except KeyboardInterrupt:
            logger.info("⚠️ Получен сигнал остановки (Ctrl+C)")
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при поллинге: {e}")
        finally:
            self.is_polling = False
            logger.info("🛑 Поллинг остановлен")
    
    async def shutdown(self) -> None:
        """Очистка ресурсов при завершении в обратном порядке инициализации"""
        logger.info("🔧 Завершение работы приложения...")
        
        # 1. Остановка поллинга (если он запущен)
        if self.is_polling and self.dp:
            try:
                await self.dp.stop_polling()
                logger.info("✅ Поллинг остановлен явно")
            except Exception as e:
                logger.error(f"❌ Ошибка при остановке поллинга: {e}")
        
        # 2. Закрытие DateAI менеджера
        if self.date_ai_manager and hasattr(self.date_ai_manager, 'close'):
            try:
                await self.date_ai_manager.close()
                logger.info("✅ DateAI менеджер закрыт")
            except Exception as e:
                logger.error(f"❌ Ошибка при закрытии DateAI менеджера: {e}")
        elif self.date_ai_manager:
            logger.info("ℹ️ DateAIManager не требует явного закрытия")
        
        # 3. Закрытие AI менеджера
        if self.ai_manager and hasattr(self.ai_manager, 'close'):
            try:
                await self.ai_manager.close()
                logger.info("✅ AI менеджер закрыт")
            except Exception as e:
                logger.error(f"❌ Ошибка при закрытии AI менеджера: {e}")
        elif self.ai_manager:
            logger.info("ℹ️ AIManager не требует явного закрытия")
        
        # 4. Закрытие Database менеджера
        if self.db_manager and hasattr(self.db_manager, 'close'):
            try:
                await self.db_manager.close()
                logger.info("✅ Database менеджер закрыт")
            except Exception as e:
                logger.error(f"❌ Ошибка при закрытии Database менеджера: {e}")
        
        # 5. Закрытие сессии бота (самый низкий уровень)
        if self.bot and hasattr(self.bot, 'session'):
            try:
                await self.bot.session.close()
                logger.info("✅ Сессия бота закрыта")
            except Exception as e:
                logger.error(f"❌ Ошибка при закрытии сессии бота: {e}")
        
        log_shutdown_info()
        logger.info("🔒 Ресурсы освобождены")
        logger.info("=" * 50)

# ========== ТОЧКА ВХОДА ==========
async def main() -> None:
    """Основная функция запуска"""
    # Настройка логирования ДО создания приложения
    setup_logging()
    
    app = TelegramBotApp()
    
    try:
        await app.setup()
        await app.run()
    except KeyboardInterrupt:
        logger.info("👋 Принудительная остановка пользователем")
    except ValueError as e:
        logger.error(f"❌ Ошибка конфигурации: {e}")
        logger.error("Проверьте файл .env и обязательные переменные окружения")
        sys.exit(1)
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await app.shutdown()

if __name__ == "__main__":
    # Запуск асинхронного приложения
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Приложение остановлено")
    except Exception as e:
        print(f"💥 Необработанная ошибка: {e}")
        sys.exit(1)