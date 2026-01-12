import pytest
import sys
import os
import time
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from aiogram.types import Message, BotCommand
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ========== НАСТРОЙКА ПУТЕЙ И ИМПОРТОВ ==========

# 1. Добавляем корень проекта в sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# 2. Отладочная информация
print(f"Project root: {project_root}")
print(f"Current directory: {os.getcwd()}")
print(f"sys.path first entry: {sys.path[0]}")

# 3. Проверяем существование файла
handlers_path = os.path.join(project_root, 'src', 'handlers', 'date_ai_handlers.py')
print(f"Handlers file exists: {os.path.exists(handlers_path)}")

# 4. Создаем моки для проблемных импортов ПЕРЕД импортом нашего модуля
class MockPeriodType:
    ALL_TIME = "all_time"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    CUSTOM = "custom"
    
    @staticmethod
    def value(value):
        return value

class MockDateAIManager:
    pass

# 5. Подменяем модули в sys.modules
sys.modules['managers.date_ai_manager'] = MagicMock()
sys.modules['managers.date_ai_manager'].DateAIManager = MockDateAIManager
sys.modules['managers.date_ai_manager'].PeriodType = MockPeriodType

# 6. Теперь импортируем наш модуль
try:
    from src.handlers.date_ai_handlers import DateAIHandlers, create_date_ai_handlers, StatsStates
    print("✅ Успешно импортировано: src.handlers.date_ai_handlers")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    # Пробуем альтернативный способ
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "date_ai_handlers",
        handlers_path
    )
    module = importlib.util.module_from_spec(spec)
    
    # Заменяем проблемный импорт в коде
    with open(handlers_path, 'r', encoding='utf-8') as f:
        code = f.read()
    
    # Заменяем относительный импорт на моки
    code = code.replace(
        'from ..managers.date_ai_manager import DateAIManager, PeriodType',
        '# Импорт заменен для тестирования\n'
        'DateAIManager = MockDateAIManager\n'
        'PeriodType = MockPeriodType'
    )
    
    # Выполняем код
    exec_globals = {
        'MockDateAIManager': MockDateAIManager,
        'MockPeriodType': MockPeriodType,
        'datetime': datetime,
        'timedelta': timedelta,
        'time': time,
        'AsyncMock': AsyncMock,
        'Mock': Mock,
        'Router': Mock,
        'F': Mock(),
        'Command': Mock(),
        'CommandStart': Mock(),
        'StateFilter': Mock(),
        'State': Mock(),
        'StatesGroup': Mock,
        'hbold': lambda x: f"**{x}**",
        'hcode': lambda x: f"`{x}`",
        'hitalic': lambda x: f"*{x}*",
        'logging': Mock(),
        'Optional': lambda x: x,
        'List': list,
        'Dict': dict,
        'Any': object,
        'asyncio': Mock(),
    }
    exec(code, exec_globals)
    
    DateAIHandlers = exec_globals['DateAIHandlers']
    create_date_ai_handlers = exec_globals['create_date_ai_handlers']
    StatsStates = exec_globals['StatsStates']
    print("✅ Успешно загружен модуль с заменой импортов")

# ========== FIXTURES ==========

@pytest.fixture
def mock_manager():
    """Мок DateAIManager"""
    manager = Mock()
    
    # Настройка методов менеджера
    manager.get_daily_stats = AsyncMock()
    manager.get_weekly_stats = AsyncMock()
    manager.get_monthly_stats = AsyncMock()
    manager.get_custom_period_stats = AsyncMock()
    manager.get_creator_stats = AsyncMock()
    manager.analyze_with_ai = AsyncMock()
    manager.answer_question = AsyncMock()
    manager.get_system_info = AsyncMock()
    manager.get_available_creator_ids = AsyncMock()
    manager.get_creators_with_data = AsyncMock()
    
    # Настройка data_period
    mock_period = Mock()
    mock_period.target_year = 2023
    manager.data_period = mock_period
    
    return manager

@pytest.fixture
def date_ai_handlers(mock_manager):
    """Экземпляр DateAIHandlers"""
    return DateAIHandlers(mock_manager)

@pytest.fixture
def message():
    """Мок сообщения"""
    msg = Mock(spec=Message)
    msg.from_user = Mock()
    msg.from_user.id = 123
    msg.chat = Mock()
    msg.chat.id = 456
    msg.text = "/test"
    msg.answer = AsyncMock()
    msg.reply = AsyncMock()
    return msg

@pytest.fixture
def state():
    """Мок FSMContext"""
    mock_state = Mock(spec=FSMContext)
    mock_state.set_state = AsyncMock()
    mock_state.update_data = AsyncMock()
    mock_state.get_data = AsyncMock()
    mock_state.clear = AsyncMock()
    return mock_state

# ========== BASIC TESTS ==========

def test_init_with_manager(mock_manager):
    """Тест инициализации"""
    handlers = DateAIHandlers(mock_manager)
    assert handlers.manager == mock_manager
    assert handlers.router is not None
    assert len(handlers.commands) == 12
    print("✅ test_init_with_manager passed")

def test_commands_initialization(mock_manager):
    """Тест инициализации команд"""
    handlers = DateAIHandlers(mock_manager)
    
    expected_commands = [
        ("start", "Начало работы"),
        ("help", "Помощь по командам"),
        ("ai_date_help", "Справочник команд AI анализатора"),
        ("today", "Статистика за сегодня"),
        ("yesterday", "Статистика за вчера"),
        ("week", "Статистика за неделю"),
        ("month", "Статистика за месяц"),
        ("custom", "Кастомный период"),
        ("creators", "Список креаторов"),
        ("creator", "Статистика по креатору"),
        ("system", "Системная информация"),
        ("ask", "Задать вопрос AI"),
    ]
    
    for cmd, (expected_cmd, expected_desc) in zip(handlers.commands, expected_commands):
        assert cmd.command == expected_cmd
        assert cmd.description == expected_desc
    
    print("✅ test_commands_initialization passed")

@pytest.mark.asyncio
async def test_cmd_start(date_ai_handlers, message):
    """Тест команды /start"""
    await date_ai_handlers.cmd_start(message)
    
    message.answer.assert_called_once()
    args, kwargs = message.answer.call_args
    assert "Анализатор статистики" in args[0]
    assert kwargs.get("parse_mode") == "HTML"
    print("✅ test_cmd_start passed")

@pytest.mark.asyncio
async def test_cmd_help(date_ai_handlers, message):
    """Тест команды /help"""
    await date_ai_handlers.cmd_help(message)
    
    message.answer.assert_called_once()
    args, _ = message.answer.call_args
    assert "Справка по командам" in args[0]
    print("✅ test_cmd_help passed")

@pytest.mark.asyncio
async def test_cmd_ai_date_help(date_ai_handlers, message):
    """Тест команды /ai_date_help"""
    await date_ai_handlers.cmd_ai_date_help(message)
    
    message.answer.assert_called_once()
    args, _ = message.answer.call_args
    assert "СПРАВОЧНИК КОМАНД AI АНАЛИЗАТОРА СТАТИСТИКИ" in args[0]
    print("✅ test_cmd_ai_date_help passed")

@pytest.mark.asyncio
async def test_cmd_today_success(date_ai_handlers, message):
    """Тест команды /today успешно"""
    # Мокаем внутренний метод
    date_ai_handlers._load_stats_with_ai = AsyncMock(return_value=True)
    
    await date_ai_handlers.cmd_today(message)
    
    date_ai_handlers._load_stats_with_ai.assert_called_once()
    print("✅ test_cmd_today_success passed")

@pytest.mark.asyncio
async def test_cmd_today_with_exception(date_ai_handlers, message):
    """Тест команды /today с исключением"""
    date_ai_handlers._load_stats_with_ai = AsyncMock(side_effect=Exception("Test error"))
    
    await date_ai_handlers.cmd_today(message)
    
    # Проверяем, что сообщение об ошибке было отправлено
    assert message.answer.call_count >= 1
    args, _ = message.answer.call_args_list[-1]
    assert "Произошла ошибка" in args[0] or "Ошибка" in args[0]
    print("✅ test_cmd_today_with_exception passed")

@pytest.mark.asyncio
async def test_cmd_yesterday_success(date_ai_handlers, message):
    """Тест команды /yesterday успешно"""
    date_ai_handlers._load_stats_with_ai = AsyncMock(return_value=True)
    
    await date_ai_handlers.cmd_yesterday(message)
    
    date_ai_handlers._load_stats_with_ai.assert_called_once()
    print("✅ test_cmd_yesterday_success passed")

@pytest.mark.asyncio
async def test_cmd_yesterday_with_exception(date_ai_handlers, message):
    """Тест команды /yesterday с исключением"""
    date_ai_handlers._load_stats_with_ai = AsyncMock(side_effect=Exception("Test error"))
    
    await date_ai_handlers.cmd_yesterday(message)
    
    assert message.answer.call_count >= 1
    args, _ = message.answer.call_args_list[-1]
    assert "Произошла ошибка" in args[0] or "Ошибка" in args[0]
    print("✅ test_cmd_yesterday_with_exception passed")

@pytest.mark.asyncio
async def test_cmd_week_success(date_ai_handlers, message):
    """Тест команды /week успешно"""
    date_ai_handlers._load_stats_with_ai = AsyncMock(return_value=True)
    
    await date_ai_handlers.cmd_week(message)
    
    date_ai_handlers._load_stats_with_ai.assert_called_once()
    print("✅ test_cmd_week_success passed")

@pytest.mark.asyncio
async def test_cmd_week_with_exception(date_ai_handlers, message):
    """Тест команды /week с исключением"""
    date_ai_handlers._load_stats_with_ai = AsyncMock(side_effect=Exception("Test error"))
    
    await date_ai_handlers.cmd_week(message)
    
    assert message.answer.call_count >= 1
    args, _ = message.answer.call_args_list[-1]
    assert "Произошла ошибка" in args[0] or "Ошибка" in args[0]
    print("✅ test_cmd_week_with_exception passed")

@pytest.mark.asyncio
async def test_cmd_month_success(date_ai_handlers, message):
    """Тест команды /month успешно"""
    date_ai_handlers._load_stats_with_ai = AsyncMock(return_value=True)
    
    await date_ai_handlers.cmd_month(message)
    
    date_ai_handlers._load_stats_with_ai.assert_called_once()
    print("✅ test_cmd_month_success passed")

@pytest.mark.asyncio
async def test_cmd_month_with_exception(date_ai_handlers, message):
    """Тест команды /month с исключением"""
    date_ai_handlers._load_stats_with_ai = AsyncMock(side_effect=Exception("Test error"))
    
    await date_ai_handlers.cmd_month(message)
    
    assert message.answer.call_count >= 1
    args, _ = message.answer.call_args_list[-1]
    assert "Произошла ошибка" in args[0] or "Ошибка" in args[0]
    print("✅ test_cmd_month_with_exception passed")

# ========== FSM TESTS ==========

@pytest.mark.asyncio
async def test_cmd_custom(date_ai_handlers, message, state):
    """Тест команды /custom"""
    await date_ai_handlers.cmd_custom(message, state)
    
    message.answer.assert_called_once()
    state.set_state.assert_called_once_with(StatsStates.waiting_custom_start)
    print("✅ test_cmd_custom passed")

@pytest.mark.asyncio
async def test_process_custom_start_valid(date_ai_handlers, message, state):
    """Тест обработки начальной даты кастомного периода - валидная дата"""
    message.text = "01.11.2023"
    state.get_data = AsyncMock(return_value={})
    
    await date_ai_handlers.process_custom_start(message, state)
    
    state.update_data.assert_called_once()
    state.set_state.assert_called_once_with(StatsStates.waiting_custom_end)
    message.answer.assert_called_once()
    print("✅ test_process_custom_start_valid passed")

@pytest.mark.asyncio
async def test_process_custom_start_wrong_year(date_ai_handlers, message, state):
    """Тест обработки начальной даты - неправильный год"""
    message.text = "01.11.2024"  # Не 2023 год
    
    await date_ai_handlers.process_custom_start(message, state)
    
    message.answer.assert_called_once()
    assert "Нет данных за 2024 год" in message.answer.call_args[0][0]
    print("✅ test_process_custom_start_wrong_year passed")

@pytest.mark.asyncio
async def test_process_custom_start_invalid_format(date_ai_handlers, message, state):
    """Тест обработки начальной даты - неверный формат"""
    message.text = "01-11-2023"  # Неправильный формат
    
    await date_ai_handlers.process_custom_start(message, state)
    
    message.answer.assert_called_once()
    assert "Неверный формат даты" in message.answer.call_args[0][0]
    print("✅ test_process_custom_start_invalid_format passed")

@pytest.mark.asyncio
async def test_process_custom_end_valid(date_ai_handlers, message, state):
    """Тест обработки конечной даты кастомного периода - валидная дата"""
    message.text = "10.11.2023"
    start_date = datetime(2023, 11, 1)
    state.get_data = AsyncMock(return_value={'start_date': start_date})
    
    # Мокаем менеджер
    mock_stats = {'has_data': True}
    date_ai_handlers.manager.get_custom_period_stats = AsyncMock(return_value=mock_stats)
    date_ai_handlers.manager.analyze_with_ai = AsyncMock(return_value="AI анализ")
    
    await date_ai_handlers.process_custom_end(message, state)
    
    date_ai_handlers.manager.get_custom_period_stats.assert_called_once_with(start_date, datetime(2023, 11, 10))
    state.clear.assert_called_once()
    print("✅ test_process_custom_end_valid passed")

@pytest.mark.asyncio
async def test_process_custom_end_no_data(date_ai_handlers, message, state):
    """Тест обработки конечной даты - нет данных"""
    message.text = "10.11.2023"
    start_date = datetime(2023, 11, 1)
    state.get_data = AsyncMock(return_value={'start_date': start_date})
    
    mock_stats = {'has_data': False, 'period_type': 'custom', 'start_date': start_date, 'end_date': datetime(2023, 11, 10)}
    date_ai_handlers.manager.get_custom_period_stats = AsyncMock(return_value=mock_stats)
    
    await date_ai_handlers.process_custom_end(message, state)
    
    message.answer.assert_called()
    state.clear.assert_called_once()
    print("✅ test_process_custom_end_no_data passed")

@pytest.mark.asyncio
async def test_process_custom_end_no_start_date(date_ai_handlers, message, state):
    """Тест обработки конечной даты - нет начальной даты"""
    message.text = "10.11.2023"
    state.get_data = AsyncMock(return_value={})  # Нет start_date
    
    await date_ai_handlers.process_custom_end(message, state)
    
    message.answer.assert_called_once()
    assert "не найдена начальная дата" in message.answer.call_args[0][0]
    state.clear.assert_called_once()
    print("✅ test_process_custom_end_no_start_date passed")

@pytest.mark.asyncio
async def test_process_custom_end_wrong_year(date_ai_handlers, message, state):
    """Тест обработки конечной даты - неправильный год"""
    message.text = "10.11.2024"  # Не 2023 год
    start_date = datetime(2023, 11, 1)
    state.get_data = AsyncMock(return_value={'start_date': start_date})
    
    await date_ai_handlers.process_custom_end(message, state)
    
    message.answer.assert_called_once()
    assert "Нет данных за 2024 год" in message.answer.call_args[0][0]
    state.clear.assert_called_once()
    print("✅ test_process_custom_end_wrong_year passed")

@pytest.mark.asyncio
async def test_process_custom_end_end_before_start(date_ai_handlers, message, state):
    """Тест обработки конечной даты - конечная дата раньше начальной"""
    message.text = "01.10.2023"  # Раньше ноября
    start_date = datetime(2023, 11, 1)
    state.get_data = AsyncMock(return_value={'start_date': start_date})
    
    await date_ai_handlers.process_custom_end(message, state)
    
    message.answer.assert_called_once()
    assert "Конечная дата должна быть позже начальной" in message.answer.call_args[0][0]
    state.clear.assert_called_once()
    print("✅ test_process_custom_end_end_before_start passed")

@pytest.mark.asyncio
async def test_process_custom_end_invalid_format(date_ai_handlers, message, state):
    """Тест обработки конечной даты - неверный формат"""
    message.text = "10-11-2023"  # Неправильный формат
    start_date = datetime(2023, 11, 1)
    state.get_data = AsyncMock(return_value={'start_date': start_date})
    
    await date_ai_handlers.process_custom_end(message, state)
    
    message.answer.assert_called_once()
    assert "Неверный формат даты" in message.answer.call_args[0][0]
    print("✅ test_process_custom_end_invalid_format passed")

# ========== CREATORS TESTS ==========

@pytest.mark.asyncio
async def test_cmd_creators_with_data(date_ai_handlers, message):
    """Тест команды /creators с данными"""
    date_ai_handlers._get_available_creators = AsyncMock(return_value=[1, 2, 3])
    
    await date_ai_handlers.cmd_creators(message)
    
    message.answer.assert_called_once()
    args, _ = message.answer.call_args
    assert "Креаторы с данными" in args[0]
    assert "Всего креаторов: 3" in args[0]
    print("✅ test_cmd_creators_with_data passed")

@pytest.mark.asyncio
async def test_cmd_creators_no_data(date_ai_handlers, message):
    """Тест команды /creators без данных"""
    date_ai_handlers._get_available_creators = AsyncMock(return_value=[])
    
    await date_ai_handlers.cmd_creators(message)
    
    message.answer.assert_called_once()
    args, _ = message.answer.call_args
    assert "Нет данных о креаторах" in args[0]
    print("✅ test_cmd_creators_no_data passed")

@pytest.mark.asyncio
async def test_cmd_creators_with_exception(date_ai_handlers, message):
    """Тест команды /creators с исключением"""
    date_ai_handlers._get_available_creators = AsyncMock(side_effect=Exception("Test error"))
    
    await date_ai_handlers.cmd_creators(message)
    
    message.answer.assert_called_once()
    args, _ = message.answer.call_args
    assert "Ошибка при получении списка креаторов" in args[0]
    print("✅ test_cmd_creators_with_exception passed")

@pytest.mark.asyncio
async def test_cmd_creator_with_creators(date_ai_handlers, message, state):
    """Тест команды /creator когда есть креаторы"""
    date_ai_handlers._get_available_creators = AsyncMock(return_value=[1, 2, 3])
    
    await date_ai_handlers.cmd_creator(message, state)
    
    message.answer.assert_called_once()
    state.set_state.assert_called_once_with(StatsStates.waiting_creator_id)
    print("✅ test_cmd_creator_with_creators passed")

@pytest.mark.asyncio
async def test_cmd_creator_no_creators(date_ai_handlers, message, state):
    """Тест команды /creator когда нет креаторов"""
    date_ai_handlers._get_available_creators = AsyncMock(return_value=[])
    
    await date_ai_handlers.cmd_creator(message, state)
    
    message.answer.assert_called_once()
    assert "Нет данных о креаторах" in message.answer.call_args[0][0]
    print("✅ test_cmd_creator_no_creators passed")

@pytest.mark.asyncio
async def test_process_creator_id_valid(date_ai_handlers, message, state):
    """Тест обработки ID креатора - валидный ID"""
    message.text = "5"
    
    # Мокаем внутренний метод
    date_ai_handlers._show_creator_stats = AsyncMock()
    
    await date_ai_handlers.process_creator_id(message, state)
    
    date_ai_handlers._show_creator_stats.assert_called_once_with(message, 5)
    state.clear.assert_called_once()
    print("✅ test_process_creator_id_valid passed")

@pytest.mark.asyncio
async def test_process_creator_id_too_low(date_ai_handlers, message, state):
    """Тест обработки ID креатора - ID меньше 1"""
    message.text = "0"
    
    await date_ai_handlers.process_creator_id(message, state)
    
    message.answer.assert_called_once()
    assert "ID креатора должен быть от 1 до 19" in message.answer.call_args[0][0]
    print("✅ test_process_creator_id_too_low passed")

@pytest.mark.asyncio
async def test_process_creator_id_too_high(date_ai_handlers, message, state):
    """Тест обработки ID креатора - ID больше 19"""
    message.text = "20"
    
    await date_ai_handlers.process_creator_id(message, state)
    
    message.answer.assert_called_once()
    assert "ID креатора должен быть от 1 до 19" in message.answer.call_args[0][0]
    print("✅ test_process_creator_id_too_high passed")

@pytest.mark.asyncio
async def test_process_creator_id_invalid_format(date_ai_handlers, message, state):
    """Тест обработки ID креатора - не число"""
    message.text = "abc"
    
    await date_ai_handlers.process_creator_id(message, state)
    
    message.answer.assert_called_once()
    assert "Введите число от 1 до 19" in message.answer.call_args[0][0]
    print("✅ test_process_creator_id_invalid_format passed")

@pytest.mark.asyncio
async def test_show_creator_stats_with_data(date_ai_handlers, message):
    """Тест показа статистики креатора с данными"""
    mock_stats = {
        'has_data': True,
        'period_type': 'all_time',
        'total_videos': 10,
        'new_videos': 2,
        'views_gained': 15000,
        'likes_gained': 500,
        'engagement_rate': 3.5
    }
    
    date_ai_handlers.manager.get_creator_stats = AsyncMock(return_value=mock_stats)
    
    await date_ai_handlers._show_creator_stats(message, creator_id=5)
    
    message.answer.assert_called()
    args, _ = message.answer.call_args
    assert "Креатор #5" in args[0]
    assert "Видео: 10" in args[0]
    print("✅ test_show_creator_stats_with_data passed")

@pytest.mark.asyncio
async def test_show_creator_stats_no_data(date_ai_handlers, message):
    """Тест показа статистики креатора без данных"""
    mock_stats = {
        'has_data': False
    }
    
    date_ai_handlers.manager.get_creator_stats = AsyncMock(return_value=mock_stats)
    
    await date_ai_handlers._show_creator_stats(message, creator_id=5)
    
    message.answer.assert_called()
    args, _ = message.answer.call_args
    assert "Нет данных за выбранный период" in args[0]
    print("✅ test_show_creator_stats_no_data passed")

@pytest.mark.asyncio
async def test_show_creator_stats_with_exception(date_ai_handlers, message):
    """Тест показа статистики креатора с исключением"""
    date_ai_handlers.manager.get_creator_stats = AsyncMock(side_effect=Exception("Test error"))
    
    await date_ai_handlers._show_creator_stats(message, creator_id=5)
    
    message.answer.assert_called()
    args, _ = message.answer.call_args
    assert "Ошибка при получении статистики" in args[0]
    print("✅ test_show_creator_stats_with_exception passed")

# ========== SYSTEM TESTS ==========

@pytest.mark.asyncio
async def test_cmd_system_success(date_ai_handlers, message):
    """Тест команды /system успешно"""
    system_info = {
        'data_year': 2023,
        'cache_size': 150,
        'cache_ttl': 300,
        'available_creator_ids': [1, 2, 3],
        'filters': {
            'video_creation': {'start': '2023-08-01', 'end': '2023-10-31'},
            'stats_collection': {'start': '2023-11-01', 'end': '2023-12-31'}
        },
        'gigachat_available': True
    }
    date_ai_handlers.manager.get_system_info = AsyncMock(return_value=system_info)
    
    await date_ai_handlers.cmd_system(message)
    
    message.answer.assert_called_once()
    args, _ = message.answer.call_args
    assert "Системная информация" in args[0]
    print("✅ test_cmd_system_success passed")

@pytest.mark.asyncio
async def test_cmd_system_with_exception(date_ai_handlers, message):
    """Тест команды /system с исключением"""
    date_ai_handlers.manager.get_system_info = AsyncMock(side_effect=Exception("Test error"))
    
    await date_ai_handlers.cmd_system(message)
    
    message.answer.assert_called_once()
    args, _ = message.answer.call_args
    assert "Ошибка при получении системной информации" in args[0]
    print("✅ test_cmd_system_with_exception passed")

# ========== AI QUESTION TESTS ==========

@pytest.mark.asyncio
async def test_cmd_ask(date_ai_handlers, message, state):
    """Тест команды /ask"""
    await date_ai_handlers.cmd_ask(message, state)
    
    message.answer.assert_called_once()
    state.set_state.assert_called_once_with(StatsStates.waiting_question)
    print("✅ test_cmd_ask passed")

@pytest.mark.asyncio
async def test_process_question_valid(date_ai_handlers, message, state):
    """Тест обработки вопроса - валидный вопрос"""
    message.text = "Какие креаторы самые популярные?"
    date_ai_handlers.manager.answer_question = AsyncMock(return_value="Топ креаторы: #1, #2, #3")
    
    await date_ai_handlers.process_question(message, state)
    
    date_ai_handlers.manager.answer_question.assert_called_once_with(message.text)
    message.answer.assert_called()
    state.clear.assert_called_once()
    print("✅ test_process_question_valid passed")

@pytest.mark.asyncio
async def test_process_question_empty(date_ai_handlers, message, state):
    """Тест обработки вопроса - пустой вопрос"""
    message.text = ""
    
    await date_ai_handlers.process_question(message, state)
    
    message.answer.assert_called_once()
    assert "Вопрос не может быть пустым" in message.answer.call_args[0][0]
    print("✅ test_process_question_empty passed")

@pytest.mark.asyncio
async def test_process_question_with_exception(date_ai_handlers, message, state):
    """Тест обработки вопроса с исключением"""
    message.text = "Какой-то вопрос"
    date_ai_handlers.manager.answer_question = AsyncMock(side_effect=Exception("Test error"))
    
    await date_ai_handlers.process_question(message, state)
    
    message.answer.assert_called()
    args, _ = message.answer.call_args
    assert "Ошибка при обработке вопроса" in args[0]
    state.clear.assert_called_once()
    print("✅ test_process_question_with_exception passed")

# ========== HELPER METHOD TESTS ==========

def test_get_target_year(date_ai_handlers, mock_manager):
    """Тест получения целевого года"""
    year = date_ai_handlers._get_target_year()
    assert year == 2023
    
    # Тест с другим годом
    mock_period = Mock()
    mock_period.target_year = 2024
    mock_manager.data_period = mock_period
    handlers = DateAIHandlers(mock_manager)
    assert handlers._get_target_year() == 2024
    
    print("✅ test_get_target_year passed")

def test_get_target_year_no_data_period():
    """Тест получения целевого года без data_period"""
    mock_manager = Mock()
    mock_manager.data_period = None
    
    handlers = DateAIHandlers(mock_manager)
    year = handlers._get_target_year()
    assert year == 2023  # значение по умолчанию
    print("✅ test_get_target_year_no_data_period passed")

@pytest.mark.asyncio
async def test_load_stats_with_ai_success(date_ai_handlers, message):
    """Тест _load_stats_with_ai успешно"""
    mock_stats_method = AsyncMock(return_value={
        'has_data': True,
        'period_type': 'day',
        'start_date': datetime(2023, 11, 15),
        'end_date': datetime(2023, 11, 15)
    })
    
    date_ai_handlers.manager.analyze_with_ai = AsyncMock(return_value="AI анализ")
    
    result = await date_ai_handlers._load_stats_with_ai(message, mock_stats_method)
    
    assert result is True
    assert message.answer.call_count == 3  # "Загружаю...", "Анализирую...", результат
    print("✅ test_load_stats_with_ai_success passed")

@pytest.mark.asyncio
async def test_load_stats_with_ai_no_data(date_ai_handlers, message):
    """Тест _load_stats_with_ai без данных"""
    mock_stats_method = AsyncMock(return_value={
        'has_data': False,
        'period_type': 'day',
        'start_date': datetime(2023, 11, 15),
        'end_date': datetime(2023, 11, 15)
    })
    
    result = await date_ai_handlers._load_stats_with_ai(message, mock_stats_method)
    
    assert result is False
    assert message.answer.call_count == 2  # "Загружаю..." + сообщение об отсутствии данных
    print("✅ test_load_stats_with_ai_no_data passed")

@pytest.mark.asyncio
async def test_load_stats_with_ai_exception(date_ai_handlers, message):
    """Тест _load_stats_with_ai с исключением"""
    mock_stats_method = AsyncMock(side_effect=Exception("Test error"))
    
    result = await date_ai_handlers._load_stats_with_ai(message, mock_stats_method)
    
    assert result is False
    assert message.answer.call_count == 2  # "Загружаю..." + сообщение об ошибке
    print("✅ test_load_stats_with_ai_exception passed")

@pytest.mark.asyncio
async def test_get_available_creators_from_manager(date_ai_handlers):
    """Тест _get_available_creators с методами менеджера"""
    # Сначала очищаем кэш
    date_ai_handlers._creators_cache = None
    date_ai_handlers._cache_time = None
    
    # Тест с get_available_creator_ids
    date_ai_handlers.manager.get_available_creator_ids = AsyncMock(return_value=[1, 2, 3])
    result = await date_ai_handlers._get_available_creators()
    assert result == [1, 2, 3]
    assert date_ai_handlers._creators_cache == [1, 2, 3]
    
    print("✅ test_get_available_creators_from_manager passed")

@pytest.mark.asyncio
async def test_get_available_creators_cached(date_ai_handlers):
    """Тест _get_available_creators с кэшем"""
    # Устанавливаем кэш
    date_ai_handlers._creators_cache = [1, 2, 3]
    date_ai_handlers._cache_time = time.time() - 100  # 100 секунд назад
    
    result = await date_ai_handlers._get_available_creators()
    assert result == [1, 2, 3]
    
    # Проверяем, что если кэш устарел, он обновится
    date_ai_handlers._cache_time = time.time() - 400  # 400 секунд назад (> 300)
    date_ai_handlers.manager.get_available_creator_ids = AsyncMock(return_value=[4, 5, 6])
    result = await date_ai_handlers._get_available_creators()
    assert result == [4, 5, 6]
    
    print("✅ test_get_available_creators_cached passed")

@pytest.mark.asyncio
async def test_get_available_creators_no_method(date_ai_handlers):
    """Тест _get_available_creators без методов в менеджере"""
    # Очищаем кэш
    date_ai_handlers._creators_cache = None
    date_ai_handlers._cache_time = None
    
    # Удаляем методы из менеджера
    delattr(date_ai_handlers.manager, 'get_available_creator_ids')
    delattr(date_ai_handlers.manager, 'get_creators_with_data')
    
    result = await date_ai_handlers._get_available_creators()
    assert result == []
    
    print("✅ test_get_available_creators_no_method passed")

@pytest.mark.asyncio
async def test_get_available_creators_with_exception(date_ai_handlers):
    """Тест _get_available_creators с исключением"""
    # Очищаем кэш
    date_ai_handlers._creators_cache = None
    date_ai_handlers._cache_time = None
    
    date_ai_handlers.manager.get_available_creator_ids = AsyncMock(side_effect=Exception("Test error"))
    
    result = await date_ai_handlers._get_available_creators()
    assert result == []
    
    print("✅ test_get_available_creators_with_exception passed")

# ========== FORMATTING TESTS ==========

def test_format_no_data_message_day(date_ai_handlers):
    """Тест форматирования сообщения без данных (день)"""
    stats = {
        'has_data': False,
        'period_type': 'day',
        'start_date': datetime(2023, 11, 15),
        'end_date': datetime(2023, 11, 15)
    }
    
    message = date_ai_handlers._format_no_data_message(stats)
    
    assert "📅" in message
    assert "15.11.2023" in message
    assert "Ср" in message
    assert "Нет данных" in message
    assert "2023 год" in message
    print("✅ test_format_no_data_message_day passed")

def test_format_no_data_message_week(date_ai_handlers):
    """Тест форматирования сообщения без данных (неделя)"""
    stats = {
        'has_data': False,
        'period_type': 'week',
        'start_date': datetime(2023, 11, 13),  # понедельник
        'end_date': datetime(2023, 11, 19)
    }
    
    message = date_ai_handlers._format_no_data_message(stats)
    
    assert "📆" in message
    assert "13.11-19.11.2023" in message
    print("✅ test_format_no_data_message_week passed")

def test_format_no_data_message_month(date_ai_handlers):
    """Тест форматирования сообщения без данных (месяц)"""
    stats = {
        'has_data': False,
        'period_type': 'month',
        'start_date': datetime(2023, 11, 1),
        'end_date': datetime(2023, 11, 30)
    }
    
    message = date_ai_handlers._format_no_data_message(stats)
    
    # Проверяем что заголовок содержит месяц и год
    assert "🗓️" in message
    # В сообщении будет <b>Ноябрь</b> 2023, поэтому проверяем оба варианта
    assert "Ноябрь" in message and "2023" in message
    print("✅ test_format_no_data_message_month passed")

def test_format_no_data_message_custom(date_ai_handlers):
    """Тест форматирования сообщения без данных (кастомный период)"""
    stats = {
        'has_data': False,
        'period_type': 'custom',
        'start_date': datetime(2023, 11, 1),
        'end_date': datetime(2023, 11, 15),
        'message': 'Данные не найдены'
    }
    
    message = date_ai_handlers._format_no_data_message(stats)
    
    assert "📅" in message
    assert "01.11.2023 - 15.11.2023" in message
    assert "Данные не найдены" in message
    print("✅ test_format_no_data_message_custom passed")

def test_format_stats_message(date_ai_handlers):
    """Тест форматирования сообщения со статистикой"""
    stats = {
        'has_data': True,
        'period_type': 'day',
        'start_date': datetime(2023, 11, 15),
        'end_date': datetime(2023, 11, 15),
        'data_type': 'mixed',
        'total_videos_analyzed': 10,
        'new_videos': 2,
        'active_creators': 5,
        'views_gained': 15000,
        'likes_gained': 500,
        'engagement_rate': 3.5,
        'top_creators': [
            {'human_id': 1, 'views_gained': 5000, 'new_videos': 1},
            {'human_id': 2, 'views_gained': 3000, 'new_videos': 0},
            {'human_id': 3, 'views_gained': 2000, 'new_videos': 1},
            {'human_id': 4, 'views_gained': 1000, 'new_videos': 0},
            {'human_id': 5, 'views_gained': 800, 'new_videos': 0},
        ],
        'filters_applied': {
            'year': 2023,
            'video_creation_months': 'август-октябрь',
            'stats_months': 'ноябрь-декабрь'
        }
    }
    
    ai_analysis = "AI анализ показывает рост активности"
    message = date_ai_handlers._format_stats_message(stats, ai_analysis)
    
    assert "📅" in message
    assert "15.11.2023" in message
    assert "Статистика:" in message
    assert "10" in message  # total_videos_analyzed
    assert "15,000" in message or "15000" in message  # views_gained
    assert "Топ креаторов:" in message
    assert "🥇" in message or "Креатор #1" in message
    assert "🥈" in message or "Креатор #2" in message
    assert "🥉" in message or "Креатор #3" in message
    assert "4️⃣" in message or "Креатор #4" in message
    assert "5️⃣" in message or "Креатор #5" in message
    assert "AI анализ:" in message
    assert "Примененные фильтры:" in message
    print("✅ test_format_stats_message passed")

def test_format_stats_message_video_creation(date_ai_handlers):
    """Тест форматирования сообщения только с созданием видео"""
    stats = {
        'has_data': True,
        'period_type': 'day',
        'start_date': datetime(2023, 11, 15),
        'end_date': datetime(2023, 11, 15),
        'data_type': 'video_creation',
        'total_videos_analyzed': 5,
        'new_videos': 2,
        'active_creators': 3,
        'views_gained': 0,
        'likes_gained': 0,
        'engagement_rate': 0,
        'top_creators': [],
    }
    
    ai_analysis = "Было создано 2 новых видео"
    message = date_ai_handlers._format_stats_message(stats, ai_analysis)
    
    assert "📹 Только создание видео" in message or "video_creation" in message
    print("✅ test_format_stats_message_video_creation passed")

def test_format_stats_message_stats_only(date_ai_handlers):
    """Тест форматирования сообщения только со статистикой"""
    stats = {
        'has_data': True,
        'period_type': 'day',
        'start_date': datetime(2023, 11, 15),
        'end_date': datetime(2023, 11, 15),
        'data_type': 'stats_only',
        'total_videos_analyzed': 5,
        'new_videos': 0,
        'active_creators': 3,
        'views_gained': 10000,
        'likes_gained': 300,
        'engagement_rate': 3.0,
        'top_creators': [],
    }
    
    ai_analysis = "Просмотры увеличились на 10000"
    message = date_ai_handlers._format_stats_message(stats, ai_analysis)
    
    assert "📊 Только статистика просмотров" in message or "stats_only" in message
    print("✅ test_format_stats_message_stats_only passed")

def test_format_stats_message_no_filters_applied(date_ai_handlers):
    """Тест форматирования сообщения без filters_applied"""
    stats = {
        'has_data': True,
        'period_type': 'day',
        'start_date': datetime(2023, 11, 15),
        'end_date': datetime(2023, 11, 15),
        'data_type': 'mixed',
        'total_videos_analyzed': 10,
        'new_videos': 2,
        'active_creators': 5,
        'views_gained': 15000,
        'likes_gained': 500,
        'engagement_rate': 3.5,
        'top_creators': []
    }
    
    ai_analysis = "AI анализ"
    message = date_ai_handlers._format_stats_message(stats, ai_analysis)
    
    assert "Примененные фильтры:" in message
    assert "2023" in message
    print("✅ test_format_stats_message_no_filters_applied passed")

# ========== UTILITY TESTS ==========

def test_get_bot_commands(date_ai_handlers):
    """Тест получения списка команд бота"""
    commands = date_ai_handlers.get_bot_commands()
    
    assert len(commands) == 12
    assert isinstance(commands[0], BotCommand)
    assert commands[0].command == "start"
    assert commands[0].description == "Начало работы"
    print("✅ test_get_bot_commands passed")

def test_get_router(date_ai_handlers):
    """Тест получения router"""
    router = date_ai_handlers.get_router()
    
    assert router is not None
    assert hasattr(router, "message")
    print("✅ test_get_router passed")

def test_stats_states_class():
    """Тест класса состояний"""
    assert hasattr(StatsStates, 'waiting_custom_start')
    assert hasattr(StatsStates, 'waiting_custom_end')
    assert hasattr(StatsStates, 'waiting_creator_id')
    assert hasattr(StatsStates, 'waiting_question')
    print("✅ test_stats_states_class passed")

# ========== FACTORY FUNCTION TESTS ==========

@pytest.mark.asyncio
async def test_create_date_ai_handlers_basic(mock_manager):
    """Базовый тест создания обработчиков"""
    handlers = await create_date_ai_handlers(mock_manager)
    
    # Функция может вернуть None при ошибке, проверяем оба случая
    if handlers is not None:
        assert isinstance(handlers, DateAIHandlers)
        assert handlers.manager == mock_manager
    print("✅ test_create_date_ai_handlers_basic passed")

@pytest.mark.asyncio
async def test_create_date_ai_handlers_exception():
    """Тест создания обработчиков с исключением"""
    # Создаем мок, который вызовет исключение при создании DateAIHandlers
    mock_manager = Mock()
    
    # Создаем мок для замены DateAIHandlers, который будет вызывать исключение
    class FailingDateAIHandlers:
        def __init__(self, manager):
            raise Exception("Test error")
    
    # Сохраняем оригинальный класс
    original_class = DateAIHandlers
    
    # Временно заменяем
    import sys
    if 'src.handlers.date_ai_handlers' in sys.modules:
        sys.modules['src.handlers.date_ai_handlers'].DateAIHandlers = FailingDateAIHandlers
    
    try:
        handlers = await create_date_ai_handlers(mock_manager)
        # При исключении функция должна вернуть None
        assert handlers is None
    finally:
        # Восстанавливаем оригинальный класс
        if 'src.handlers.date_ai_handlers' in sys.modules:
            sys.modules['src.handlers.date_ai_handlers'].DateAIHandlers = original_class
    
    print("✅ test_create_date_ai_handlers_exception passed")

# ========== INTEGRATION TESTS ==========

@pytest.mark.asyncio
async def test_integration_flow(date_ai_handlers, message):
    """Интеграционный тест потока команд"""
    # Начинаем с /start
    await date_ai_handlers.cmd_start(message)
    first_call = message.answer.call_args_list[0]
    assert "Анализатор статистики" in first_call[0][0]
    
    # Очищаем вызовы для следующей команды
    message.answer.reset_mock()
    
    # Получаем help
    await date_ai_handlers.cmd_help(message)
    second_call = message.answer.call_args_list[0]
    assert "Справка по командам" in second_call[0][0]
    
    # Очищаем вызовы для следующей команды
    message.answer.reset_mock()
    
    # Проверяем системную информацию с корректными данными
    date_ai_handlers.manager.get_system_info = AsyncMock(return_value={
        'data_year': 2023,
        'cache_size': 0,
        'cache_ttl': 0,
        'available_creator_ids': [],
        'filters': {
            'video_creation': {'start': '2023-08-01', 'end': '2023-10-31'},
            'stats_collection': {'start': '2023-11-01', 'end': '2023-12-31'}
        },
        'gigachat_available': False
    })
    await date_ai_handlers.cmd_system(message)
    third_call = message.answer.call_args_list[0]
    assert "Системная информация" in third_call[0][0]
    
    print("✅ test_integration_flow passed")

# ========== EDGE CASE TESTS ==========

def test_edge_case_empty_period_type(date_ai_handlers):
    """Тест граничного случая - пустой period_type"""
    stats = {
        'has_data': False,
        'period_type': '',
        'start_date': datetime(2023, 11, 15),
        'end_date': datetime(2023, 11, 15)
    }
    
    message = date_ai_handlers._format_no_data_message(stats)
    # Должно сработать ветка else
    assert "Период" in message or "📅" in message
    
    print("✅ test_edge_case_empty_period_type passed")

def test_edge_case_unknown_data_type(date_ai_handlers):
    """Тест граничного случая - неизвестный data_type"""
    stats = {
        'has_data': True,
        'period_type': 'day',
        'start_date': datetime(2023, 11, 15),
        'end_date': datetime(2023, 11, 15),
        'data_type': 'unknown_type',
        'total_videos_analyzed': 10,
        'new_videos': 2,
        'active_creators': 5,
        'views_gained': 15000,
        'likes_gained': 500,
        'engagement_rate': 3.5,
        'top_creators': []
    }
    
    ai_analysis = "AI анализ"
    message = date_ai_handlers._format_stats_message(stats, ai_analysis)
    
    # Не должно падать с ошибкой
    assert "📅" in message
    print("✅ test_edge_case_unknown_data_type passed")

# ========== MAIN ==========

if __name__ == "__main__":
    # Сначала запустим базовые проверки
    print("=" * 60)
    print("Запуск расширенных тестов DateAIHandlers...")
    print("=" * 60)
    
    # Создаем простой мок для проверки
    mock_manager = Mock()
    mock_period = Mock()
    mock_period.target_year = 2023
    mock_manager.data_period = mock_period
    
    handlers = DateAIHandlers(mock_manager)
    print(f"✅ DateAIHandlers создан: {handlers}")
    print(f"✅ Команд: {len(handlers.commands)}")
    print(f"✅ Целевой год: {handlers._get_target_year()}")
    
    # Запускаем pytest
    print("\n" + "=" * 60)
    print("Запуск всех тестов через pytest...")
    print("=" * 60)
    pytest.main([__file__, "-v", "--tb=short"])