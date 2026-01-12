# src/managers/ai_manager.py
import asyncio
import time
import asyncpg
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import logging

from ..config import GIGACHAT_AVAILABLE, GIGACHAT_CLIENT_SECRET

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)

class AIManager:
    """AI Manager + своя БД"""
    
    def __init__(self, db_url: str = "postgresql://postgres:password@localhost:5432/video_stats"):
        logger.info("[AI] Независимый AI Manager 12.0 запущен")
        self.ai_version = "12.0 Standalone"
        self.last_request_time = 0
        
        # ========== БАЗА ДАННЫХ ==========
        self.db_url = db_url
        self.db_pool = None
        self._db_cache = {}
        self._cache_ttl = 30
        
        # ========== GIGACHAT ==========
        self.giga = None
        self.giga_status = "not_initialized"
        self.active_model = None
        
        if GIGACHAT_AVAILABLE:
            self._initialize_gigachat()
        else:
            logger.warning("[AI] GigaChat отключен в конфиге")
            self.giga_status = "disabled"
        
        # ========== ПРОМПТЫ ==========
        self.prompts = {
            "creator_analysis": """Ты - аналитик видеоплатформы. Проанализируй данные креатора #{creator_id}:

Видео: {videos:,}
Просмотры: {views:,}
Лайки: {likes:,}
Комментарии: {comments:,}
Жалобы: {reports:,}
Снапшоты: {snapshots:,}

Дай краткий анализ (3-4 предложения) и оценку от 1 до 10.""",
            
            "videos_by_views": """Ты - аналитик видеоконтента. Проанализируй статистику:

Всего видео в системе: {total_videos:,}
Видео с {comparison} {threshold:,} просмотров: {count:,} ({percent:.1f}%)
Общее число просмотров: {total_views:,}

Дай краткий анализ распределения просмотров.""",
            
            "extremes_analysis": """Ты - аналитик креаторского сообщества. Проанализируй экстремумы по {metric_ru}:

ЛИДЕР: Креатор #{max_id} - {max_value:,} {metric_ru}
МИНИМУМ: Креатор #{min_id} - {min_value:,} {metric_ru}
РАЗНИЦА: {difference:,} {metric_ru} ({ratio:.1f} раз)
Всего креаторов: {total_creators}

Дай краткий анализ неравномерности.""",
            
            "top_n_analysis": """Ты - специалист по рейтингам. Проанализируй топ-{n} креаторов по {metric_ru}:

{ranking_table}

Доля топ-{n} от общего: {top_n_percent:.1f}%
Всего креаторов: {total_creators}

Дай краткий анализ лидеров (3-4 предложения).""",
            
            "platform_analysis": """Ты - аналитик видеоплатформы. Проанализируй общее состояние:

Видео: {total_videos:,}
Креаторы: {total_creators:,}
Просмотры: {total_views:,}
Лайки: {total_likes:,}
Комментарии: {total_comments:,}
Вовлеченность: {engagement:.1f}%

Дай краткий анализ состояния платформы (4-5 предложений)."""
        }
    
    # ========== МЕТОДЫ ДЛЯ БД ==========
    
    async def _get_db_pool(self):
        """Подключение к PostgreSQL"""
        if self.db_pool is None:
            try:
                self.db_pool = await asyncpg.create_pool(
                    dsn=self.db_url,
                    min_size=2,
                    max_size=5,
                    command_timeout=30
                )
                logger.info("[AI] Создано СВОЕ подключение к PostgreSQL")
            except Exception as e:
                logger.error(f"[AI] Ошибка подключения к БД: {e}")
                raise
        return self.db_pool
    
    def _get_cached(self, key: str) -> Any:
        """СВОЙ кэш"""
        if key in self._db_cache:
            value, timestamp = self._db_cache[key]
            if time.time() - timestamp < self._cache_ttl:
                return value
            else:
                del self._db_cache[key]
        return None
    
    def _set_cached(self, key: str, value: Any):
        """Сохраняет в СВОЙ кэш"""
        self._db_cache[key] = (value, time.time())
    
    # ========== SQL ЗАПРОСЫ ==========
    
    async def _get_all_basic_stats(self) -> Dict[str, int]:
        """Запрос: общая статистика"""
        cache_key = "all_basic_stats"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        pool = await self._get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchrow('''
                SELECT
                    COUNT(*) as total_videos,
                    COUNT(DISTINCT creator_id) as total_creators,
                    SUM(views_count) as total_views,
                    SUM(likes_count) as total_likes,
                    SUM(comments_count) as total_comments,
                    SUM(reports_count) as total_reports
                FROM videos
            ''')
            
            snapshots_result = await conn.fetchval("SELECT COUNT(*) FROM video_snapshots;")
            
            stats = {
                "total_videos": result["total_videos"] or 0,
                "total_creators": result["total_creators"] or 0,
                "total_views": result["total_views"] or 0,
                "total_likes": result["total_likes"] or 0,
                "total_comments": result["total_comments"] or 0,
                "total_reports": result["total_reports"] or 0,
                "total_snapshots": snapshots_result or 0
            }
            
            self._set_cached(cache_key, stats)
            return stats
    
    async def _get_creator_stats(self, creator_id: int) -> Optional[Dict]:
        """Преобразование UUID в строку"""
        cache_key = f"creator_{creator_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        pool = await self._get_db_pool()
        async with pool.acquire() as conn:
            # UUID для числового ID
            creator_uuid = await conn.fetchval('''
                SELECT uuid FROM creator_mapping WHERE id = $1
            ''', creator_id)
            
            if not creator_uuid:
                logger.warning(f"[AI] Не найден UUID для креатора #{creator_id}")
                return None
            
            #   ПРЕОБРАЗУЕМ UUID в строку
            creator_uuid_str = str(creator_uuid)
            
            #   Ищем по UUID как строке
            result = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as videos_count,
                    SUM(views_count) as total_views,
                    SUM(likes_count) as total_likes,
                    SUM(comments_count) as total_comments,
                    SUM(reports_count) as total_reports
                FROM videos 
                WHERE creator_id = $1
                GROUP BY creator_id
            ''', creator_uuid_str)
            
            if not result:
                logger.warning(f"[AI] Не найдено видео для креатора #{creator_id} (UUID: {creator_uuid_str[:8]}...)")
                return None
            
            #   Снапшоты по UUID как строке
            snapshots_result = await conn.fetchval('''
                SELECT COUNT(*) 
                FROM video_snapshots vs
                JOIN videos v ON vs.video_id = v.id
                WHERE v.creator_id = $1
            ''', creator_uuid_str)
            
            stats = {
                'videos': result['videos_count'] or 0,
                'views': result['total_views'] or 0,
                'likes': result['total_likes'] or 0,
                'comments': result['total_comments'] or 0,
                'reports': result['total_reports'] or 0,
                'snapshots': snapshots_result or 0,
                'uuid': creator_uuid_str
            }
            
            self._set_cached(cache_key, stats)
            logger.info(f"[AI] Получена статистика креатора #{creator_id}: {stats['videos']} видео")
            return stats
    
    async def _get_all_creators_stats(self) -> Dict[int, Dict]:
        """Запрос: ВСЕ креаторы с числовыми ID"""
        cache_key = "all_creators_stats"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        pool = await self._get_db_pool()
        async with pool.acquire() as conn:
            results = await conn.fetch('''
                SELECT
                    cm.id as creator_id,
                    cm.uuid as creator_uuid,
                    COUNT(*) as videos_count,
                    SUM(v.views_count) as total_views,
                    SUM(v.likes_count) as total_likes,
                    SUM(v.comments_count) as total_comments,
                    SUM(v.reports_count) as total_reports
                FROM videos v
                JOIN creator_mapping cm ON v.creator_id = cm.uuid
                GROUP BY cm.id, cm.uuid
                ORDER BY cm.id
            ''')
            
            if not results:
                logger.warning("[AI] Нет данных о креаторах в БД")
                return {}
            
            creators = {}
            for row in results:
                creator_id = row['creator_id']
                creator_uuid_str = str(row['creator_uuid'])
                
                snapshots_result = await conn.fetchval('''
                    SELECT COUNT(*)
                    FROM video_snapshots vs
                    JOIN videos v ON vs.video_id = v.id
                    WHERE v.creator_id = $1
                ''', creator_uuid_str)
                
                creators[creator_id] = {
                    'uuid': creator_uuid_str,
                    'videos': row['videos_count'] or 0,
                    'views': row['total_views'] or 0,
                    'likes': row['total_likes'] or 0,
                    'comments': row['total_comments'] or 0,
                    'reports': row['total_reports'] or 0,
                    'snapshots': snapshots_result or 0
                }
            
            self._set_cached(cache_key, creators)
            logger.info(f"[AI] Получена статистика {len(creators)} креаторов")
            return creators
    
    async def _get_videos_by_views(self, threshold: int, comparison: str) -> Dict:
        """Запрос: видео по просмотрам"""
        cache_key = f"videos_views_{comparison}_{threshold}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        pool = await self._get_db_pool()
        async with pool.acquire() as conn:
            if comparison == "more":
                query = "SELECT COUNT(*) FROM videos WHERE views_count >= $1"
            else:
                query = "SELECT COUNT(*) FROM videos WHERE views_count <= $1"
            
            count = await conn.fetchval(query, threshold)
            total = await conn.fetchval("SELECT COUNT(*) FROM videos")
            
            # Избегаем деления на ноль
            total = total or 1
            
            result = {
                'count': count or 0,
                'total': total,
                'percent': (count / total * 100) if total > 0 else 0
            }
            
            self._set_cached(cache_key, result)
            return result
    
    async def _get_top_creators_by_metric(self, metric: str, limit: int = 3) -> List[Tuple[int, Dict]]:
        """Возвращает топ-N креаторов по указанной метрике"""
        try:
            creators_stats = await self._get_all_creators_stats()
            if not creators_stats:
                return []
            
            metric_map = {
                'videos': 'videos',
                'views': 'views',
                'likes': 'likes',
                'comments': 'comments',
                'reports': 'reports',
                'snapshots': 'snapshots'
            }
            
            if metric not in metric_map:
                logger.warning(f"[AI] Неизвестная метрика для топа: {metric}")
                return []
            
            db_field = metric_map[metric]
            
            sorted_creators = sorted(
                creators_stats.items(),
                key=lambda x: x[1][db_field],
                reverse=True
            )[:limit]
            
            return sorted_creators
            
        except Exception as e:
            logger.error(f"[AI] Ошибка получения топ-{limit} креаторов: {e}")
            return []
    
    async def _get_extreme_creators(self, metric: str) -> Dict[str, Tuple[int, Dict]]:
        """Возвращает креаторов с минимальным и максимальным значением метрики"""
        try:
            creators_stats = await self._get_all_creators_stats()
            if not creators_stats:
                return {}
            
            metric_map = {
                'videos': 'videos',
                'views': 'views',
                'likes': 'likes',
                'comments': 'comments',
                'reports': 'reports',
                'snapshots': 'snapshots'
            }
            
            if metric not in metric_map:
                logger.warning(f"[AI] Неизвестная метрика для экстремумов: {metric}")
                return {}
            
            db_field = metric_map[metric]
            
            # Находим креаторов с максимальным и минимальным значением
            max_creator = max(creators_stats.items(), key=lambda x: x[1][db_field])
            min_creator = min(creators_stats.items(), key=lambda x: x[1][db_field])
            
            return {
                'max': max_creator,
                'min': min_creator,
                'total': len(creators_stats)
            }
            
        except Exception as e:
            logger.error(f"[AI] Ошибка получения экстремумов: {e}")
            return {}
    
    # ========== GIGACHAT ==========
    
    def _initialize_gigachat(self):
        """Инициализация GigaChat"""
        try:
            from gigachat import GigaChat
            from gigachat.models import Chat, Messages, MessagesRole
            
            logger.info("[AI] Инициализирую GigaChat-2 Lite")
            
            self.giga = GigaChat(
                credentials=GIGACHAT_CLIENT_SECRET,
                verify_ssl_certs=False,
                model="GigaChat-2",
                timeout=45
            )
            
            self.giga_status = "initialized"
            self.active_model = "GigaChat-2"
            logger.info("[AI] GigaChat-2 объект создан")
            
        except Exception as e:
            logger.error(f"[AI] Ошибка GigaChat: {e}")
            self.giga = None
            self.giga_status = "init_error"
    
    async def _check_gigachat(self) -> str:
        """Проверка GigaChat"""
        if self.giga is None:
            return "disabled"
        
        if hasattr(self, '_giga_checked') and self._giga_checked:
            return self.giga_status
        
        try:
            from gigachat.models import Chat, Messages, MessagesRole
            
            logger.info("[AI] Проверяю GigaChat...")
            
            messages = Messages(
                role=MessagesRole.USER,
                content="Привет! Ответь 'Работаю'."
            )
            chat = Chat(messages=[messages])
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: self.giga.chat(chat))
            
            logger.info(f"[AI] GigaChat работает: {response.choices[0].message.content[:30]}")
            self.giga_status = "active"
            
        except Exception as e:
            error_str = str(e)
            logger.warning(f"[AI] Ошибка GigaChat: {e}")
            
            if "402" in error_str:
                self.giga_status = "payment_required"
            elif "404" in error_str:
                self.giga_status = "model_not_found"
            else:
                self.giga_status = "error"
        
        self._giga_checked = True
        return self.giga_status
    
    async def _ask_gigachat(self, prompt: str) -> str:
        """Запрос к GigaChat"""
        try:
            if self.giga is None:
                return "🤖 GigaChat недоступен"
            
            status = await self._check_gigachat()
            if status != "active":
                return f"🤖 GigaChat статус: {status}"
            
            # Контроль частоты
            current_time = time.time()
            if current_time - self.last_request_time < 1.0:
                await asyncio.sleep(1.0)
            
            from gigachat.models import Chat, Messages, MessagesRole
            
            logger.info(f"[AI] Отправляю запрос: {prompt[:70]}...")
            
            messages = Messages(role=MessagesRole.USER, content=prompt.strip())
            chat = Chat(messages=[messages])
            
            self.last_request_time = time.time()
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: self.giga.chat(chat))
            
            result = response.choices[0].message.content
            logger.info(f"[AI] Получен ответ ({len(result)} символов)")
            return result
            
        except Exception as e:
            logger.error(f"[AI] Ошибка запроса: {e}")
            return f"⚠️ Ошибка GigaChat: {str(e)[:150]}"
    
    # ========== ОСНОВНЫЕ AI МЕТОДЫ ==========
    
    async def analyze_creator(self, creator_id: int) -> str:
        """Анализ креатора через AI"""
        try:
            creator_stats = await self._get_creator_stats(creator_id)
            if not creator_stats:
                return f"❌ Креатор #{creator_id} не найден в базе данных"
            
            prompt = self.prompts["creator_analysis"].format(
                creator_id=creator_id,
                videos=creator_stats['videos'],
                views=creator_stats['views'],
                likes=creator_stats['likes'],
                comments=creator_stats['comments'],
                reports=creator_stats['reports'],
                snapshots=creator_stats['snapshots']
            )
            
            logger.info(f"[AI] Анализ креатора #{creator_id}")
            analysis = await self._ask_gigachat(prompt)
            
            return f"""

{analysis}

📌 РЕАЛЬНЫЕ ДАННЫЕ ИЗ БД:
🎯 Креатор #{creator_id}
📹 Видео: {creator_stats['videos']:,}
📸 Снапшоты: {creator_stats['snapshots']:,}
⚠️ Жалобы: {creator_stats['reports']:,}
💬 Комментарии: {creator_stats['comments']:,}
❤️ Лайки: {creator_stats['likes']:,}
👁️ Просмотры: {creator_stats['views']:,}
🔗 UUID: {creator_stats['uuid'][:8]}...

<i>AI анализ через GigaChat-2 • Независимый модуль</i>
"""
            
        except Exception as e:
            logger.error(f"[AI] Ошибка анализа креатора #{creator_id}: {e}")
            return f"❌ Ошибка AI анализа креатора #{creator_id}: {str(e)[:100]}"
    
    async def analyze_videos_by_views(self, threshold: int, comparison: str) -> str:
        """Анализ видео по просмотрам"""
        try:
            stats = await self._get_videos_by_views(threshold, comparison)
            all_stats = await self._get_all_basic_stats()
            
            comparison_text = "более" if comparison == "more" else "менее"
            prompt = self.prompts["videos_by_views"].format(
                total_videos=all_stats['total_videos'],
                comparison=comparison_text,
                threshold=threshold,
                count=stats['count'],
                percent=stats['percent'],
                total_views=all_stats['total_views']
            )
            
            logger.info(f"[AI] Анализ видео с {comparison_text} {threshold} просмотров")
            analysis = await self._ask_gigachat(prompt)
            
            return f"""

{analysis}

📌 РЕАЛЬНЫЕ ЦИФРЫ:
• Всего видео: {all_stats['total_videos']:,}
• Видео с {comparison_text} {threshold:,} просмотров: {stats['count']:,}
• Это {stats['percent']:.1f}% от всех видео
• Всего просмотров: {all_stats['total_views']:,}

<i>AI анализ через GigaChat-2 • Независимый модуль</i>
"""
            
        except Exception as e:
            logger.error(f"[AI] Ошибка анализа видео: {e}")
            return f"❌ Ошибка AI анализа: {str(e)[:100]}"
    
    async def analyze_extremes(self, metric: str) -> str:
        """Анализ экстремумов (мин/макс значений)"""
        try:
            metric_lower = metric.strip().lower()
            
            # === СРАЗУ проверяем метрику (исправлено) ===
            metric_map = {
                'videos': ('videos', 'видео', 'видео'),
                'views': ('views', 'просмотрам', 'просмотров'),
                'likes': ('likes', 'лайкам', 'лайков'),
                'comments': ('comments', 'комментариям', 'комментариев'),
                'reports': ('reports', 'жалобам', 'жалоб'),
                'snapshots': ('snapshots', 'снапшотам', 'снапшотов')
            }
            
            if metric_lower not in metric_map:
                return f"❌ Неизвестная метрика: {metric}"
            
            # === Только потом получаем данные ===
            extremes_data = await self._get_extreme_creators(metric_lower)
            
            if not extremes_data:
                return "❌ Нет данных о креаторах в БД для анализа экстремумов"
            
            max_creator = extremes_data.get('max')
            min_creator = extremes_data.get('min')
            
            if not max_creator or not min_creator:
                return "❌ Не удалось определить экстремальные значения"
            
            db_field, _, ru_genitive = metric_map[metric_lower]
            
            # Рассчитываем разницу и отношение
            max_value = max_creator[1][db_field]
            min_value = min_creator[1][db_field]
            difference = max_value - min_value
            ratio = max_value / max(min_value, 1)  # Избегаем деления на ноль
            
            prompt = self.prompts["extremes_analysis"].format(
                metric_ru=ru_genitive,
                max_id=max_creator[0],
                max_value=max_value,
                min_id=min_creator[0],
                min_value=min_value,
                difference=difference,
                ratio=ratio,
                total_creators=extremes_data.get('total', 0)
            )
            
            logger.info(f"[AI] Анализ экстремумов по {ru_genitive}")
            analysis = await self._ask_gigachat(prompt)
            
            return f"""

{analysis}

📌 РЕАЛЬНЫЕ ЦИФРЫ:
🏆 Максимум: Креатор #{max_creator[0]} - {max_value:,} {ru_genitive}
📉 Минимум: Креатор #{min_creator[0]} - {min_value:,} {ru_genitive}
📈 Разница: {difference:,} {ru_genitive} (в {ratio:.1f} раз)
👥 Всего креаторов: {extremes_data.get('total', 0)}

<i>AI анализ через GigaChat-2 • Независимый модуль</i>
"""
            
        except Exception as e:
            logger.error(f"[AI] Ошибка анализа экстремумов: {e}")
            return f"❌ Ошибка AI анализа экстремумов: {str(e)[:100]}"
    
    async def analyze_top_n(self, metric: str, n: int = 3) -> str:
        """Анализ топ-N креаторов (по умолчанию топ-3)"""
        try:
            metric_lower = metric.strip().lower()
            
            # === Специальная логика для 'creators' ===
            if metric_lower == 'creators':
                # Топ креаторов по количеству видео
                all_creators = await self._get_all_creators_stats()
                if not all_creators:
                    return "❌ Нет данных о креаторах в БД"
                
                # Сортируем по количеству видео
                top_creators = sorted(
                    all_creators.items(),
                    key=lambda x: x[1]['videos'],
                    reverse=True
                )[:n]
                
                if not top_creators:
                    return f"❌ Не удалось сформировать топ-{n} креаторов"
                
                # Формируем таблицу рейтинга
                medals = ["🥇", "🥈", "🥉", "4.", "5.", "6.", "7.", "8.", "9.", "10."]
                ranking_lines = []
                
                for i, (creator_id, stats) in enumerate(top_creators):
                    if i < len(medals):
                        prefix = medals[i]
                    else:
                        prefix = f"{i+1}."
                    
                    ranking_lines.append(f"{prefix} Креатор #{creator_id}: {stats['videos']:,} видео")
                
                ranking_table = "\n".join(ranking_lines)
                
                # Рассчитываем статистику
                total_videos = sum(c['videos'] for c in all_creators.values())
                top_n_videos = sum(stats['videos'] for _, stats in top_creators)
                top_n_percent = (top_n_videos / total_videos * 100) if total_videos > 0 else 0
                
                prompt = self.prompts["top_n_analysis"].format(
                    n=len(top_creators),
                    metric_ru='видео',
                    ranking_table=ranking_table,
                    top_n_percent=top_n_percent,
                    total_creators=len(all_creators)
                )
                
                logger.info(f"[AI] Анализ топ-{len(top_creators)} креаторов по количеству видео")
                analysis = await self._ask_gigachat(prompt)
                
                # Формируем таблицу для вывода
                output_table = ""
                for i, (creator_id, stats) in enumerate(top_creators):
                    if i < 3:
                        medal = ["🥇", "🥈", "🥉"][i]
                    else:
                        medal = f"{i+1}."
                    
                    output_table += f"{medal} <b>Креатор #{creator_id}:</b> {stats['videos']:,} видео\n"
                
                return f"""

{analysis}

📌 РЕАЛЬНЫЙ ТОП-{len(top_creators)} КРЕАТОРОВ ПО КОЛИЧЕСТВУ ВИДЕО:
{output_table}
📊 Топ-{len(top_creators)} контролируют: {top_n_percent:.1f}% всех видео
👥 Всего креаторов в анализе: {len(all_creators)}

<i>AI анализ через GigaChat-2 • Независимый модуль</i>
"""
            
            
            # Остальная логика (для других метрик)
            top_creators = await self._get_top_creators_by_metric(metric_lower, n)
            
            if not top_creators:
                return f"❌ Нет данных для формирования топ-{n} по метрике {metric}"
            
            if len(top_creators) < n:
                logger.warning(f"[AI] Только {len(top_creators)} креаторов доступно для топ-{n}")
            
            metric_map = {
                'videos': ('videos', 'видео', 'видео'),
                'views': ('views', 'просмотрам', 'просмотров'),
                'likes': ('likes', 'лайкам', 'лайков'),
                'comments': ('comments', 'комментариям', 'комментариев'),
                'reports': ('reports', 'жалобам', 'жалоб'),
                'snapshots': ('snapshots', 'снапшотам', 'снапшотов')
            }
            
            if metric_lower not in metric_map:
                return f"❌ Неизвестная метрика: {metric}"
            
            db_field, _, ru_genitive = metric_map[metric_lower]
            
            # Получаем статистику всех креаторов для расчетов
            all_creators = await self._get_all_creators_stats()
            if not all_creators:
                return "❌ Нет данных о креаторах в БД"
            
            # Рассчитываем общие значения
            total_value = sum(c[db_field] for c in all_creators.values())
            top_n_value = sum(stats[db_field] for _, stats in top_creators)
            top_n_percent = (top_n_value / total_value * 100) if total_value > 0 else 0
            
            # Формируем таблицу рейтинга для промпта
            medals = ["🥇", "🥈", "🥉", "4.", "5.", "6.", "7.", "8.", "9.", "10."]
            ranking_lines = []
            
            for i, (creator_id, stats) in enumerate(top_creators):
                if i < len(medals):
                    prefix = medals[i]
                else:
                    prefix = f"{i+1}."
                
                ranking_lines.append(f"{prefix} Креатор #{creator_id}: {stats[db_field]:,} {ru_genitive}")
            
            ranking_table = "\n".join(ranking_lines)
            
            prompt = self.prompts["top_n_analysis"].format(
                n=len(top_creators),
                metric_ru=ru_genitive,
                ranking_table=ranking_table,
                top_n_percent=top_n_percent,
                total_creators=len(all_creators)
            )
            
            logger.info(f"[AI] Анализ топ-{len(top_creators)} по {ru_genitive}")
            analysis = await self._ask_gigachat(prompt)
            
            # Формируем таблицу для вывода
            output_table = ""
            for i, (creator_id, stats) in enumerate(top_creators):
                if i < 3:
                    medal = ["🥇", "🥈", "🥉"][i]
                else:
                    medal = f"{i+1}."
                
                output_table += f"{medal} <b>Креатор #{creator_id}:</b> {stats[db_field]:,} {ru_genitive}\n"
            
            return f"""

{analysis}

📌 РЕАЛЬНЫЙ ТОП-{len(top_creators)} ПО {ru_genitive.upper()}: 
{output_table}
📊 Топ-{len(top_creators)} контролируют: {top_n_percent:.1f}% всех {ru_genitive}
👥 Всего креаторов в анализе: {len(all_creators)}

<i>AI анализ через GigaChat-2 • Независимый модуль</i>
"""
            
        except Exception as e:
            logger.error(f"[AI] Ошибка анализа топ-N: {e}")
            return f"❌ Ошибка AI анализа топ-N: {str(e)[:100]}"
    
    async def analyze_top_three(self, metric: str) -> str:
        """Алиас для обратной совместимости - анализ топ-3"""
        return await self.analyze_top_n(metric, n=3)
    
    async def analyze_top_ten(self, metric: str) -> str:
        """Анализ топ-10 креаторов"""
        return await self.analyze_top_n(metric, n=10)
    
    async def ai_general_analysis(self) -> str:
        """Общий AI анализ платформы"""
        try:
            stats = await self._get_all_basic_stats()
            # Рассчитываем вовлеченность (лайки/просмотры * 100%)
            # Используем max(..., 1) чтобы избежать деления на ноль
            engagement = (stats['total_likes'] / max(stats['total_views'], 1)) * 100
            # Используем существующий промпт из словаря
            prompt = self.prompts["platform_analysis"].format(
                total_videos=stats['total_videos'],
                total_creators=stats['total_creators'],
                total_views=stats['total_views'],
                total_likes=stats['total_likes'],
                total_comments=stats['total_comments'],
                engagement=engagement
            )
            
            logger.info("[AI] Общий AI анализ платформы")
            analysis = await self._ask_gigachat(prompt)
            
            return f"""

{analysis}

📌 ФАКТИЧЕСКИЕ ДАННЫЕ ИЗ БД:
📹 Видео: {stats['total_videos']:,}
👥 Креаторы: {stats['total_creators']:,}
👁️ Просмотры: {stats['total_views']:,}
❤️ Лайки: {stats['total_likes']:,}
💬 Комментарии: {stats['total_comments']:,}
⚠️ Жалобы: {stats['total_reports']:,}
📸 Снапшоты: {stats['total_snapshots']:,}
🎯 Вовлеченность: {engagement:.1f}%

<i>AI анализ через GigaChat-2 • Версия: {self.ai_version}</i>
"""
            
        except Exception as e:
            logger.error(f"[AI] Ошибка общего анализа: {e}")
            return f"❌ Ошибка AI анализа платформы: {str(e)[:100]}"
    
    async def close(self):
        """Закрывает СВОИ ресурсы"""
        if self.db_pool:
            await self.db_pool.close()
            self.db_pool = None
            logger.info("[AI] Закрыто СВОЕ подключение к БД")