import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import asyncpg
import logging
import asyncio
from enum import Enum
from textwrap import dedent
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from contextlib import asynccontextmanager

# ========== ЯВНЫЙ ИМПОРТ ИЗ CONFIG.PY ==========
try:
    from config import GIGACHAT_AVAILABLE, GIGACHAT_CLIENT_SECRET
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning("[DateAIManager] config.py не найден или не содержит GigaChat настроек")
    GIGACHAT_AVAILABLE = False
    GIGACHAT_CLIENT_SECRET = None
# ================================================

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)


@dataclass
class DataPeriod:
    """Конфигурация периодов данных"""
    video_creation_start: datetime  # август
    video_creation_end: datetime    # октябрь
    stats_start: datetime          # ноябрь
    stats_end: datetime            # декабрь
    target_year: int


class PeriodType(Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    CUSTOM = "custom"
    ALL_TIME = "all_time"


class DataType(Enum):
    VIDEO_CREATION = "video_creation"  # только создание (август-октябрь)
    STATS_ONLY = "stats_only"          # только статистика (ноябрь-декабрь)
    MIXED = "mixed"                    # смешанный
    NONE = "none"                      # нет данных


# ========== ASYNC GIGACHAT CLIENT ==========

class AsyncGigaChatClient:
    """Асинхронный клиент для работы с GigaChat API"""
    
    def __init__(self, client_secret: str, max_workers: int = 2):
        self.client_secret = client_secret
        self.giga = None
        self.initialized = False
        self.last_request_time = 0
        self.request_lock = asyncio.Lock()
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="gigachat_")
        self.logger = logger.getChild("gigachat")

    async def initialize(self):
        """Инициализация GigaChat"""
        try:
            from gigachat import GigaChat
            from gigachat.models import Chat, Messages, MessagesRole

            self.giga = GigaChat(
                credentials=self.client_secret,
                verify_ssl_certs=False,
                model="GigaChat-2",
                timeout=45
            )
            self.initialized = True
            self.logger.info("GigaChat-2 объект создан")
        except ImportError:
            self.logger.error("gigachat-библиотека не установлена")
            self.initialized = False
        except Exception as e:
            self.logger.error(f"Ошибка инициализации: {e}")
            self.initialized = False

    async def _make_request(self, prompt: str, max_retries: int = 3) -> str:
        if not self.initialized:
            await self.initialize()
            if not self.initialized:
                return "GigaChat не инициализирован"

        async with self.request_lock:
            try:
                from gigachat.models import Chat, Messages, MessagesRole

                # Контроль частоты запросов
                current_time = time.time()
                time_since_last = current_time - self.last_request_time
                if time_since_last < 1.0:
                    await asyncio.sleep(1.0 - time_since_last)

                messages = Messages(role=MessagesRole.USER, content=prompt.strip())
                chat = Chat(messages=[messages])

                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    self.executor,
                    lambda: self.giga.chat(chat)
                )

                self.last_request_time = time.time()
                result = response.choices[0].message.content
                self.logger.info(f"Ответ получен ({len(result)} символов)")
                return result

            except Exception as e:
                self.logger.error(f"Исключение при запросе к GigaChat: {e}")
                if max_retries > 0:
                    await asyncio.sleep(1)
                    return await self._make_request(prompt, max_retries - 1)
                return "Ошибка подключения к AI"

    async def analyze_statistics(self, prompt: str) -> str:
        return await self._make_request(prompt)

    async def answer_question(self, context: str, question: str) -> str:
        full_prompt = f"{context}\nВопрос: {question}"
        return await self._make_request(full_prompt)

    async def close(self):
        """Закрытие ресурсов с ожиданием завершения потоков"""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=True)
        self.logger.info("Executor остановлен")


# ========== UTILITY FUNCTIONS ==========

def _calculate_period_bounds(start_date: datetime, period_type: PeriodType,
                           end_date: Optional[datetime] = None) -> Optional[Tuple[datetime, datetime]]:
    """Рассчитать границы периода на основе типа и дат"""
    if period_type == PeriodType.DAY and start_date:
        start = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return start, end
        
    elif period_type == PeriodType.WEEK and start_date:
        monday = start_date - timedelta(days=start_date.weekday())
        start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
        return start, end
        
    elif period_type == PeriodType.MONTH and start_date:
        start = start_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start_date.month == 12:
            end = start_date.replace(year=start_date.year + 1, month=1, day=1)
        else:
            end = start_date.replace(month=start_date.month + 1, day=1)
        return start, end
        
    elif period_type == PeriodType.CUSTOM and start_date and end_date:
        if end_date < start_date:
            raise ValueError("Дата окончания периода должна быть позже даты начала")
        start = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = end_date.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return start, end
    
    return None


# ========== MAIN DATABASE MANAGER ==========

class DateAIManager:
    """
    Главный менеджер статистики для реляционной БД.
    """
    
    MAX_CACHE_SIZE = 100
    CACHE_TTL = 300  # 5 минут
    
    def __init__(self, db_config: Dict, gigachat_secret: Optional[str] = None):
        logger.info("[DateAIManager] Инициализация")
        self.db_config = db_config
        self.db_pool: Optional[asyncpg.Pool] = None
        self.giga_client: Optional[AsyncGigaChatClient] = None
        self.data_period: Optional[DataPeriod] = None
        self._initialized = False
        self._init_lock = asyncio.Lock()
        
        # Кэш с TTL
        self._stats_cache: Dict[str, Tuple[Any, float]] = {}
        
        # ========== ЯВНАЯ ПОПЫТКА ИСПОЛЬЗОВАТЬ КЛЮЧ ИЗ CONFIG.PY ==========
        if gigachat_secret is None and GIGACHAT_AVAILABLE and GIGACHAT_CLIENT_SECRET:
            logger.info("[DateAIManager] Использую GigaChat ключ из config.py")
            gigachat_secret = GIGACHAT_CLIENT_SECRET
        
        if gigachat_secret:
            self.giga_client = AsyncGigaChatClient(gigachat_secret)
        elif GIGACHAT_AVAILABLE:
            logger.warning("[DateAIManager] GigaChat доступен, но ключ не указан")
        else:
            logger.info("[DateAIManager] GigaChat отключен в конфиге или не настроен")
        # ===================================================================
        
        self.VIDEO_CREATION_MONTHS = (8, 9, 10)
        self.STATS_MONTHS = (11, 12)

    async def initialize(self) -> bool:
        """Инициализация менеджера"""
        async with self._init_lock:
            if self._initialized:
                return True
            
            try:
                await self._connect_db()
                target_year = await self._determine_target_year()
                
                if not target_year:
                    logger.error("[DateAIManager] Не удалось определить target_year")
                    return False
                
                self.data_period = DataPeriod(
                    video_creation_start=datetime(target_year, 8, 1),
                    video_creation_end=datetime(target_year, 10, 31, 23, 59, 59),
                    stats_start=datetime(target_year, 11, 1),
                    stats_end=datetime(target_year, 12, 31, 23, 59, 59),
                    target_year=target_year
                )
                
                logger.info(f"[DateAIManager] Работаем с данными за {target_year} год")
                
                if self.giga_client:
                    await self.giga_client.initialize()
                
                self._initialized = True
                return True
                
            except Exception as e:
                logger.error(f"[DateAIManager] Ошибка инициализации: {e}", exc_info=True)
                return False

    def _check_initialized(self):
        """Проверка инициализации"""
        if not self._initialized:
            raise RuntimeError("DateAIManager не инициализирован. Вызовите initialize() перед использованием.")

    async def _connect_db(self):
        """Подключение к БД"""
        try:
            self.db_pool = await asyncpg.create_pool(**self.db_config)
            logger.info("[DateAIManager] Подключение к БД установлено")
        except Exception as e:
            logger.error(f"[DateAIManager] Ошибка подключения к БД: {e}")
            raise

    async def _determine_target_year(self) -> Optional[int]:
        """Определить последний год в данных"""
        query = "SELECT MAX(EXTRACT(YEAR FROM video_created_at)) FROM videos"
        async with self.db_pool.acquire() as conn:
            result = await conn.fetchval(query)
            return int(result) if result else None

    # ========== КЭШИРОВАНИЕ ==========

    def _get_cached(self, key: str) -> Optional[Any]:
        """Получить значение из кэша"""
        if key in self._stats_cache:
            value, timestamp = self._stats_cache[key]
            if time.time() - timestamp < self.CACHE_TTL:
                return value
            del self._stats_cache[key]
        return None

    def _set_cached(self, key: str, value: Any):
        """Сохранить значение в кэш"""
        # Очистка устаревших записей
        current_time = time.time()
        expired_keys = [
            k for k, (_, ts) in self._stats_cache.items()
            if current_time - ts >= self.CACHE_TTL
        ]
        
        for k in expired_keys:
            del self._stats_cache[k]
        
        # Ограничение размера
        if len(self._stats_cache) >= self.MAX_CACHE_SIZE:
            oldest_key = min(self._stats_cache.keys(), 
                           key=lambda k: self._stats_cache[k][1])
            del self._stats_cache[oldest_key]
        
        self._stats_cache[key] = (value, current_time)

    async def clear_cache(self):
        """Очистить кэш"""
        self._stats_cache.clear()
        logger.info("[DateAIManager] Кэш очищен")

    # ========== ОСНОВНЫЕ МЕТОДЫ СТАТИСТИКИ ==========

    async def get_daily_stats(self, date: datetime) -> Dict[str, Any]:
        """Статистика за день"""
        self._check_initialized()
        
        if date.year != self.data_period.target_year:
            return self._create_out_of_range_response(date, date)
        
        start, end = self._calculate_day_bounds(date)
        return await self._calculate_stats_for_period(start, end, PeriodType.DAY)

    async def get_weekly_stats(self, start_date: datetime) -> Dict[str, Any]:
        """Статистика за неделю"""
        self._check_initialized()
        
        if start_date.year != self.data_period.target_year:
            return self._create_out_of_range_response(start_date, start_date)
        
        start, end = self._calculate_week_bounds(start_date)
        return await self._calculate_stats_for_period(start, end, PeriodType.WEEK)

    async def get_monthly_stats(self, year: int, month: int) -> Dict[str, Any]:
        """Статистика за месяц"""
        self._check_initialized()
        
        if year != self.data_period.target_year:
            return self._create_out_of_range_response(
                datetime(year, month, 1), datetime(year, month, 28)
            )
        
        start, end = self._calculate_month_bounds(year, month)
        return await self._calculate_stats_for_period(start, end, PeriodType.MONTH)

    async def get_custom_period_stats(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Статистика за произвольный период"""
        self._check_initialized()
        
        if end_date < start_date:
            return {"error": "Дата окончания периода должна быть позже даты начала"}
        
        if start_date.year != self.data_period.target_year or end_date.year != self.data_period.target_year:
            return self._create_out_of_range_response(start_date, end_date)
        
        start = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = end_date.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        
        return await self._calculate_stats_for_period(start, end, PeriodType.CUSTOM)

    # ========== УТИЛИТЫ ДЛЯ РАСЧЕТА ПЕРИОДОВ ==========

    def _calculate_day_bounds(self, date: datetime) -> Tuple[datetime, datetime]:
        """Рассчитать границы дня"""
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return start, end

    def _calculate_week_bounds(self, date: datetime) -> Tuple[datetime, datetime]:
        """Рассчитать границы недели"""
        monday = date - timedelta(days=date.weekday())
        start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
        return start, end

    def _calculate_month_bounds(self, year: int, month: int) -> Tuple[datetime, datetime]:
        """Рассчитать границы месяца"""
        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year + 1, 1, 1)
        else:
            end = datetime(year, month + 1, 1)
        return start, end

    async def _calculate_stats_for_period(self, start: datetime, end: datetime, period_type: PeriodType) -> Dict[str, Any]:
        """Вычислить статистику за период"""
        cache_key = f"{period_type.value}_{start.timestamp()}_{end.timestamp()}"
        
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        data_type = self._get_period_type(start, end)
        
        if data_type == DataType.NONE:
            result = self._create_no_data_response(start, end, period_type, data_type)
            self._set_cached(cache_key, result)
            return result
        
        videos = await self._fetch_videos_in_period(start, end)
        
        if not videos:
            result = self._create_no_data_response(start, end, period_type, data_type)
            self._set_cached(cache_key, result)
            return result
        
        result = self._aggregate_video_stats(videos, start, end, period_type, data_type)
        self._set_cached(cache_key, result)
        
        return result

    def _get_period_type(self, start: datetime, end: datetime) -> DataType:
        """Определить тип данных в периоде"""
        period = self.data_period
        
        if end <= period.video_creation_start or start >= period.stats_end:
            return DataType.NONE
        
        if start >= period.video_creation_start and end <= period.video_creation_end:
            return DataType.VIDEO_CREATION
        
        if start >= period.stats_start and end <= period.stats_end:
            return DataType.STATS_ONLY
        
        return DataType.MIXED

    async def _fetch_videos_in_period(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        """Получить видео с приростом за период"""
        period = self.data_period
        
        # Упрощенный SQL с GREATEST
        query = """
        WITH video_creation AS (
            SELECT
                id,
                creator_human_number AS human_id,
                video_created_at AS created_at,
                CASE
                    WHEN $1 <= video_created_at AND video_created_at < $2
                    THEN 1 ELSE 0
                END AS is_new
            FROM videos
            WHERE video_created_at >= $3 AND video_created_at <= $4
              AND creator_human_number BETWEEN 1 AND 19
        ),
        stats_delta AS (
            SELECT
                s.video_id,
                GREATEST(
                    COALESCE(MAX(s.views_count) FILTER (WHERE s.created_at < $2), 0) -
                    COALESCE(MAX(s.views_count) FILTER (WHERE s.created_at < $1), 0),
                    0
                ) AS views_gained,
                GREATEST(
                    COALESCE(MAX(s.likes_count) FILTER (WHERE s.created_at < $2), 0) -
                    COALESCE(MAX(s.likes_count) FILTER (WHERE s.created_at < $1), 0),
                    0
                ) AS likes_gained
            FROM video_snapshots s
            WHERE s.created_at >= $5 AND s.created_at <= $6
            GROUP BY s.video_id
            HAVING GREATEST(
                COALESCE(MAX(s.views_count) FILTER (WHERE s.created_at < $2), 0) -
                COALESCE(MAX(s.views_count) FILTER (WHERE s.created_at < $1), 0),
                0
            ) > 0
            OR GREATEST(
                COALESCE(MAX(s.likes_count) FILTER (WHERE s.created_at < $2), 0) -
                COALESCE(MAX(s.likes_count) FILTER (WHERE s.created_at < $1), 0),
                0
            ) > 0
        )
        SELECT
            vc.human_id,
            vc.is_new,
            COALESCE(sd.views_gained, 0) AS views_gained,
            COALESCE(sd.likes_gained, 0) AS likes_gained
        FROM video_creation vc
        LEFT JOIN stats_delta sd ON vc.id = sd.video_id
        WHERE vc.is_new = 1 OR sd.video_id IS NOT NULL
        """
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                query,
                start, end,
                period.video_creation_start, period.video_creation_end,
                period.stats_start, period.stats_end
            )
            return [dict(row) for row in rows]

    def _aggregate_video_stats(self, videos: List[Dict], start: datetime, end: datetime,
                              period_type: PeriodType, data_type: DataType) -> Dict[str, Any]:
        """Агрегировать статистику"""
        creator_stats = {}
        total_new_videos = 0
        total_views_gained = 0
        total_likes_gained = 0
        
        for video in videos:
            human_id = video['human_id']
            
            if human_id not in creator_stats:
                creator_stats[human_id] = {
                    'human_id': human_id,
                    'new_videos': 0,
                    'views_gained': 0,
                    'likes_gained': 0
                }
            
            if video['is_new']:
                creator_stats[human_id]['new_videos'] += 1
                total_new_videos += 1
            
            creator_stats[human_id]['views_gained'] += video['views_gained']
            creator_stats[human_id]['likes_gained'] += video['likes_gained']
            total_views_gained += video['views_gained']
            total_likes_gained += video['likes_gained']
        
        top_creators = sorted(
            creator_stats.values(),
            key=lambda x: x['views_gained'],
            reverse=True
        )[:5]
        
        engagement_rate = 0
        if total_views_gained > 0:
            engagement_rate = (total_likes_gained / total_views_gained) * 100
        
        return {
            'period_type': period_type.value,
            'data_type': data_type.value,
            'start_date': start,
            'end_date': end,
            'has_data': True,
            'total_videos_analyzed': len(videos),
            'new_videos': total_new_videos,
            'active_creators': len(creator_stats),
            'views_gained': total_views_gained,
            'likes_gained': total_likes_gained,
            'engagement_rate': round(engagement_rate, 2),
            'top_creators': top_creators,
            'filters_applied': {
                'video_creation_months': 'август-октябрь',
                'stats_months': 'ноябрь-декабрь',
                'year': self.data_period.target_year
            }
        }

    # ========== МЕТОДЫ ДЛЯ КРЕАТОРОВ ==========

    async def get_creator_stats(self, creator_id: int, period_type: PeriodType = PeriodType.ALL_TIME,
                               start_date: Optional[datetime] = None,
                               end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """Статистика для конкретного креатора"""
        self._check_initialized()
        
        if not (1 <= creator_id <= 19):
            return {"error": "creator_id должен быть от 1 до 19"}
        
        # Определяем период
        try:
            if period_type == PeriodType.ALL_TIME:
                start = self.data_period.video_creation_start
                end = self.data_period.stats_end
            else:
                period_bounds = _calculate_period_bounds(start_date, period_type, end_date)
                if not period_bounds:
                    return {"error": "Неверные параметры периода"}
                start, end = period_bounds
        except ValueError as e:
            return {"error": str(e)}
        
        # Получаем данные
        videos = await self._fetch_creator_videos_in_period(creator_id, start, end)
        
        if not videos:
            return {
                "human_id": creator_id,
                "has_data": False,
                "message": "Нет данных за указанный период"
            }
        
        # Агрегируем
        return self._aggregate_creator_stats(creator_id, videos, start, end, period_type)

    async def _fetch_creator_videos_in_period(self, creator_id: int, start: datetime, end: datetime) -> List[Dict]:
        """Получить видео креатора за период"""
        period = self.data_period
        
        query = """
        WITH video_creation AS (
            SELECT
                id,
                CASE
                    WHEN $1 <= video_created_at AND video_created_at < $2
                    THEN 1 ELSE 0
                END AS is_new
            FROM videos
            WHERE creator_human_number = $5
              AND video_created_at >= $3 AND video_created_at <= $4
        ),
        stats_delta AS (
            SELECT
                s.video_id,
                GREATEST(
                    COALESCE(MAX(s.views_count) FILTER (WHERE s.created_at < $2), 0) -
                    COALESCE(MAX(s.views_count) FILTER (WHERE s.created_at < $1), 0),
                    0
                ) AS views_gained,
                GREATEST(
                    COALESCE(MAX(s.likes_count) FILTER (WHERE s.created_at < $2), 0) -
                    COALESCE(MAX(s.likes_count) FILTER (WHERE s.created_at < $1), 0),
                    0
                ) AS likes_gained
            FROM video_snapshots s
            JOIN videos v ON s.video_id = v.id
            WHERE v.creator_human_number = $5
              AND s.created_at >= $6 AND s.created_at <= $7
            GROUP BY s.video_id
            HAVING GREATEST(
                COALESCE(MAX(s.views_count) FILTER (WHERE s.created_at < $2), 0) -
                COALESCE(MAX(s.views_count) FILTER (WHERE s.created_at < $1), 0),
                0
            ) > 0
            OR GREATEST(
                COALESCE(MAX(s.likes_count) FILTER (WHERE s.created_at < $2), 0) -
                COALESCE(MAX(s.likes_count) FILTER (WHERE s.created_at < $1), 0),
                0
            ) > 0
        )
        SELECT
            vc.is_new,
            COALESCE(sd.views_gained, 0) AS views_gained,
            COALESCE(sd.likes_gained, 0) AS likes_gained
        FROM video_creation vc
        LEFT JOIN stats_delta sd ON vc.id = sd.video_id
        WHERE vc.is_new = 1 OR sd.video_id IS NOT NULL
        """
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                query,
                start, end,
                period.video_creation_start, period.video_creation_end,
                creator_id,
                period.stats_start, period.stats_end
            )
            return [dict(row) for row in rows]

    def _aggregate_creator_stats(self, creator_id: int, videos: List[Dict],
                                start: datetime, end: datetime,
                                period_type: PeriodType) -> Dict[str, Any]:
        """Агрегировать статистику креатора"""
        total_new = sum(v['is_new'] for v in videos)
        total_views = sum(v['views_gained'] for v in videos)
        total_likes = sum(v['likes_gained'] for v in videos)
        
        engagement = 0
        if total_views > 0:
            engagement = round((total_likes / total_views) * 100, 2)
        
        return {
            "human_id": creator_id,
            "period_type": period_type.value,
            "start_date": start,
            "end_date": end,
            "has_data": True,
            "total_videos": len(videos),
            "new_videos": total_new,
            "views_gained": total_views,
            "likes_gained": total_likes,
            "engagement_rate": engagement,
            "filters_applied": {
                "video_months": "август-октябрь",
                "stats_months": "ноябрь-декабрь",
                "year": self.data_period.target_year
            }
        }

    async def get_available_creator_ids(self) -> List[int]:
        """Получить всех креаторов 1–19, которые есть в данных"""
        self._check_initialized()
        
        query = """
        SELECT DISTINCT creator_human_number
        FROM videos
        WHERE creator_human_number BETWEEN 1 AND 19
          AND video_created_at >= $1 AND video_created_at <= $2
        ORDER BY creator_human_number
        """
        
        period = self.data_period
        
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(query, period.video_creation_start, period.stats_end)
                return [row['creator_human_number'] for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении доступных креаторов: {e}")
            return []

    # ========== AI МЕТОДЫ ==========

    async def analyze_with_ai(self, stats: Dict[str, Any]) -> str:
        """Анализ статистики с помощью AI"""
        if not self.giga_client:
            return "GigaChat не настроен"
        
        prompt = self._create_ai_prompt(stats)
        return await self.giga_client.analyze_statistics(prompt)

    async def answer_question(self, question: str) -> str:
        """Ответ на вопрос с помощью AI"""
        if not self.giga_client:
            return "GigaChat не настроен"
        
        context = self._create_context_for_question()
        return await self.giga_client.answer_question(context, question)

    def _create_ai_prompt(self, stats: Dict[str, Any]) -> str:
        """Создать промпт для AI"""
        period_type = stats['period_type']
        data_type = stats['data_type']
        
        type_desc = {
            "video_creation": "только создание новых видео (август-октябрь)",
            "stats_only": "только прирост статистики (ноябрь-декабрь)",
            "mixed": "смешанный период"
        }.get(data_type, data_type)
        
        top_creators_text = ""
        for i, creator in enumerate(stats.get('top_creators', [])[:3]):
            medal = ["🥇", "🥈", "🥉"][i]
            top_creators_text += (
                f"{medal} Креатор #{creator['human_id']}: "
                f"+{creator['views_gained']:,} просмотров, "
                f"+{creator['likes_gained']:,} лайков\n"
            )
        
        prompt = dedent(f"""
        Анализ статистики видеоплатформы ({self.data_period.target_year} год):
        
        ВАЖНО: Данные отфильтрованы по требованиям:
        • Создание видео: только август, сентябрь, октябрь {self.data_period.target_year} года
        • Статистика просмотров: только ноябрь, декабрь {self.data_period.target_year} года
        
        ДАННЫЕ ДЛЯ АНАЛИЗА:
        • Период: {period_type.upper()}
        • Тип данных: {type_desc}
        • Даты: {stats['start_date'].strftime('%d.%m.%Y')} - {stats['end_date'].strftime('%d.%m.%Y')}
        
        СТАТИСТИКА:
        • Проанализировано видео: {stats.get('total_videos_analyzed', 0)}
        • Новых видео: {stats.get('new_videos', 0)}
        • Активных креаторов: {stats.get('active_creators', 0)}
        • Прирост просмотров: {stats.get('views_gained', 0):,}
        • Прирост лайков: {stats.get('likes_gained', 0):,}
        • Вовлеченность: {stats.get('engagement_rate', 0)}%
        
        ТОП КРЕАТОРОВ:
        {top_creators_text if top_creators_text else "Нет данных в топе"}
        
        Креаторы обозначены номерами от 1 до 19.
        Дай краткий профессиональный анализ (2-3 предложения).
        """)
        
        return prompt.strip()

    def _create_context_for_question(self) -> str:
        """Создать контекст для вопросов"""
        return dedent(f"""
        КОНТЕКСТ ВИДЕОПЛАТФОРМЫ:
        • Видео: август-октябрь {self.data_period.target_year}
        • Статистика: ноябрь-декабрь {self.data_period.target_year}
        • Креаторы: 1-19
        • Данные хранятся в реляционной БД (таблицы videos, video_snapshots)
        """)

    # ========== УТИЛИТЫ ==========

    async def get_system_info(self) -> Dict[str, Any]:
        """Получить информацию о системе (АСИНХРОННЫЙ)"""
        if not self._initialized:
            return {"error": "Система не инициализирована"}
        
        creators = await self.get_available_creator_ids()
        
        return {
            "data_year": self.data_period.target_year,
            "available_creator_ids": creators,
            "filters": {
                "video_creation": {
                    "months": list(self.VIDEO_CREATION_MONTHS),
                    "start": self.data_period.video_creation_start.strftime('%Y-%m-%d'),
                    "end": self.data_period.video_creation_end.strftime('%Y-%m-%d')
                },
                "stats_collection": {
                    "months": list(self.STATS_MONTHS),
                    "start": self.data_period.stats_start.strftime('%Y-%m-%d'),
                    "end": self.data_period.stats_end.strftime('%Y-%m-%d')
                }
            },
            "gigachat_available": self.giga_client is not None,
            "gigachat_status": "enabled" if (self.giga_client and GIGACHAT_AVAILABLE) else "disabled",
            "cache_size": len(self._stats_cache),
            "cache_ttl": self.CACHE_TTL
        }

    def _create_no_data_response(self, start: datetime, end: datetime,
                                period_type: PeriodType, data_type: DataType) -> Dict[str, Any]:
        """Создать ответ об отсутствии данных"""
        return {
            'period_type': period_type.value,
            'data_type': data_type.value,
            'start_date': start,
            'end_date': end,
            'has_data': False,
            'message': 'Нет данных за указанный период',
            'filters_applied': {
                'video_creation_months': 'август-октябрь',
                'stats_months': 'ноябрь-декабрь',
                'year': self.data_period.target_year
            }
        }

    def _create_out_of_range_response(self, start: datetime, end: datetime) -> Dict[str, Any]:
        """Создать ответ для периода вне диапазона"""
        return {
            'period_type': 'out_of_range',
            'start_date': start,
            'end_date': end,
            'has_data': False,
            'message': f'Период вне диапазона ({self.data_period.target_year} год)',
            'target_year': self.data_period.target_year
        }

    async def close(self):
        """Закрыть все соединения"""
        if self.db_pool:
            await self.db_pool.close()
            logger.info("[DateAIManager] БД закрыта")
        
        if self.giga_client:
            await self.giga_client.close()
            logger.info("[DateAIManager] GigaChat закрыт")
        
        self._initialized = False
        self._stats_cache.clear()


# ========== КОНТЕКСТНЫЙ МЕНЕДЖЕР ==========

@asynccontextmanager
async def date_ai_manager_context(db_config: Dict, gigachat_secret: Optional[str] = None):
    """Контекстный менеджер для DateAIManager"""
    # Проверяем, нужно ли использовать ключ из config.py
    if gigachat_secret is None and GIGACHAT_AVAILABLE and GIGACHAT_CLIENT_SECRET:
        logger.info("[DateAIManager контекст] Использую GigaChat ключ из config.py")
        gigachat_secret = GIGACHAT_CLIENT_SECRET
    
    manager = DateAIManager(db_config, gigachat_secret)
    try:
        await manager.initialize()
        yield manager
    finally:
        await manager.close()


# ========== ПРИМЕР ИСПОЛЬЗОВАНИЯ ==========

async def example_usage():
    """Пример использования"""
    
    db_config = {
        'user': 'postgres',
        'password': 'password',
        'host': 'localhost',
        'port': 5432,
        'database': 'video_stats',
        'min_size': 5,
        'max_size': 20
    }
    
    # Теперь автоматически подхватит ключ из config.py, если он там есть
    async with date_ai_manager_context(db_config) as manager:
        # Теперь get_system_info - асинхронный метод
        info = await manager.get_system_info()
        print(f"Системная информация: {info}")
        
        creators = await manager.get_available_creator_ids()
        print(f"Доступные креаторы: {creators}")
        
        today = datetime.now()
        daily_stats = await manager.get_daily_stats(today)
        print(f"Статистика за день: {daily_stats.get('views_gained', 0)} просмотров")
        
        # AI анализ теперь будет работать, если ключ есть в config.py
        if manager.giga_client:
            ai_analysis = await manager.analyze_with_ai(daily_stats)
            print(f"AI анализ: {ai_analysis}")
        
        # Пример с ошибкой валидации
        bad_stats = await manager.get_custom_period_stats(today, today - timedelta(days=1))
        print(f"Статистика с ошибкой: {bad_stats}")

if __name__ == "__main__":
    asyncio.run(example_usage())