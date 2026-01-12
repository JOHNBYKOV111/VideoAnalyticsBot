import asyncio
import aiohttp
import uuid
import base64
import ssl
import json
import re
from config import *
from prompts import SQL_PROMPT
from utils import clean_sql
from typing import Optional
from log_config import logger


GIGACHAT_AVAILABLE = bool(GIGACHAT_CLIENT_ID and GIGACHAT_CLIENT_SECRET)


def strip_markdown_sql(s: str) -> str:
    
    s = s.strip()
    if s.startswith("```"):
        s = s[3:].lstrip()
        if s.lower().startswith("sql"):
            s = s[3:].lstrip()
    if s.endswith("```"):
        s = s[:-3].rstrip()
    return s.strip()


def validate_and_fix_sql(sql: str, user_query: str) -> str:
    """
    Проверяет SQL запрос перед выполнением
    """
    sql_upper = sql.upper()
    
    # 1. Проверяем на опасные операции
    dangerous_keywords = ["DELETE", "DROP", "INSERT", "UPDATE", "CREATE", "ALTER", "TRUNCATE"]
    for keyword in dangerous_keywords:
        if keyword in sql_upper:
            raise ValueError(f"Запрещённая операция: {keyword}")
    
    # 2. Поиск по creator_id (заменяем на creator_human_number)
    user_query_lower = user_query.lower()
    
    # Если в запросе есть упоминание "креатор" с цифрой, исправляем SQL
    if "креатор" in user_query_lower or "creator" in user_query_lower:
        # Ищем цифры в запросе пользователя
        numbers = re.findall(r'\d+', user_query)
        if numbers:
            # Заменяем creator_id = 'число' на creator_human_number = число
            for num in numbers:
                # Заменяем строковые сравнения с цифрами
                sql = re.sub(
                    rf"creator_id\s*=\s*['\"]{num}['\"]",
                    f"creator_human_number = {num}",
                    sql,
                    flags=re.IGNORECASE
                )
                # Заменяем ILIKE сравнения
                sql = re.sub(
                    rf"creator_id::TEXT\s+ILIKE\s+['\"]%{num}%['\"]",
                    f"creator_human_number = {num}",
                    sql,
                    flags=re.IGNORECASE
                )
    
    # 3. Форматирование для человеческих ответов
    # Поле creator_human_number в SELECT если его нет
    if "SELECT" in sql_upper and "creator_human_number" not in sql_upper:
        # Проверяем, выбираем ли мы все поля или конкретные
        if "SELECT *" in sql_upper:
            # Не меняем - оставляем как есть
            pass
        elif "SELECT" in sql_upper and "FROM videos" in sql_upper:
            # Если это SELECT по videos, но не выбираем human_number - добавляем
            if "COUNT" not in sql_upper and "AVG" not in sql_upper and "SUM" not in sql_upper:
                # Простой SELECT без агрегации - добавляем human_number
                sql = sql.replace("SELECT", "SELECT creator_human_number,", 1)
    
    # 4. Проверяем ORDER BY и LIMIT
    if "ORDER BY" in sql_upper and "LIMIT" not in sql_upper:
        # Если есть сортировка, но нет лимита - добавляем лимит 10
        if "COUNT" not in sql_upper and "AVG" not in sql_upper and "SUM" not in sql_upper:
            sql = sql.rstrip(';') + " LIMIT 10;"
    
    return sql


async def gigachat_to_sql(query: str) -> Optional[str]:
    """
    Конвертирует запрос на естественном языке в SQL для видео-аналитики через GigaChat.
    """
    if not GIGACHAT_AVAILABLE:
        logger.warning("GigaChat keys missing")
        return None

    connector = aiohttp.TCPConnector(ssl=False, limit=10)
    timeout = aiohttp.ClientTimeout(total=20)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # 1. Получаем access token
        credentials = f"{GIGACHAT_CLIENT_ID}:{GIGACHAT_CLIENT_SECRET}"
        auth_b64 = base64.b64encode(credentials.encode()).decode()

        token_headers = {
            "Authorization": f"Basic {auth_b64}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        token_data = {"scope": "GIGACHAT_API_PERS"}

        token_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        token_resp = await session.post(token_url, headers=token_headers, data=token_data)

        if token_resp.status != 200:
            text = await token_resp.text()
            logger.error(f"Token failed: {token_resp.status} | {text[:300]}")
            return None

        tokens = await token_resp.json()
        access_token = tokens.get("access_token")
        if not access_token:
            logger.error("No access_token in token response")
            return None

        # 2. Формируем промпт под SQL ИЗ SQL_PROMPT
        prompt = SQL_PROMPT.format(user_query=query)
        logger.info(f"GigaChat prompt for: '{query}'")

        chat_payload = {
            "model": "GigaChat-2-Pro",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 512,
            "temperature": 0.1,
            "n": 1,
            "stream": False,
            "repetition_penalty": 1,
            "update_interval": 0,
        }

        chat_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
        }

        chat_url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        
        try:
            chat_resp = await session.post(chat_url, headers=chat_headers, json=chat_payload)
        except Exception as e:
            logger.error(f"GigaChat connection error: {e}")
            return None

        logger.info(f"GigaChat status: {chat_resp.status}")
        if chat_resp.status != 200:
            text = await chat_resp.text()
            logger.error(f"GigaChat {chat_resp.status}: {text[:500]}")
            return None

        try:
            data = await chat_resp.json()
        except Exception as e:
            text = await chat_resp.text()
            logger.error(f"GigaChat JSON parse error: {e} | {text[:500]}")
            return None

        if not data.get("choices"):
            logger.error(f"GigaChat empty choices: {data}")
            return None

        # 🎯 Универсальный парсер контента
        sql_raw = None
        try:
            def get_nested_content(obj):
                if isinstance(obj, dict) and "content" in obj:
                    return obj["content"]
                if isinstance(obj, list):
                    for item in obj:
                        result = get_nested_content(item)
                        if result:
                            return result
                if isinstance(obj, dict):
                    for v in obj.values():
                        result = get_nested_content(v)
                        if result:
                            return result
                return None

            sql_raw = get_nested_content(data)
            sql_raw = sql_raw.strip() if sql_raw else ""
            logger.info(f"GigaChat raw SQL: {sql_raw[:100]}...")
        except Exception as e:
            logger.error(f"Parse error: {e}")
            return None

        if not sql_raw:
            logger.error("GigaChat no SQL content")
            return None

        sql_stripped = strip_markdown_sql(sql_raw)

        try:
            sql_clean = clean_sql(sql_stripped)
        except Exception as e:
            logger.error(f"clean_sql failed: {e} | {sql_stripped}")
            return None

        if not sql_clean.upper().startswith("SELECT"):
            logger.warning(f"GigaChat SQL not SELECT: {sql_clean[:200]}")
            return None

        # 3. Валидируем и исправляем SQL
        try:
            sql_final = validate_and_fix_sql(sql_clean, query)
            logger.info(f"GigaChat final SQL: {sql_final}")
            return sql_final
        except ValueError as e:
            logger.error(f"SQL validation error: {e}")
            return None
        except Exception as e:
            logger.error(f"SQL fix error: {e}")
            return sql_clean