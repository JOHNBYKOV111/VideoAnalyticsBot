import asyncpg
import os
import time
from typing import Dict, Any, Optional
from cachetools import TTLCache
import logging

logger = logging.getLogger(__name__)


class VideoDatabaseManager:
    """Менеджер базы данных для базовых SQL-запросов с кэшированием"""
    
    def __init__(self, db_url: Optional[str] = None, cache_ttl: int = 60):
        """
        Инициализация менеджера БД
        
        Args:
            db_url: URL подключения к БД. Если не указан, берётся из переменной окружения DATABASE_URL
            cache_ttl: Время жизни кэша в секундах (по умолчанию 60)
        """
        self.db_url = db_url or os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/video_stats")
        self.pool: Optional[asyncpg.Pool] = None
        self._cache = TTLCache(maxsize=128, ttl=cache_ttl)
        self._connection_lock = False
        logger.info(f"Инициализирован VideoDatabaseManager с TTL кэша: {cache_ttl}с")
    
    async def connect(self, ssl=None, server_settings=None) -> Optional[asyncpg.Pool]:
        """Создает пул подключений к БД"""
        if self.pool and not self.pool._closed:
            return self.pool
        
        try:
            self.pool = await asyncpg.create_pool(
                dsn=self.db_url,
                min_size=2,
                max_size=5,
                ssl=ssl,
                server_settings=server_settings or {
                    'application_name': 'video_stats_manager'
                }
            )
            logger.info("Пул подключений к БД успешно создан")
            return self.pool
        except Exception as e:
            logger.error(f"Ошибка подключения к БД: {e}")
            self.pool = None
            return None
    
    async def close(self):
        """Закрывает соединение с БД"""
        if self.pool and not self.pool._closed:
            await self.pool.close()
            self.pool = None
            logger.info("Соединение с БД закрыто")
    
    def _get_cached(self, key: str) -> Any:
        """Получает значение из кэша"""
        try:
            return self._cache[key]
        except KeyError:
            return None
    
    def _set_cached(self, key: str, value: Any):
        """Сохраняет значение в кэш"""
        self._cache[key] = value
    
    # ========== ОБЩИЕ ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========
    
    async def _get_cached_count(self, cache_key: str, query: str) -> int:
        """
        Общий метод для получения кэшированного количества
        
        Args:
            cache_key: Ключ для кэша
            query: SQL запрос для выполнения
            
        Returns:
            Результат запроса или 0 при ошибке
        """
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        pool = await self.connect()
        if not pool:
            return 0
        
        try:
            async with pool.acquire() as conn:
                result = await conn.fetchval(query)
                count = result or 0
                self._set_cached(cache_key, count)
                return count
        except Exception as e:
            logger.error(f"Ошибка при выполнении запроса {query}: {e}")
            return 0
    
    # ========== БАЗОВЫЕ ЗАПРОСЫ ==========
    
    async def get_total_videos_count(self) -> int:
        """Сколько всего видео есть в системе?"""
        return await self._get_cached_count(
            "total_videos",
            "SELECT COUNT(*) FROM videos;"
        )
    
    async def get_total_creators_count(self) -> int:
        """Сколько всего креаторов есть в системе?"""
        return await self._get_cached_count(
            "total_creators",
            "SELECT COUNT(DISTINCT creator_id) FROM videos;"
        )
    
    async def get_total_snapshots_count(self) -> int:
        """Сколько всего снапшотов есть в системе?"""
        return await self._get_cached_count(
            "total_snapshots",
            "SELECT COUNT(*) FROM video_snapshots;"
        )
    
    async def get_total_reports_count(self) -> int:
        """
        Сколько всего жалоб есть в системе?
        Примечание: В зависимости от структуры БД может потребоваться изменить запрос
        """
        # Вариант 1: Если жалобы хранятся в отдельной таблице
        # return await self._get_cached_count(
        #     "total_reports",
        #     "SELECT COUNT(*) FROM reports;"
        # )
        
        # Вариант 2: Если количество жалоб хранится в videos
        return await self._get_cached_count(
            "total_reports",
            "SELECT SUM(reports_count) FROM videos;"
        )
    
    async def get_total_likes_count(self) -> int:
        """Сколько всего лайков?"""
        return await self._get_cached_count(
            "total_likes",
            "SELECT SUM(likes_count) FROM videos;"
        )
    
    async def get_total_comments_count(self) -> int:
        """Сколько всего комментариев?"""
        return await self._get_cached_count(
            "total_comments",
            "SELECT SUM(comments_count) FROM videos;"
        )
    
    async def get_total_views_count(self) -> int:
        """Сколько всего просмотров?"""
        return await self._get_cached_count(
            "total_views",
            "SELECT SUM(views_count) FROM videos;"
        )
    
    async def get_all_basic_stats(self) -> Dict[str, int]:
        """Получает ВСЕ базовые статистики одним запросом"""
        cache_key = "all_basic_stats"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        pool = await self.connect()
        if not pool:
            return {
                "total_videos": 0,
                "total_creators": 0,
                "total_views": 0,
                "total_likes": 0,
                "total_comments": 0,
                "total_reports": 0,
                "total_snapshots": 0
            }
        
        try:
            async with pool.acquire() as conn:
                # Единый запрос для всех статистик
                result = await conn.fetchrow('''
                    SELECT
                        (SELECT COUNT(*) FROM videos) AS total_videos,
                        (SELECT COUNT(DISTINCT creator_id) FROM videos) AS total_creators,
                        (SELECT SUM(views_count) FROM videos) AS total_views,
                        (SELECT SUM(likes_count) FROM videos) AS total_likes,
                        (SELECT SUM(comments_count) FROM videos) AS total_comments,
                        (SELECT SUM(reports_count) FROM videos) AS total_reports,
                        (SELECT COUNT(*) FROM video_snapshots) AS total_snapshots;
                ''')
                
                stats = {
                    "total_videos": result["total_videos"] or 0,
                    "total_creators": result["total_creators"] or 0,
                    "total_views": result["total_views"] or 0,
                    "total_likes": result["total_likes"] or 0,
                    "total_comments": result["total_comments"] or 0,
                    "total_reports": result["total_reports"] or 0,
                    "total_snapshots": result["total_snapshots"] or 0
                }
                
                self._set_cached(cache_key, stats)
                return stats
                
        except Exception as e:
            logger.error(f"Ошибка при получении всех статистик: {e}")
            return {
                "total_videos": 0,
                "total_creators": 0,
                "total_views": 0,
                "total_likes": 0,
                "total_comments": 0,
                "total_reports": 0,
                "total_snapshots": 0
            }
    
    # ========== ДОПОЛНИТЕЛЬНЫЕ МЕТОДЫ ==========
    
    async def get_video_stats(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Получает статистику конкретного видео"""
        pool = await self.connect()
        if not pool:
            return None
        
        try:
            async with pool.acquire() as conn:
                result = await conn.fetchrow('''
                    SELECT
                        video_id, creator_id, title, views_count,
                        likes_count, comments_count, reports_count,
                        created_at, updated_at
                    FROM videos
                    WHERE video_id = $1;
                ''', video_id)
                
                if result:
                    return dict(result)
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при получении статистики видео {video_id}: {e}")
            return None
    
    async def get_top_creators(self, limit: int = 10) -> list:
        """Получает топ креаторов по количеству видео"""
        pool = await self.connect()
        if not pool:
            return []
        
        try:
            async with pool.acquire() as conn:
                results = await conn.fetch('''
                    SELECT
                        creator_id,
                        COUNT(*) as video_count,
                        SUM(views_count) as total_views,
                        SUM(likes_count) as total_likes
                    FROM videos
                    GROUP BY creator_id
                    ORDER BY video_count DESC
                    LIMIT $1;
                ''', limit)
                
                return [dict(row) for row in results]
                
        except Exception as e:
            logger.error(f"Ошибка при получении топ креаторов: {e}")
            return []
    
    async def get_recent_snapshots(self, limit: int = 5) -> list:
        """Получает последние снапшоты"""
        pool = await self.connect()
        if not pool:
            return []
        
        try:
            async with pool.acquire() as conn:
                results = await conn.fetch('''
                    SELECT
                        vs.*,
                        v.title as video_title
                    FROM video_snapshots vs
                    LEFT JOIN videos v ON vs.video_id = v.video_id
                    ORDER BY vs.created_at DESC
                    LIMIT $1;
                ''', limit)
                
                return [dict(row) for row in results]
                
        except Exception as e:
            logger.error(f"Ошибка при получении последних снапшотов: {e}")
            return []
    
    # ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========
    
    async def clear_cache(self):
        """Очищает кэш"""
        self._cache.clear()
        logger.info("Кэш очищен")
    
    async def test_connection(self, check_tables: bool = False) -> bool:
        """Проверяет соединение с БД и опционально наличие таблиц"""
        try:
            pool = await self.connect()
            if not pool:
                return False
            
            async with pool.acquire() as conn:
                # Базовая проверка соединения
                await conn.fetchval("SELECT 1")
                
                # Дополнительная проверка таблиц
                if check_tables:
                    required_tables = ['videos', 'video_snapshots']
                    for table in required_tables:
                        exists = await conn.fetchval('''
                            SELECT EXISTS (
                                SELECT FROM information_schema.tables
                                WHERE table_name = $1
                            );
                        ''', table)
                        
                        if not exists:
                            logger.warning(f"Таблица {table} не найдена в БД")
                            return False
                
                logger.info("Проверка соединения с БД пройдена успешно")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка при проверке соединения: {e}")
            return False
    
    async def get_database_info(self) -> Dict[str, Any]:
        """Получает информацию о БД"""
        pool = await self.connect()
        if not pool:
            return {"error": "Нет соединения с БД"}
        
        try:
            async with pool.acquire() as conn:
                # Версия PostgreSQL
                version = await conn.fetchval("SELECT version();")
                
                # Размер БД
                db_size = await conn.fetchval("SELECT pg_database_size(current_database());")
                
                # Количество активных соединений
                active_connections = await conn.fetchval("SELECT COUNT(*) FROM pg_stat_activity;")
                
                return {
                    "version": version.split(",")[0] if version else "Неизвестно",
                    "database_size_mb": round(db_size / (1024 * 1024), 2) if db_size else 0,
                    "active_connections": active_connections or 0,
                    "cache_size": len(self._cache),
                    "cache_hits": self._cache.hits if hasattr(self._cache, 'hits') else 0,
                    "cache_misses": self._cache.mishes if hasattr(self._cache, 'misses') else 0
                }
                
        except Exception as e:
            logger.error(f"Ошибка при получении информации о БД: {e}")
            return {"error": str(e)}
    
    async def __aenter__(self):
        """Поддержка контекстного менеджера"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Поддержка контекстного менеджера"""
        await self.close()


# Пример использования
async def example_usage():
    """Пример использования VideoDatabaseManager"""
    
    # Способ 1: Использование переменной окружения
    os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost:5432/video_stats"
    db_manager = VideoDatabaseManager()
    
    # Способ 2: Явная передача URL
    # db_manager = VideoDatabaseManager("postgresql://user:pass@localhost:5432/video_stats")
    
    # Проверка соединения
    if await db_manager.test_connection(check_tables=True):
        print("✅ Соединение с БД установлено")
        
        # Получение всех статистик
        stats = await db_manager.get_all_basic_stats()
        print(f"📊 Всего видео: {stats['total_videos']}")
        print(f"👥 Всего креаторов: {stats['total_creators']}")
        print(f"👁️ Всего просмотров: {stats['total_views']}")
        
        # Получение отдельных статистик
        total_likes = await db_manager.get_total_likes_count()
        print(f"👍 Всего лайков: {total_likes}")
        
        # Получение информации о БД
        db_info = await db_manager.get_database_info()
        print(f"🗄️ Размер БД: {db_info.get('database_size_mb', 0)} MB")
        
        # Очистка кэша
        await db_manager.clear_cache()
        print("🧹 Кэш очищен")
        
    else:
        print("❌ Ошибка подключения к БД")
    
    # Закрытие соединения
    await db_manager.close()
    
    # Использование контекстного менеджера
    async with VideoDatabaseManager() as db:
        stats = await db.get_all_basic_stats()
        print(f"Использование через контекстный менеджер: {stats['total_videos']} видео")


if __name__ == "__main__":
    import asyncio
    
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Запуск примера
    asyncio.run(example_usage())