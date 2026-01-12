import os
import sys
import logging
import pytest
from unittest.mock import patch, MagicMock, mock_open, call
import io
from logging.handlers import RotatingFileHandler

# Добавляем путь к src для импорта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture(autouse=True)
def reset_logging_and_modules():
    """Сброс настроек логирования и модулей перед каждым тестом"""
    # Сохраняем корневой логгер
    root_logger = logging.getLogger()
    # Удаляем все handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    # Сбрасываем уровень
    root_logger.setLevel(logging.WARNING)
    
    # Удаляем модуль из sys.modules чтобы переимпортировать
    modules_to_delete = [m for m in sys.modules.keys() if m == 'log_config' or m.startswith('log_config.')]
    for module in modules_to_delete:
        if module in sys.modules:
            del sys.modules[module]
    
    yield
    
    # Очистка после теста
    modules_to_delete = [m for m in sys.modules.keys() if m == 'log_config' or m.startswith('log_config.')]
    for module in modules_to_delete:
        if module in sys.modules:
            del sys.modules[module]


def test_remove_emojis():
    """Тест удаления эмодзи из текста"""
    # Патчим os.makedirs ПЕРЕД импортом модуля
    with patch('os.makedirs'):
        # Импортируем заново
        import log_config
        from log_config import _remove_emojis
        
        # Тест с эмодзи
        text_with_emoji = "Привет! 👋 Как дела? 😊"
        result = _remove_emojis(text_with_emoji)
        assert result == "Привет!  Как дела? "
        assert "👋" not in result
        assert "😊" not in result
        
        # Тест с кириллицей и ASCII
        text_without_emoji = "Hello мир! 123"
        result = _remove_emojis(text_without_emoji)
        assert result == text_without_emoji
        
        # Тест с флагами (специальные эмодзи)
        text_with_flags = "Россия 🇷🇺 и США 🇺🇸"
        result = _remove_emojis(text_with_flags)
        assert result == "Россия  и США "
        
        # Тест с пустой строкой
        assert _remove_emojis("") == ""
        
        # Тест с только эмодзи
        assert _remove_emojis("👋😊🎉") == ""


def test_safe_stream_handler_emit():
    """Тест SafeStreamHandler с разными кодировками"""
    # Патчим os.makedirs ПЕРЕД импортом модуля
    with patch('os.makedirs'):
        # Импортируем заново
        import log_config
        from log_config import SafeStreamHandler
        
        # Создаем реальный handler и подменяем поток
        class MockStream:
            def __init__(self, encoding='utf-8'):
                self.encoding = encoding
                self.written = []
                
            def write(self, text):
                self.written.append(text)
                
            def flush(self):
                pass
        
        # Тест с UTF-8 потоком
        utf8_stream = MockStream('utf-8')
        handler = SafeStreamHandler(utf8_stream)
        handler.setFormatter(logging.Formatter('%(message)s'))
        
        # Создаем тестовую запись
        record = logging.LogRecord(
            name='test',
            level=logging.INFO,
            pathname='',
            lineno=0,
            msg='Тест с эмодзи 👋',
            args=(),
            exc_info=None
        )
        
        handler.emit(record)
        assert len(utf8_stream.written) > 0
        assert 'Тест с эмодзи 👋' in utf8_stream.written[0]
        
        # Тест с Latin-1 потоком
        latin_stream = MockStream('latin-1')
        handler2 = SafeStreamHandler(latin_stream)
        handler2.setFormatter(logging.Formatter('%(message)s'))
        
        handler2.emit(record)
        assert len(latin_stream.written) > 0
        # В Latin-1 эмодзи должны быть удалены
        assert '👋' not in latin_stream.written[0]


def test_safe_stream_handler_emit_exception():
    """Тест обработки исключений в SafeStreamHandler"""
    # Патчим os.makedirs ПЕРЕД импортом модуля
    with patch('os.makedirs'):
        # Импортируем заново
        import log_config
        from log_config import SafeStreamHandler
        
        # Создаем поток с исключением
        class BrokenStream:
            def write(self, text):
                raise Exception("Write error")
                
            def flush(self):
                pass
        
        stream = BrokenStream()
        handler = SafeStreamHandler(stream)
        handler.setFormatter(logging.Formatter('%(message)s'))
        
        # Создаем запись
        record = logging.LogRecord(
            name='test',
            level=logging.INFO,
            pathname='',
            lineno=0,
            msg='Тест',
            args=(),
            exc_info=None
        )
        
        # Не должно вызывать исключение
        try:
            handler.emit(record)
            # Если мы здесь, значит исключение было обработано
            assert True
        except Exception:
            pytest.fail("Handler should handle exceptions internally")


def test_setup_logging_debug_false():
    """Тест настройки логирования с DEBUG=false"""
    with patch.dict(os.environ, {'DEBUG': 'false'}, clear=True):
        # Патчим os.makedirs ПЕРЕД импортом модуля
        with patch('os.makedirs') as mock_makedirs:
            # Теперь импортируем модуль
            import log_config
            
            # Создаем мок для RotatingFileHandler
            mock_file_handler = MagicMock(spec=RotatingFileHandler)
            mock_file_handler.level = logging.INFO
            
            with patch('log_config.RotatingFileHandler', return_value=mock_file_handler):
                root_logger = log_config.setup_logging()
                
                # Проверяем создание директории (должно быть вызвано при импорте)
                mock_makedirs.assert_called_once_with("logs", exist_ok=True)
                
                # Проверяем наличие консольного handler
                console_handlers = [h for h in root_logger.handlers 
                                  if hasattr(h, '_is_utf8')]
                assert len(console_handlers) == 1
                
                # Проверяем, что файловый handler был настроен
                mock_file_handler.setLevel.assert_called_with(logging.INFO)
                mock_file_handler.setFormatter.assert_called()
                
                # Проверяем глобальную переменную
                assert log_config.DEBUG is False


def test_setup_logging_debug_true():
    """Тест настройки логирования с DEBUG=true"""
    with patch.dict(os.environ, {'DEBUG': 'true'}, clear=True):
        # Патчим os.makedirs ПЕРЕД импортом модуля
        with patch('os.makedirs'):
            # Теперь импортируем модуль
            import log_config
            
            root_logger = log_config.setup_logging()
            
            # Проверяем глобальную переменную
            assert log_config.DEBUG is True
            
            # Проверяем уровень логирования
            assert root_logger.level == logging.DEBUG
            
            # Проверяем консольный handler
            console_handlers = [h for h in root_logger.handlers 
                              if hasattr(h, '_is_utf8')]
            assert len(console_handlers) == 1
            
            # Проверяем отсутствие файловых handlers
            file_handlers = [h for h in root_logger.handlers 
                           if isinstance(h, RotatingFileHandler)]
            assert len(file_handlers) == 0


def test_setup_logging_multiple_calls():
    """Тест многократного вызова setup_logging"""
    with patch.dict(os.environ, {'DEBUG': 'false'}, clear=True):
        # Патчим os.makedirs ПЕРЕД импортом модуля
        with patch('os.makedirs'):
            # Теперь импортируем модуль
            import log_config
            
            # Создаем мок для файлового handler
            mock_file_handler = MagicMock(spec=RotatingFileHandler)
            mock_file_handler.level = logging.INFO
            
            with patch('log_config.RotatingFileHandler', return_value=mock_file_handler):
                # Первый вызов
                root_logger1 = log_config.setup_logging()
                handlers_count1 = len(root_logger1.handlers)
                
                # Второй вызов (должен очистить старые handlers)
                root_logger2 = log_config.setup_logging()
                handlers_count2 = len(root_logger2.handlers)
                
                # Количество handlers должно быть одинаковым
                assert handlers_count1 == handlers_count2


def test_get_logger():
    """Тест получения логгера"""
    # Патчим os.makedirs ПЕРЕД импортом модуля
    with patch('os.makedirs'):
        # Теперь импортируем модуль
        import log_config
        from log_config import get_logger
        
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"
        
        # Проверяем, что это тот же логгер, что и из стандартного модуля
        assert logger is logging.getLogger("test.module")


def test_log_startup_info_windows():
    """Тест записи информации о запуске на Windows"""
    # Патчим os.makedirs ПЕРЕД импортом модуля
    with patch('os.makedirs'):
        # Теперь импортируем модуль
        import log_config
        from log_config import log_startup_info
        
        with patch('sys.platform', 'win32'):
            with patch.dict(os.environ, {'DEBUG': 'false'}, clear=True):
                # Мокаем root логгер
                mock_logger = MagicMock()
                mock_info = MagicMock()
                mock_logger.info = mock_info
                
                with patch('logging.getLogger', return_value=mock_logger):
                    log_startup_info("TestApp")
                    
                    # Проверяем вызовы
                    assert mock_info.call_count == 4
                    
                    # Проверяем первый вызов с правильным символом для Windows
                    first_call_args = mock_info.call_args_list[0][0][0]
                    assert "[START] TestApp startup" in str(first_call_args)


def test_log_startup_info_linux():
    """Тест записи информации о запуске на Linux"""
    # Патчим os.makedirs ПЕРЕД импортом модуля
    with patch('os.makedirs'):
        # Теперь импортируем модуль
        import log_config
        from log_config import log_startup_info
        
        with patch('sys.platform', 'linux'):
            with patch.dict(os.environ, {'DEBUG': 'true'}, clear=True):
                mock_logger = MagicMock()
                mock_info = MagicMock()
                mock_logger.info = mock_info
                
                with patch('logging.getLogger', return_value=mock_logger):
                    log_startup_info("TestApp")
                    
                    # Проверяем вызовы
                    calls = mock_info.call_args_list
                    assert len(calls) == 4
                    
                    # Проверяем символ запуска для Linux
                    first_call_args = calls[0][0][0]
                    assert "🚀 TestApp startup" in str(first_call_args)


def test_log_shutdown_info_windows():
    """Тест записи информации о завершении на Windows"""
    # Патчим os.makedirs ПЕРЕД импортом модуля
    with patch('os.makedirs'):
        # Теперь импортируем модуль
        import log_config
        from log_config import log_shutdown_info
        
        with patch('sys.platform', 'win32'):
            mock_logger = MagicMock()
            mock_info = MagicMock()
            mock_logger.info = mock_info
            
            with patch('logging.getLogger', return_value=mock_logger):
                log_shutdown_info("TestApp")
                
                mock_info.assert_called_once()
                call_args = mock_info.call_args[0][0]
                assert "[END] TestApp shutdown" in str(call_args)


def test_log_shutdown_info_macos():
    """Тест записи информации о завершении на macOS"""
    # Патчим os.makedirs ПЕРЕД импортом модуля
    with patch('os.makedirs'):
        # Теперь импортируем модуль
        import log_config
        from log_config import log_shutdown_info
        
        with patch('sys.platform', 'darwin'):  # macOS
            mock_logger = MagicMock()
            mock_info = MagicMock()
            mock_logger.info = mock_info
            
            with patch('logging.getLogger', return_value=mock_logger):
                log_shutdown_info("TestApp")
                
                mock_info.assert_called_once()
                call_args = mock_info.call_args[0][0]
                assert "👋 TestApp shutdown" in str(call_args)


@pytest.mark.parametrize("debug_value,expected", [
    ('true', True),
    ('True', True),
    ('TRUE', True),
    ('false', False),
    ('False', False),
    ('FALSE', False),
    ('', False),
    ('invalid', False),
])
def test_debug_env_var_parsing(debug_value, expected):
    """Тест парсинга переменной окружения DEBUG"""
    with patch.dict(os.environ, {'DEBUG': debug_value}, clear=True):
        # Патчим os.makedirs ПЕРЕД импортом модуля
        with patch('os.makedirs'):
            # Теперь импортируем модуль с установленной переменной окружения
            import log_config
            
            # Для случая DEBUG=false мокаем файловый handler
            if not expected:
                mock_file_handler = MagicMock(spec=RotatingFileHandler)
                mock_file_handler.level = logging.INFO
                with patch('log_config.RotatingFileHandler', return_value=mock_file_handler):
                    log_config.setup_logging()
            else:
                log_config.setup_logging()
            
            # Проверяем значение глобальной переменной
            assert log_config.DEBUG == expected, f"DEBUG={debug_value} should be {expected}"


def test_logging_output_format():
    """Тест формата вывода логов"""
    with patch.dict(os.environ, {'DEBUG': 'false'}, clear=True):
        # Патчим os.makedirs ПЕРЕД импортом модуля
        with patch('os.makedirs'):
            # Теперь импортируем модуль
            import log_config
            
            # Захватываем stdout
            captured_output = io.StringIO()
            
            # Создаем мок для файлового handler
            mock_file_handler = MagicMock(spec=RotatingFileHandler)
            mock_file_handler.level = logging.INFO
            
            with patch('log_config.RotatingFileHandler', return_value=mock_file_handler):
                # Используем реальный sys.stdout для теста
                with patch('sys.stdout', captured_output):
                    root_logger = log_config.setup_logging()
                    
                    # Получаем вывод (инициализационное сообщение)
                    output = captured_output.getvalue()
                    
                    # Проверяем базовый формат
                    assert " - " in output
                    assert "Logger initialized" in output
                    
                    # Проверяем наличие временной метки
                    lines = output.strip().split('\n')
                    for line in lines:
                        if line:
                            parts = line.split(' - ')
                            assert len(parts) >= 4


def test_rotating_file_handler_config():
    """Тест конфигурации RotatingFileHandler"""
    with patch.dict(os.environ, {'DEBUG': 'false'}, clear=True):
        # Патчим os.makedirs ПЕРЕД импортом модуля
        with patch('os.makedirs'):
            # Теперь импортируем модуль
            import log_config
            
            # Создаем мок для файлового handler с нужными атрибутами
            mock_file_handler = MagicMock(spec=RotatingFileHandler)
            mock_file_handler.level = logging.INFO
            
            with patch('log_config.RotatingFileHandler', return_value=mock_file_handler) as mock_handler_class:
                log_config.setup_logging()
                
                # Проверяем параметры вызова RotatingFileHandler
                mock_handler_class.assert_called_once_with(
                    'logs/bot.log',
                    maxBytes=10*1024*1024,
                    backupCount=5,
                    encoding='utf-8'
                )
                
                # Проверяем настройки handler
                mock_file_handler.setLevel.assert_called_with(logging.INFO)
                mock_file_handler.setFormatter.assert_called()


def test_safe_stream_handler_init():
    """Тест инициализации SafeStreamHandler"""
    # Патчим os.makedirs ПЕРЕД импортом модуля
    with patch('os.makedirs'):
        # Теперь импортируем модуль
        import log_config
        from log_config import SafeStreamHandler
        
        # Тест с потоком без атрибута encoding
        mock_stream = MagicMock()
        # Удаляем атрибут encoding
        if hasattr(mock_stream, 'encoding'):
            delattr(mock_stream, 'encoding')
        
        handler = SafeStreamHandler(mock_stream)
        assert handler._is_utf8 is True  # По умолчанию UTF-8
        
        # Тест с UTF-8 потоком
        mock_stream_utf8 = MagicMock()
        mock_stream_utf8.encoding = 'UTF-8'
        
        handler2 = SafeStreamHandler(mock_stream_utf8)
        assert handler2._is_utf8 is True
        
        # Тест с Latin-1 потоком
        mock_stream_latin = MagicMock()
        mock_stream_latin.encoding = 'latin-1'
        
        handler3 = SafeStreamHandler(mock_stream_latin)
        assert handler3._is_utf8 is False


def test_logger_hierarchy():
    """Тест иерархии логгеров"""
    # Патчим os.makedirs ПЕРЕД импортом модуля
    with patch('os.makedirs'):
        # Теперь импортируем модуль
        import log_config
        from log_config import get_logger
        
        root_logger = logging.getLogger()
        child_logger = get_logger("parent.child")
        
        # Проверяем, что child_logger наследует настройки root
        assert child_logger.parent == root_logger
        
        # Проверяем propagate (по умолчанию True)
        assert child_logger.propagate is True


def test_setup_logging_returns_root_logger():
    """Тест что setup_logging возвращает root логгер"""
    with patch.dict(os.environ, {'DEBUG': 'false'}, clear=True):
        # Патчим os.makedirs ПЕРЕД импортом модуля
        with patch('os.makedirs'):
            # Теперь импортируем модуль
            import log_config
            
            # Мокаем файловый handler
            mock_file_handler = MagicMock(spec=RotatingFileHandler)
            mock_file_handler.level = logging.INFO
            
            with patch('log_config.RotatingFileHandler', return_value=mock_file_handler):
                root_logger = log_config.setup_logging()
                assert root_logger is logging.getLogger()


def test_global_debug_variable():
    """Тест глобальной переменной DEBUG"""
    # Тест 1: Проверяем начальное значение (должно быть False по умолчанию)
    with patch.dict(os.environ, {}, clear=True):
        # Патчим os.makedirs ПЕРЕД импортом модуля
        with patch('os.makedirs'):
            # Теперь импортируем модуль
            import log_config
            # DEBUG должен быть False по умолчанию (определен в начале файла)
            assert log_config.DEBUG is False
    
    # Тест 2: Проверяем изменение через setup_logging с DEBUG=true
    with patch.dict(os.environ, {'DEBUG': 'true'}, clear=True):
        # Патчим os.makedirs ПЕРЕД импортом модуля
        with patch('os.makedirs'):
            # Теперь импортируем модуль
            import log_config
            
            log_config.setup_logging()
            assert log_config.DEBUG is True
    
    # Тест 3: Проверяем изменение через setup_logging с DEBUG=false
    with patch.dict(os.environ, {'DEBUG': 'false'}, clear=True):
        # Патчим os.makedirs ПЕРЕД импортом модуля
        with patch('os.makedirs'):
            # Теперь импортируем модуль
            import log_config
            
            mock_file_handler = MagicMock(spec=RotatingFileHandler)
            mock_file_handler.level = logging.INFO
            
            with patch('log_config.RotatingFileHandler', return_value=mock_file_handler):
                log_config.setup_logging()
                assert log_config.DEBUG is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])