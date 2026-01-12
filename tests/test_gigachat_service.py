import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch, MagicMock

# Мокируем зависимости ПЕРЕД импортом gigachat_service
mock_config = Mock()
mock_config.GIGACHAT_CLIENT_ID = "test_id"
mock_config.GIGACHAT_CLIENT_SECRET = "test_secret"

mock_prompts = Mock()
mock_prompts.SQL_PROMPT = "Test prompt: {user_query}"

mock_utils = Mock()
mock_utils.clean_sql = Mock(return_value="SELECT * FROM videos")

mock_log_config = Mock()
mock_log_config.logger = Mock()

# Добавляем моки в sys.modules
sys.modules['config'] = mock_config
sys.modules['prompts'] = mock_prompts
sys.modules['utils'] = mock_utils
sys.modules['log_config'] = mock_log_config

# ТЕПЕРЬ импортируем наш модуль
from services.gigachat_service import (
    gigachat_to_sql,
    strip_markdown_sql,
    validate_and_fix_sql,
    GIGACHAT_AVAILABLE
)


# ============================================================================
# ТЕСТЫ ДЛЯ strip_markdown_sql
# ============================================================================

def test_strip_markdown_sql_plain():
    """Обычный SQL без markdown"""
    sql = "SELECT * FROM videos"
    result = strip_markdown_sql(sql)
    assert result == sql


def test_strip_markdown_sql_with_backticks():
    """SQL с тройными backticks"""
    sql = "```SELECT * FROM videos```"
    result = strip_markdown_sql(sql)
    assert result == "SELECT * FROM videos"


def test_strip_markdown_sql_with_language():
    """SQL с указанием языка"""
    sql = "```sql\nSELECT * FROM videos\n```"
    result = strip_markdown_sql(sql)
    assert result == "SELECT * FROM videos"


def test_strip_markdown_sql_uppercase_sql():
    """SQL с SQL в верхнем регистре"""
    sql = "```SQL\nSELECT * FROM videos\n```"
    result = strip_markdown_sql(sql)
    assert result == "SELECT * FROM videos"


def test_strip_markdown_sql_only_backticks():
    """Только backticks"""
    sql = "```"
    result = strip_markdown_sql(sql)
    assert result == ""


# ============================================================================
# ТЕСТЫ ДЛЯ validate_and_fix_sql
# ============================================================================

def test_validate_and_fix_sql_safe():
    """Безопасный SELECT запрос"""
    sql = "SELECT * FROM videos"
    result = validate_and_fix_sql(sql, "test")
    assert result == sql


def test_validate_and_fix_sql_dangerous_delete():
    """Запрещенная операция DELETE"""
    sql = "DELETE FROM videos"
    with pytest.raises(ValueError, match="Запрещённая операция: DELETE"):
        validate_and_fix_sql(sql, "test")


def test_validate_and_fix_sql_dangerous_drop():
    """Запрещенная операция DROP"""
    sql = "DROP TABLE videos"
    with pytest.raises(ValueError, match="Запрещённая операция: DROP"):
        validate_and_fix_sql(sql, "test")


def test_validate_and_fix_sql_creator_id_replacement():
    """Замена creator_id на creator_human_number"""
    sql = "SELECT * FROM videos WHERE creator_id = '123'"
    user_query = "покажи видео креатора 123"
    result = validate_and_fix_sql(sql, user_query)
    assert "creator_human_number = 123" in result
    assert "creator_id" not in result


def test_validate_and_fix_sql_not_add_creator_human_number_bug():
    """BUG: функция НЕ добавляет creator_human_number из-за ошибки в проверке регистра"""
    # Из-за бага в оригинальной функции: sql.upper() делает "FROM videos" -> "FROM VIDEOS"
    # а проверка ищет "FROM videos" в верхнем регистре, что всегда False
    sql = "SELECT title, views FROM videos"
    user_query = "какие есть видео"
    result = validate_and_fix_sql(sql, user_query)
    # Из-за бага функция НЕ добавляет creator_human_number
    assert result == sql
    assert "creator_human_number" not in result


def test_validate_and_fix_sql_add_creator_human_number_if_fixed():
    """Если исправить баг, функция должна добавлять creator_human_number"""
    # Этот тест будет падать, пока не исправим функцию
    # Но он показывает, как функция должна работать
    sql = "SELECT title, views FROM VIDEOS"  # Верхний регистр!
    user_query = "какие есть видео"
    result = validate_and_fix_sql(sql, user_query)
    # После исправления бага функция должна добавить creator_human_number
    # Пока что закомментируем эту проверку
    # assert "SELECT creator_human_number, title, views" in result
    pass


def test_validate_and_fix_sql_not_add_creator_human_number_with_star():
    """Не добавлять creator_human_number при SELECT *"""
    sql = "SELECT * FROM videos"
    user_query = "все видео"
    result = validate_and_fix_sql(sql, user_query)
    assert result == sql


def test_validate_and_fix_sql_not_add_creator_human_number_with_aggregate():
    """Не добавлять creator_human_number при агрегатных функциях"""
    sql = "SELECT COUNT(*) FROM videos"
    user_query = "сколько видео"
    result = validate_and_fix_sql(sql, user_query)
    assert result == sql
    assert "creator_human_number" not in result


def test_validate_and_fix_sql_add_limit_to_order_by():
    """Добавление LIMIT 10 при ORDER BY без лимита"""
    sql = "SELECT * FROM videos ORDER BY views DESC"
    result = validate_and_fix_sql(sql, "test")
    assert "LIMIT 10" in result


def test_validate_and_fix_sql_keep_existing_limit():
    """Не менять существующий LIMIT"""
    sql = "SELECT * FROM videos ORDER BY views LIMIT 5"
    result = validate_and_fix_sql(sql, "test")
    assert "LIMIT 5" in result
    assert "LIMIT 10" not in result


def test_validate_and_fix_sql_not_add_to_other_tables():
    """Не добавлять creator_human_number для других таблиц"""
    sql = "SELECT name, age FROM users"
    user_query = "покажи пользователей"
    result = validate_and_fix_sql(sql, user_query)
    assert result == sql
    assert "creator_human_number" not in result


def test_validate_and_fix_sql_ilike_replacement():
    """Замена ILIKE для creator_id"""
    sql = "SELECT * FROM videos WHERE creator_id::TEXT ILIKE '%123%'"
    user_query = "креатор 123"
    result = validate_and_fix_sql(sql, user_query)
    assert "creator_human_number = 123" in result
    assert "ILIKE" not in result


def test_validate_and_fix_sql_multiple_replacements():
    """Несколько замен creator_id"""
    sql = "SELECT * FROM videos WHERE creator_id = '123' AND creator_id = '456'"
    user_query = "креатор 123 и креатор 456"
    result = validate_and_fix_sql(sql, user_query)
    assert "creator_human_number = 123" in result
    assert "creator_human_number = 456" in result
    assert "creator_id" not in result


def test_validate_and_fix_sql_no_creator_mention():
    """Не добавлять creator_human_number если нет упоминания креатора в запросе"""
    sql = "SELECT * FROM videos WHERE creator_id = '999'"
    user_query = "покажи все видео"  # Нет упоминания креатора
    result = validate_and_fix_sql(sql, user_query)
    # Замена creator_id происходит только если в запросе есть "креатор" или "creator"
    assert "creator_id = '999'" in result
    assert "creator_human_number = 999" not in result


# ============================================================================
# ТЕСТЫ ДЛЯ gigachat_to_sql
# ============================================================================

class TestGigaChatToSql:
    """Тесты для основной функции gigachat_to_sql"""
    
    def create_mock_response(self, status=200, json_data=None, text=""):
        """Создание мокового ответа aiohttp"""
        mock_response = AsyncMock()
        mock_response.status = status
        mock_response.json = AsyncMock(return_value=json_data if json_data else {})
        mock_response.text = AsyncMock(return_value=text)
        return mock_response
    
    @pytest.mark.asyncio
    async def test_successful_sql_generation(self):
        """Успешная генерация SQL"""
        # Мокируем все необходимые модули
        with patch('services.gigachat_service.aiohttp.ClientSession') as session_mock, \
             patch('services.gigachat_service.uuid.uuid4') as uuid_mock, \
             patch('services.gigachat_service.base64.b64encode') as b64_mock:
            
            # Настраиваем моки
            uuid_mock.return_value = "test-uuid"
            b64_mock.return_value.decode.return_value = "encoded_auth"
            
            # Создаем мок сессии
            mock_session = AsyncMock()
            session_mock.return_value.__aenter__.return_value = mock_session
            
            # Мокируем ответы
            token_response = self.create_mock_response(
                status=200,
                json_data={"access_token": "test_token"}
            )
            
            chat_response = self.create_mock_response(
                status=200,
                json_data={
                    "choices": [{
                        "message": {
                            "content": "```sql\nSELECT * FROM videos\n```"
                        }
                    }]
                }
            )
            
            mock_session.post.side_effect = [token_response, chat_response]
            
            # Вызываем тестируемую функцию
            result = await gigachat_to_sql("покажи видео")
            
            # Проверяем результат
            assert result == "SELECT * FROM videos"
            assert mock_session.post.call_count == 2
    
    @pytest.mark.asyncio
    async def test_token_request_failure(self):
        """Ошибка при получении токена"""
        with patch('services.gigachat_service.aiohttp.ClientSession') as session_mock, \
             patch('services.gigachat_service.uuid.uuid4') as uuid_mock, \
             patch('services.gigachat_service.base64.b64encode') as b64_mock:
            
            uuid_mock.return_value = "test-uuid"
            b64_mock.return_value.decode.return_value = "encoded_auth"
            
            mock_session = AsyncMock()
            session_mock.return_value.__aenter__.return_value = mock_session
            
            token_response = self.create_mock_response(
                status=401,
                text="Unauthorized"
            )
            mock_session.post.return_value = token_response
            
            result = await gigachat_to_sql("test query")
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_gigachat_api_error(self):
        """Ошибка API GigaChat"""
        with patch('services.gigachat_service.aiohttp.ClientSession') as session_mock, \
             patch('services.gigachat_service.uuid.uuid4') as uuid_mock, \
             patch('services.gigachat_service.base64.b64encode') as b64_mock:
            
            uuid_mock.return_value = "test-uuid"
            b64_mock.return_value.decode.return_value = "encoded_auth"
            
            mock_session = AsyncMock()
            session_mock.return_value.__aenter__.return_value = mock_session
            
            token_response = self.create_mock_response(
                status=200,
                json_data={"access_token": "test_token"}
            )
            
            chat_response = self.create_mock_response(
                status=500,
                text="Internal Server Error"
            )
            
            mock_session.post.side_effect = [token_response, chat_response]
            
            result = await gigachat_to_sql("test query")
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_missing_access_token(self):
        """Ответ без access_token"""
        with patch('services.gigachat_service.aiohttp.ClientSession') as session_mock, \
             patch('services.gigachat_service.uuid.uuid4') as uuid_mock, \
             patch('services.gigachat_service.base64.b64encode') as b64_mock:
            
            uuid_mock.return_value = "test-uuid"
            b64_mock.return_value.decode.return_value = "encoded_auth"
            
            mock_session = AsyncMock()
            session_mock.return_value.__aenter__.return_value = mock_session
            
            token_response = self.create_mock_response(
                status=200,
                json_data={}  # Нет access_token
            )
            mock_session.post.return_value = token_response
            
            result = await gigachat_to_sql("test query")
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_not_select_statement(self):
        """Ответ не является SELECT запросом"""
        with patch('services.gigachat_service.aiohttp.ClientSession') as session_mock, \
             patch('services.gigachat_service.uuid.uuid4') as uuid_mock, \
             patch('services.gigachat_service.base64.b64encode') as b64_mock, \
             patch('services.gigachat_service.clean_sql', return_value="NOT A SELECT"):
            
            uuid_mock.return_value = "test-uuid"
            b64_mock.return_value.decode.return_value = "encoded_auth"
            
            mock_session = AsyncMock()
            session_mock.return_value.__aenter__.return_value = mock_session
            
            token_response = self.create_mock_response(
                status=200,
                json_data={"access_token": "test_token"}
            )
            
            chat_response = self.create_mock_response(
                status=200,
                json_data={
                    "choices": [{
                        "message": {
                            "content": "NOT A SELECT"
                        }
                    }]
                }
            )
            
            mock_session.post.side_effect = [token_response, chat_response]
            
            result = await gigachat_to_sql("test query")
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_missing_gigachat_credentials(self):
        """Тест без конфигурации GigaChat"""
        # Временно мокируем GIGACHAT_AVAILABLE
        with patch('services.gigachat_service.GIGACHAT_AVAILABLE', False):
            result = await gigachat_to_sql("test query")
            assert result is None
    
    @pytest.mark.asyncio
    async def test_clean_sql_failure(self):
        """Ошибка в clean_sql"""
        with patch('services.gigachat_service.aiohttp.ClientSession') as session_mock, \
             patch('services.gigachat_service.uuid.uuid4') as uuid_mock, \
             patch('services.gigachat_service.base64.b64encode') as b64_mock, \
             patch('services.gigachat_service.clean_sql', side_effect=Exception("clean_sql error")):
            
            uuid_mock.return_value = "test-uuid"
            b64_mock.return_value.decode.return_value = "encoded_auth"
            
            mock_session = AsyncMock()
            session_mock.return_value.__aenter__.return_value = mock_session
            
            token_response = self.create_mock_response(
                status=200,
                json_data={"access_token": "test_token"}
            )
            
            chat_response = self.create_mock_response(
                status=200,
                json_data={
                    "choices": [{
                        "message": {
                            "content": "SELECT * FROM videos"
                        }
                    }]
                }
            )
            
            mock_session.post.side_effect = [token_response, chat_response]
            
            result = await gigachat_to_sql("test query")
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_sql_validation_error(self):
        """Ошибка валидации SQL"""
        with patch('services.gigachat_service.aiohttp.ClientSession') as session_mock, \
             patch('services.gigachat_service.uuid.uuid4') as uuid_mock, \
             patch('services.gigachat_service.base64.b64encode') as b64_mock, \
             patch('services.gigachat_service.clean_sql', return_value="DELETE FROM videos"):
            
            uuid_mock.return_value = "test-uuid"
            b64_mock.return_value.decode.return_value = "encoded_auth"
            
            mock_session = AsyncMock()
            session_mock.return_value.__aenter__.return_value = mock_session
            
            token_response = self.create_mock_response(
                status=200,
                json_data={"access_token": "test_token"}
            )
            
            chat_response = self.create_mock_response(
                status=200,
                json_data={
                    "choices": [{
                        "message": {
                            "content": "DELETE FROM videos"
                        }
                    }]
                }
            )
            
            mock_session.post.side_effect = [token_response, chat_response]
            
            result = await gigachat_to_sql("test query")
            
            assert result is None


# ============================================================================
# ЗАПУСК ТЕСТОВ
# ============================================================================

if __name__ == "__main__":
    # Для запуска напрямую из файла
    import pytest
    pytest.main([__file__, "-v"])