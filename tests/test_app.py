import pytest
import asyncio
import os
import sys
from unittest.mock import Mock, AsyncMock, patch, MagicMock, call
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import BotCommand
import importlib

# Добавляем корень проекта в sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# ========== FIXTURES ==========

@pytest.fixture
def app():
    """Экземпляр TelegramBotApp"""
    from src.app import TelegramBotApp
    return TelegramBotApp()

@pytest.fixture
def mock_env():
    """Фикстура для мока переменных окружения"""
    with patch.dict(os.environ, {
        'BOT_TOKEN': '1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ',
        'TARGET_YEAR': '2023',
        'DB_HOST': 'localhost',
        'DB_PORT': '5432',
        'DB_NAME': 'test_db',
        'DB_USER': 'test_user',
        'DB_PASSWORD': 'test_password',
        'GIGACHAT_SECRET': 'test_gigachat_secret'
    }):
        yield

@pytest.fixture
def mock_empty_env():
    """Фикстура для пустого окружения"""
    with patch.dict(os.environ, {}, clear=True):
        yield

@pytest.fixture
def mock_logger():
    """Мок логгера"""
    with patch('src.app.logger') as mock_logger:
        mock_logger.info = Mock()
        mock_logger.error = Mock()
        mock_logger.warning = Mock()
        mock_logger.debug = Mock()
        mock_logger.isEnabledFor = Mock(return_value=False)
        yield mock_logger

# ========== BASIC TESTS ==========

def test_app_initialization(app):
    """Тест инициализации приложения"""
    assert app.bot is None
    assert app.dp is None
    assert app.db_manager is None
    assert app.ai_manager is None
    assert app.date_ai_manager is None
    assert app.is_initialized is False
    assert app.is_polling is False

# ========== CONFIGURATION TESTS ==========

def test_load_configuration_success(app, mock_env, mock_logger):
    """Тест успешной загрузки конфигурации"""
    app._load_configuration()
    
    # Проверяем глобальные переменные
    from src.app import BOT_TOKEN, TARGET_YEAR, DB_CONFIG
    
    assert BOT_TOKEN == '1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    assert TARGET_YEAR == 2023
    assert DB_CONFIG == {
        'host': 'localhost',
        'port': 5432,
        'database': 'test_db',
        'user': 'test_user',
        'password': 'test_password'
    }

def test_load_configuration_empty_env(app, mock_empty_env, mock_logger):
    """Тест загрузки конфигурации с пустым окружением"""
    app._load_configuration()
    
    from src.app import BOT_TOKEN, TARGET_YEAR, DB_CONFIG
    current_year = datetime.now().year
    
    assert BOT_TOKEN is None
    assert TARGET_YEAR == current_year
    assert DB_CONFIG['host'] == 'localhost'

@pytest.mark.asyncio
async def test_validate_configuration_success(app, mock_env, mock_logger):
    """Тест успешной валидации конфигурации"""
    app._load_configuration()
    await app._validate_configuration()
    
    # Не должно быть исключений
    assert True

@pytest.mark.asyncio
async def test_validate_configuration_missing_token(app, mock_empty_env, mock_logger):
    """Тест валидации конфигурации с отсутствующим токеном"""
    with pytest.raises(ValueError, match="❌ Отсутствуют обязательные переменные окружения: BOT_TOKEN"):
        await app._validate_configuration()

# ========== MANAGERS TESTS ==========

@pytest.mark.asyncio
async def test_initialize_managers_success(app, mock_env, mock_logger):
    """Тест успешной инициализации менеджеров"""
    app._load_configuration()
    
    # Создаем моки менеджеров
    mock_db_manager = AsyncMock()
    mock_db_manager.connect = AsyncMock(return_value=True)
    mock_db_manager.test_connection = AsyncMock(return_value=True)
    
    mock_ai_manager = AsyncMock()
    mock_ai_manager.health_check = AsyncMock()
    
    mock_date_ai_manager = AsyncMock()
    mock_date_ai_manager.initialize = AsyncMock()
    
    # Мокаем импорты менеджеров по полному пути модуля
    with patch('src.managers.database_manager.VideoDatabaseManager', return_value=mock_db_manager), \
         patch('src.managers.ai_manager.AIManager', return_value=mock_ai_manager), \
         patch('src.managers.date_ai_manager.DateAIManager', return_value=mock_date_ai_manager):
        
        await app._initialize_managers()
    
    assert app.db_manager is not None
    assert app.ai_manager is not None
    assert app.date_ai_manager is not None
    
    mock_db_manager.connect.assert_called_once()
    mock_ai_manager.health_check.assert_called_once()
    mock_date_ai_manager.initialize.assert_called_once()

@pytest.mark.asyncio
async def test_initialize_managers_db_connection_failed(app, mock_env, mock_logger):
    """Тест инициализации менеджеров с ошибкой подключения к БД"""
    app._load_configuration()
    
    # Создаем мок менеджера БД который не может подключиться
    mock_db_manager = AsyncMock()
    mock_db_manager.connect = AsyncMock(return_value=False)
    
    # Мокаем импорт
    with patch('src.managers.database_manager.VideoDatabaseManager', return_value=mock_db_manager):
        with pytest.raises(ConnectionError, match="Не удалось установить соединение с базой данных"):
            await app._initialize_managers()

@pytest.mark.asyncio
async def test_initialize_managers_db_test_failed(app, mock_env, mock_logger):
    """Тест инициализации менеджеров с ошибкой проверки таблиц"""
    app._load_configuration()
    
    # Создаем моки
    mock_db_manager = AsyncMock()
    mock_db_manager.connect = AsyncMock(return_value=True)
    mock_db_manager.test_connection = AsyncMock(return_value=False)
    
    mock_ai_manager = AsyncMock()
    mock_date_ai_manager = AsyncMock()
    
    with patch('src.managers.database_manager.VideoDatabaseManager', return_value=mock_db_manager), \
         patch('src.managers.ai_manager.AIManager', return_value=mock_ai_manager), \
         patch('src.managers.date_ai_manager.DateAIManager', return_value=mock_date_ai_manager):
        
        await app._initialize_managers()
    
    # Должен продолжить работу с предупреждением
    assert app.db_manager is not None

@pytest.mark.asyncio
async def test_initialize_managers_ai_health_check_failed(app, mock_env, mock_logger):
    """Тест инициализации менеджеров с ошибкой проверки AI"""
    app._load_configuration()
    
    # Создаем моки
    mock_db_manager = AsyncMock()
    mock_db_manager.connect = AsyncMock(return_value=True)
    mock_db_manager.test_connection = AsyncMock(return_value=True)
    
    mock_ai_manager = AsyncMock()
    mock_ai_manager.health_check = AsyncMock(side_effect=Exception("AI недоступен"))
    
    mock_date_ai_manager = AsyncMock()
    
    with patch('src.managers.database_manager.VideoDatabaseManager', return_value=mock_db_manager), \
         patch('src.managers.ai_manager.AIManager', return_value=mock_ai_manager), \
         patch('src.managers.date_ai_manager.DateAIManager', return_value=mock_date_ai_manager):
        
        await app._initialize_managers()
    
    # Должен продолжить работу с предупреждением
    assert app.ai_manager is not None

@pytest.mark.asyncio
async def test_initialize_managers_date_ai_init_failed(app, mock_env, mock_logger):
    """Тест инициализации менеджеров с ошибкой инициализации DateAI"""
    app._load_configuration()
    
    # Создаем моки
    mock_db_manager = AsyncMock()
    mock_db_manager.connect = AsyncMock(return_value=True)
    mock_db_manager.test_connection = AsyncMock(return_value=True)
    
    mock_ai_manager = AsyncMock()
    
    mock_date_ai_manager = AsyncMock()
    mock_date_ai_manager.initialize = AsyncMock(side_effect=Exception("DateAI ошибка"))
    
    with patch('src.managers.database_manager.VideoDatabaseManager', return_value=mock_db_manager), \
         patch('src.managers.ai_manager.AIManager', return_value=mock_ai_manager), \
         patch('src.managers.date_ai_manager.DateAIManager', return_value=mock_date_ai_manager):
        
        await app._initialize_managers()
    
    # Должен продолжить работу с предупреждением
    assert app.date_ai_manager is not None

# ========== HANDLERS TESTS ==========

@pytest.mark.asyncio
async def test_initialize_handlers_success(app, mock_logger):
    """Тест успешной инициализации обработчиков"""
    # Создаем мок диспетчера и менеджера
    mock_dp = Mock()
    mock_dp.include_router = Mock()
    app.dp = mock_dp
    app.date_ai_manager = Mock()
    
    # Мокаем импорт модулей обработчиков
    mock_ai_module = MagicMock()
    mock_ai_module.router = Mock()
    
    mock_base_module = MagicMock()
    mock_base_module.router = Mock()
    
    # Конфигурируем side_effect для корректной работы import_module
    def import_module_side_effect(module_path, package=None):
        if 'ai_handlers' in module_path:
            return mock_ai_module
        elif 'base_handlers' in module_path:
            return mock_base_module
        else:
            raise ImportError(f"Module not found: {module_path}")
    
    # Мокаем DateAI обработчики
    mock_date_ai_handlers_obj = Mock()
    mock_date_ai_handlers_obj.get_router = Mock(return_value=Mock())
    
    with patch('src.app.importlib.import_module', side_effect=import_module_side_effect), \
         patch('src.handlers.date_ai_handlers.create_date_ai_handlers', AsyncMock(return_value=mock_date_ai_handlers_obj)):
        
        await app._initialize_handlers()
    
    # Проверяем регистрацию роутеров
    assert mock_dp.include_router.call_count >= 2

@pytest.mark.asyncio
async def test_initialize_handlers_base_router_not_found(app, mock_logger):
    """Тест инициализации обработчиков, когда базовый роутер не найден"""
    # Создаем мок диспетчера
    mock_dp = Mock()
    mock_dp.include_router = Mock()
    app.dp = mock_dp
    app.date_ai_manager = Mock()
    
    # Настроим mock чтобы вызывал ImportError
    with patch('src.app.importlib.import_module', side_effect=ImportError("Module not found")):
        with pytest.raises(ImportError, match="Не удалось найти базовые обработчики"):
            await app._initialize_handlers()

@pytest.mark.asyncio
async def test_initialize_handlers_date_ai_import_error(app, mock_logger):
    """Тест инициализации обработчиков с ошибкой импорта DateAI"""
    # Создаем мок диспетчера
    mock_dp = Mock()
    mock_dp.include_router = Mock()
    app.dp = mock_dp
    app.date_ai_manager = Mock()
    
    # Мокаем базовые и AI обработчики
    mock_ai_module = MagicMock()
    mock_ai_module.router = Mock()
    
    mock_base_module = MagicMock()
    mock_base_module.router = Mock()
    
    def import_module_side_effect(module_path, package=None):
        if 'ai_handlers' in module_path:
            return mock_ai_module
        elif 'base_handlers' in module_path:
            return mock_base_module
        else:
            raise ImportError(f"Module not found: {module_path}")
    
    with patch('src.app.importlib.import_module', side_effect=import_module_side_effect):
        # Мокаем импорт DateAI обработчиков с ошибкой
        with patch('src.handlers.date_ai_handlers.create_date_ai_handlers', side_effect=ImportError("Модуль не найден")):
            await app._initialize_handlers()
    
    # Должно быть предупреждение, но не ошибка
    assert True

# ========== BOT COMMANDS TESTS ==========

@pytest.mark.asyncio
async def test_setup_bot_commands_success(app, mock_logger):
    """Тест успешной настройки команд бота"""
    # Создаем мок бота
    mock_bot = AsyncMock()
    mock_bot.set_my_commands = AsyncMock()
    app.bot = mock_bot
    
    await app._setup_bot_commands()
    
    # Проверяем что команды были установлены
    mock_bot.set_my_commands.assert_called_once()

# ========== SETUP TESTS ==========

@pytest.mark.asyncio
async def test_setup_success(app, mock_env, mock_logger):
    """Тест успешной полной инициализации приложения"""
    # Мокаем все необходимые компоненты
    with patch('src.app.log_startup_info'):
        # Мокаем создание бота
        mock_bot_instance = AsyncMock()
        mock_bot_instance.set_my_commands = AsyncMock()
        mock_bot_instance.session = AsyncMock()
        
        # Мокаем диспетчер
        mock_dp_instance = AsyncMock()
        mock_dp_instance.include_router = Mock()
        mock_dp_instance.resolve_used_update_types = Mock(return_value=[])
        
        # Мокаем менеджеры
        mock_db_manager = AsyncMock()
        mock_db_manager.connect = AsyncMock(return_value=True)
        mock_db_manager.test_connection = AsyncMock(return_value=True)
        
        mock_ai_manager = AsyncMock()
        mock_ai_manager.health_check = AsyncMock()
        
        mock_date_ai_manager = AsyncMock()
        mock_date_ai_manager.initialize = AsyncMock()
        
        # Мокаем импорт менеджеров
        with patch('src.app.Bot', return_value=mock_bot_instance), \
             patch('src.app.Dispatcher', return_value=mock_dp_instance), \
             patch('src.managers.database_manager.VideoDatabaseManager', return_value=mock_db_manager), \
             patch('src.managers.ai_manager.AIManager', return_value=mock_ai_manager), \
             patch('src.managers.date_ai_manager.DateAIManager', return_value=mock_date_ai_manager), \
             patch('src.app.MemoryStorage'), \
             patch('src.app.AiohttpSession'):
            
            # Мокаем обработчики
            mock_router = Mock()
            mock_ai_module = MagicMock()
            mock_ai_module.router = mock_router
            
            mock_base_module = MagicMock()
            mock_base_module.router = mock_router
            
            def import_module_side_effect(module_path, package=None):
                if 'ai_handlers' in module_path:
                    return mock_ai_module
                elif 'base_handlers' in module_path:
                    return mock_base_module
                else:
                    raise ImportError(f"Module not found: {module_path}")
            
            with patch('src.app.importlib.import_module', side_effect=import_module_side_effect):
                # Мокаем DateAI обработчики
                mock_date_ai_handlers_obj = Mock()
                mock_date_ai_handlers_obj.get_router = Mock(return_value=mock_router)
                
                with patch('src.handlers.date_ai_handlers.create_date_ai_handlers', AsyncMock(return_value=mock_date_ai_handlers_obj)):
                    await app.setup()
    
    assert app.is_initialized is True
    assert app.bot is not None
    assert app.dp is not None

@pytest.mark.asyncio
async def test_setup_configuration_error(app, mock_empty_env, mock_logger):
    """Тест инициализации с ошибкой конфигурации"""
    with pytest.raises(ValueError):
        await app.setup()
    
    assert app.is_initialized is False

@pytest.mark.asyncio
async def test_setup_connection_error(app, mock_env, mock_logger):
    """Тест инициализации с ошибкой подключения к БД"""
    with patch('src.app.log_startup_info'):
        # Мокаем менеджер БД который не может подключиться
        mock_db_manager = AsyncMock()
        mock_db_manager.connect = AsyncMock(return_value=False)
        
        # Мокаем только необходимые компоненты
        with patch('src.app.Bot', return_value=AsyncMock()), \
             patch('src.app.Dispatcher', return_value=AsyncMock()), \
             patch('src.managers.database_manager.VideoDatabaseManager', return_value=mock_db_manager):
            
            with pytest.raises(ConnectionError):
                await app.setup()
    
    assert app.is_initialized is False

# ========== RUN TESTS ==========

@pytest.mark.asyncio
async def test_run_success(app, mock_logger):
    """Тест успешного запуска поллинга"""
    app.is_initialized = True
    app.dp = AsyncMock()
    # Используем side_effect с asyncio.CancelledError чтобы имитировать остановку
    app.dp.start_polling = AsyncMock(side_effect=asyncio.CancelledError())
    
    try:
        await app.run()
    except asyncio.CancelledError:
        pass
    
    app.dp.start_polling.assert_called_once()

@pytest.mark.asyncio
async def test_run_not_initialized(app, mock_logger):
    """Тест запуска без инициализации"""
    app.is_initialized = False
    
    await app.run()
    
    # Должен логировать ошибку, но не падать
    assert True

# ========== SHUTDOWN TESTS ==========

@pytest.mark.asyncio
async def test_shutdown_success(app, mock_logger):
    """Тест успешного завершения работы"""
    app.is_polling = True
    app.db_manager = AsyncMock()
    app.ai_manager = AsyncMock()
    app.date_ai_manager = AsyncMock()
    app.bot = Mock()
    app.bot.session = AsyncMock()
    app.bot.session.close = AsyncMock()
    app.dp = AsyncMock()
    app.dp.stop_polling = AsyncMock()
    
    # Патчим log_shutdown_info
    with patch('src.app.log_shutdown_info'):
        await app.shutdown()
    
    # Проверяем порядок вызовов
    app.dp.stop_polling.assert_called_once()
    app.date_ai_manager.close.assert_called_once()
    app.ai_manager.close.assert_called_once()
    app.db_manager.close.assert_called_once()
    app.bot.session.close.assert_called_once()

@pytest.mark.asyncio
async def test_shutdown_not_polling(app, mock_logger):
    """Тест завершения работы без поллинга"""
    app.is_polling = False
    app.db_manager = AsyncMock()
    app.ai_manager = AsyncMock()
    app.date_ai_manager = AsyncMock()
    
    # Патчим log_shutdown_info
    with patch('src.app.log_shutdown_info'):
        await app.shutdown()
    
    # stop_polling не должен вызываться
    assert True

# ========== INTEGRATION TESTS ==========

@pytest.mark.asyncio
async def test_setup_shutdown_integration(app, mock_env, mock_logger):
    """Интеграционный тест setup -> shutdown"""
    with patch('src.app.log_startup_info'), \
         patch('src.app.log_shutdown_info'):
        
        # Мокаем Bot создание
        mock_bot_instance = AsyncMock()
        mock_bot_instance.set_my_commands = AsyncMock()
        mock_bot_instance.session = AsyncMock()
        mock_bot_instance.session.close = AsyncMock()
        
        # Мокаем диспетчер
        mock_dp_instance = AsyncMock()
        mock_dp_instance.include_router = Mock()
        mock_dp_instance.resolve_used_update_types = Mock(return_value=[])
        mock_dp_instance.start_polling = AsyncMock()
        mock_dp_instance.stop_polling = AsyncMock()
        
        # Мокаем менеджеры
        mock_db_manager = AsyncMock()
        mock_db_manager.connect = AsyncMock(return_value=True)
        mock_db_manager.test_connection = AsyncMock(return_value=True)
        mock_db_manager.close = AsyncMock()
        
        mock_ai_manager = AsyncMock()
        mock_ai_manager.health_check = AsyncMock()
        mock_ai_manager.close = AsyncMock()
        
        mock_date_ai_manager = AsyncMock()
        mock_date_ai_manager.initialize = AsyncMock()
        mock_date_ai_manager.close = AsyncMock()
        
        # Мокаем импорт менеджеров
        with patch('src.app.Bot', return_value=mock_bot_instance), \
             patch('src.app.Dispatcher', return_value=mock_dp_instance), \
             patch('src.managers.database_manager.VideoDatabaseManager', return_value=mock_db_manager), \
             patch('src.managers.ai_manager.AIManager', return_value=mock_ai_manager), \
             patch('src.managers.date_ai_manager.DateAIManager', return_value=mock_date_ai_manager), \
             patch('src.app.MemoryStorage'), \
             patch('src.app.AiohttpSession'):
            
            # Мокаем обработчики
            mock_router = Mock()
            mock_ai_module = MagicMock()
            mock_ai_module.router = mock_router
            
            mock_base_module = MagicMock()
            mock_base_module.router = mock_router
            
            def import_module_side_effect(module_path, package=None):
                if 'ai_handlers' in module_path:
                    return mock_ai_module
                elif 'base_handlers' in module_path:
                    return mock_base_module
                else:
                    raise ImportError(f"Module not found: {module_path}")
            
            with patch('src.app.importlib.import_module', side_effect=import_module_side_effect):
                # Мокаем DateAI обработчики
                mock_date_ai_handlers_obj = Mock()
                mock_date_ai_handlers_obj.get_router = Mock(return_value=mock_router)
                
                with patch('src.handlers.date_ai_handlers.create_date_ai_handlers', AsyncMock(return_value=mock_date_ai_handlers_obj)):
                    # Запускаем setup
                    await app.setup()
                    
                    # Проверяем что все инициализировано
                    assert app.is_initialized is True
                    
                    # Устанавливаем is_polling для shutdown
                    app.is_polling = True
                    
                    # Запускаем shutdown
                    await app.shutdown()
                    
                    # Проверяем что все закрыто
                    mock_db_manager.close.assert_called_once()
                    mock_ai_manager.close.assert_called_once()
                    mock_date_ai_manager.close.assert_called_once()
                    mock_bot_instance.session.close.assert_called_once()

# ========== MAIN FUNCTION TESTS ==========

@pytest.mark.asyncio
async def test_main_success():
    """Тест основной функции main"""
    from src.app import main
    
    mock_app = AsyncMock()
    mock_app.setup = AsyncMock()
    mock_app.run = AsyncMock()
    mock_app.shutdown = AsyncMock()
    
    with patch('src.app.TelegramBotApp', return_value=mock_app), \
         patch('src.app.setup_logging'):
        
        # Мокаем asyncio.run чтобы вызвать нашу функцию напрямую
        await main()
    
    mock_app.setup.assert_called_once()
    mock_app.run.assert_called_once()
    mock_app.shutdown.assert_called_once()

# ========== EDGE CASE TESTS ==========

def test_bot_commands_structure():
    """Тест структуры команд бота"""
    from src.app import BOT_COMMANDS
    
    assert len(BOT_COMMANDS) > 0
    
    # Проверяем наличие обязательных команд
    commands_dict = {cmd['command']: cmd['description'] for cmd in BOT_COMMANDS}
    
    assert 'start' in commands_dict
    assert 'help' in commands_dict
    assert 'today' in commands_dict
    assert 'creators' in commands_dict
    
    # Проверяем формат команд
    for cmd in BOT_COMMANDS:
        assert 'command' in cmd
        assert 'description' in cmd
        assert isinstance(cmd['command'], str)
        assert isinstance(cmd['description'], str)

# ========== MAIN EXECUTION ==========

if __name__ == "__main__":
    # Запускаем все тесты
    print("=" * 60)
    print("Запуск тестов TelegramBotApp...")
    print("=" * 60)
    
    # Подсчитываем количество тестов
    test_count = len([name for name in globals() if name.startswith('test_') and callable(globals()[name])])
    print(f"📊 Всего тестов: {test_count}")
    
    # Запускаем pytest
    pytest.main([__file__, "-v", "--tb=short"])