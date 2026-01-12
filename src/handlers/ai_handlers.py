from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command, Filter
import re
import logging
import traceback
import html
from ..managers.ai_manager import AIManager

logger = logging.getLogger(__name__)
router = Router()
ai_manager = AIManager()

# ========== КОНСТАНТЫ ==========
MAX_AI_CREATOR_ID = 19

# ========== МАППИНГ МЕТРИК ==========
METRIC_MAP = {
    'видео': 'videos', 'ролик': 'videos', 'роликов': 'videos', 'видеороликов': 'videos',
    'лайков': 'likes', 'лайки': 'likes', 'лайк': 'likes',
    'просмотров': 'views', 'просмотры': 'views', 'просмотр': 'views',
    'комментариев': 'comments', 'комментарии': 'comments', 'комментарий': 'comments',
    'жалоб': 'reports', 'жалобы': 'reports', 'жалоба': 'reports',
    'снапшотов': 'snapshots', 'снапшоты': 'snapshots', 'снапшот': 'snapshots',
    'креаторов': 'creators', 'креаторы': 'creators', 'креатор': 'creators',
}

# ========== AI ФИЛЬТР ==========
class StrictAICommandFilter(Filter):
    """Фильтр для AI команд - ловит только явные AI запросы"""
    
    def __init__(self):
        # Паттерны AI команд
        self.AI_PATTERNS = [
            # 1. Креаторы: "5", "креатор 5", "анализ 10"
            re.compile(r'^(?:(?:креатор|анализ|покажи|проанализируй|создатель|автор)\s+)?(\d{1,2})$', re.IGNORECASE),
            
            # 2. Топ: "топ 3 лайков", "топ видео", "топ по лайкам"
            re.compile(r'^топ(?:\s+\d+)?(?:\s+по)?\s+(видео|роликов|лайк(?:ов|и)?|просмотр(?:ов|ы)?|комментар(?:иев|ий|ии)?|жалоб(?:ы)?|снапшот(?:ов|ы)?|креатор(?:ов|ы)?)$', re.IGNORECASE),
            
            # 3. Рейтинг: "рейтинг просмотров", "рейтинг по лайкам"
            re.compile(r'^рейтинг(?:\s+по)?\s+(видео|роликов|лайк(?:ов|и)?|просмотр(?:ов|ы)?|комментар(?:иев|ий|ии)?|жалоб(?:ы)?|снапшот(?:ов|ы)?|креатор(?:ов|ы)?)$', re.IGNORECASE),
            
            # 4. Экстремумы: "экстремум лайков", "кто больше видео", "максимум просмотров"
            re.compile(r'^(?:экстремум|кто\s+(?:больше|меньше)|максимум|минимум|самый\s+(?:большой|маленький))\s+(видео|роликов|лайк(?:ов|и)?|просмотр(?:ов|ы)?|комментар(?:иев|ий|ии)?|жалоб(?:ы)?|снапшот(?:ов|ы)?|креатор(?:ов|ы)?)$', re.IGNORECASE),
            
            # 5. Видео по просмотрам: "видео с более 100000 просмотров"
            re.compile(r'^видео\s+(?:с\s+)?(?:более|менее|больше|меньше)\s+\d+\s+просмотр', re.IGNORECASE),
            
            # 6. Сравнение: "сравни 5 и 10"
            re.compile(r'^сравни\s+\d+\s+и\s+\d+$', re.IGNORECASE),
            
            # 7. Вопросы: "у кого больше всего видео", "кто лучший по лайкам"
            re.compile(r'^(?:у\s+кого|кто)\s+(?:больше|меньше|лучший|худший|сильнее|слабее)\s+(?:всего\s+)?(?:по\s+)?(видео|роликов|лайк(?:ов|и)?|просмотр(?:ов|ы)?|комментар(?:иев|ий|ии)?|жалоб(?:ы)?|снапшот(?:ов|ы)?|креатор(?:ов|ы)?)', re.IGNORECASE),
            
            # 8. Общий анализ: "общий анализ", "анализ платформы"
            re.compile(r'^(?:общий\s+)?анализ(?:\s+платформы)?$', re.IGNORECASE),
            
            # 9. Лидеры: "лидеры по просмотрам"
            re.compile(r'^лидер(?:ы)?(?:\s+по)?\s+(видео|роликов|лайк(?:ов|и)?|просмотр(?:ов|ы)?|комментар(?:иев|ий|ии)?|жалоб(?:ы)?|снапшот(?:ов|ы)?|креатор(?:ов|ы)?)$', re.IGNORECASE),
        ]
        
        # AI ключевые слова (начало фраз)
        self.AI_KEYWORDS = {
            'креатор', 'анализ', 'покажи', 'проанализируй',
            'топ', 'рейтинг', 'экстремум', 'кто больше', 'кто меньше',
            'максимум', 'минимум', 'видео с', 'сравни', 'у кого',
            'кто лучший', 'кто худший', 'лидер', 'самый большой', 'самый маленький'
        }
        
        # Метрики для AI команд - все формы слов
        self.AI_METRICS = {
            'видео', 'роликов', 
            'лайк', 'лайки', 'лайков',
            'просмотр', 'просмотры', 'просмотров',
            'комментар', 'комментарии', 'комментариев', 'комментарий',
            'жалоба', 'жалобы', 'жалоб',
            'снапшот', 'снапшоты', 'снапшотов',
            'креатор', 'креаторы', 'креаторов'
        }

    async def __call__(self, message: Message) -> bool:
        text = message.text.strip() if message.text else ""
        logger.info(f"StrictAI фильтр проверяет: '{text}'")
        
        if not text:
            return False
        
        text_lower = text.lower()
        
        # ВСЕ команды со слешем пропускаются (их обрабатывают декораторы)
        if text.startswith('/'):
            return False
        
        # 1. Проверка цифр 1-19
        if text_lower.isdigit():
            try:
                num = int(text_lower)
                if 1 <= num <= MAX_AI_CREATOR_ID:
                    logger.info(f"StrictAI: цифра {num} - AI команда")
                    return True
            except ValueError:
                pass
        
        # 2. Проверка, начинается ли с AI ключевых слов
        starts_with_ai = False
        for keyword in self.AI_KEYWORDS:
            if text_lower.startswith(keyword):
                starts_with_ai = True
                break
        
        if not starts_with_ai:
            return False
        
        # 3. Проверка паттернами
        for pattern in self.AI_PATTERNS:
            match = pattern.match(text_lower)
            if match:
                logger.info(f"StrictAI: паттерн найден")
                
                # Если есть группа метрики - дополнительная проверка
                if match.groups():
                    metric = match.group(1)
                    metric_base = re.sub(r'\([^)]*\)', '', metric)
                    metric_base = re.sub(r'[^а-я]', '', metric_base)
                    
                    # Проверяем все возможные формы
                    for ai_metric in self.AI_METRICS:
                        if metric_base.startswith(ai_metric[:3]) or ai_metric.startswith(metric_base[:3]):
                            return True
                else:
                    return True
        
        return False

# ========== ВСЕ КОМАНДЫ СО СЛЕШЕМ ==========

@router.message(Command("analiz", "creator"))
async def handle_creator_commands(message: Message):
    """Обработчик для /analiz и /creator из меню"""
    logger.info(f"ВЫЗВАН handle_creator_commands: {message.text}")
    text = message.text.strip()
    parts = text.split()

    if len(parts) >= 2:
        try:
            creator_id = int(parts[1])
            if 1 <= creator_id <= MAX_AI_CREATOR_ID:
                logger.info(f"handle_creator_commands: обрабатываем креатора #{creator_id}")
                await message.answer(f"🤖 Анализирую креатора #{creator_id}...")
                response = await ai_manager.analyze_creator(creator_id)
                success = await safe_send_message(message, response)
                if not success:
                    logger.error(f"handle_creator_commands: не удалось отправить ответ для креатора #{creator_id}")
                return
            else:
                await message.answer(f"❌ ID креатора должен быть от 1 до {MAX_AI_CREATOR_ID}")
                return
        except ValueError:
            await message.answer(f"❌ Ошибка: '{parts[1]}' не является числом")
            return
        except Exception as e:
            logger.error(f"handle_creator_commands: ошибка обработки: {e}")
            logger.error(traceback.format_exc())
            await message.answer(f"❌ Ошибка при обработке: {str(e)}")
            return
    else:
        help_text = (
            "🤖 **АНАЛИЗ КРЕАТОРА**\n"
            "Для использования укажите ID креатора:\n"
            "📋 <code>/analiz 5</code> - анализ креатора с ID 5\n"
            "📋 <code>/creator 10</code> - анализ креатора с ID 10\n"
            f"📊 <b>Доступные ID:</b> от 1 до {MAX_AI_CREATOR_ID}\n"
            "💡 <b>Или просто напишите:</b>\n"
            "• креатор 5\n"
            "• анализ 10\n"
            "• 15 (просто цифру)\n"
            "• покажи 7"
        )
        success = await safe_send_message(message, help_text)
        if not success:
            await message.answer("❌ Не удалось отправить справку из-за сетевой ошибки.")

@router.message(Command("top3", "top", "rating"))
async def handle_top_commands(message: Message):
    """Обработчик для /top3, /top и /rating из меню"""
    logger.info(f"ВЫЗВАН handle_top_commands: {message.text}")
    text = message.text.strip()
    parts = text.split()

    if len(parts) >= 2:
        arg = parts[1].lower()
        metric = METRIC_MAP.get(arg, arg)
        if metric in {'videos', 'views', 'likes', 'comments', 'reports', 'snapshots', 'creators'}:
            logger.info(f"handle_top_commands: обрабатываем топ по '{arg}' (-> '{metric}')")
            await message.answer(f"🏆 Формирую топ по '{arg}'...")
            response = await ai_manager.analyze_top_three(metric)
            success = await safe_send_message(message, response)
            if not success:
                logger.error(f"handle_top_commands: не удалось отправить ответ для топа по '{metric}'")
            return
        else:
            logger.warning(f"handle_top_commands: метрика '{arg}' не найдена в списке доступных")
    help_text = (
        "🤖 **ТОП-3 ПО МЕТРИКЕ**\n"
        "Для использования укажите метрику:\n"
        "📋 <code>/top3 views</code> - топ-3 по просмотрам\n"
        "📋 <code>/top3 likes</code> - топ-3 по лайкам\n"
        "📋 <code>/top videos</code> - топ по видео\n"
        "📋 <code>/rating comments</code> - рейтинг по комментариям\n"
        "📊 <b>Доступные метрики:</b>\n"
        "• views / просмотры\n"
        "• likes / лайки\n"
        "• videos / видео\n"
        "• comments / комментарии\n"
        "• reports / жалобы\n"
        "• snapshots / снапшоты\n"
        "• creators / креаторы\n"
        "💡 <b>Или просто напишите:</b>\n"
        "• топ лайки\n"
        "• рейтинг просмотров\n"
        "• кто больше видео"
    )
    success = await safe_send_message(message, help_text)
    if not success:
        await message.answer("❌ Не удалось отправить справку из-за сетевой ошибки.")

@router.message(Command("extremes", "maxmin"))
async def handle_extremes_commands(message: Message):
    """Обработчик для /extremes и /maxmin из меню"""
    logger.info(f"ВЫЗВАН handle_extremes_commands: {message.text}")
    text = message.text.strip()
    parts = text.split()

    if len(parts) >= 2:
        arg = parts[1].lower()
        metric = METRIC_MAP.get(arg, arg)
        if metric in {'videos', 'views', 'likes', 'comments', 'reports', 'snapshots', 'creators'}:
            logger.info(f"handle_extremes_commands: обрабатываем экстремумы по '{arg}' (-> '{metric}')")
            await message.answer(f"📉 Формирую экстремумы по '{arg}'...")
            response = await ai_manager.analyze_extremes(metric)
            success = await safe_send_message(message, response)
            if not success:
                logger.error(f"handle_extremes_commands: не удалось отправить ответ для экстремумов по '{metric}'")
            return
        else:
            logger.warning(f"handle_extremes_commands: метрика '{arg}' не найдена в списке доступных")
    help_text = (
        "🤖 **МИН/МАКС ЗНАЧЕНИЯ**\n"
        "Для использования укажите метрику:\n"
        "📋 <code>/extremes views</code> - мин/макс по просмотрам\n"
        "📋 <code>/maxmin likes</code> - мин/макс по лайкам\n"
        "📊 <b>Доступные метрики:</b>\n"
        "• views / просмотры\n"
        "• likes / лайки\n"
        "• videos / видео\n"
        "• comments / комментарии\n"
        "• reports / жалобы\n"
        "• snapshots / снапшоты\n"
        "• creators / креаторы\n"
        "💡 <b>Или просто напишите:</b>\n"
        "• кто больше лайков\n"
        "• максимум просмотров\n"
        "• минимум видео"
    )
    success = await safe_send_message(message, help_text)
    if not success:
        await message.answer("❌ Не удалось отправить справку из-за сетевой ошибки.")

@router.message(Command("analizvideo"))
async def handle_analizvideo_menu(message: Message):
    """Обработчик для /analizvideo из меню"""
    logger.info(f"ВЫЗВАН handle_analizvideo_menu: {message.text}")
    text = message.text.strip()
    parts = text.split()

    if len(parts) >= 3:
        try:
            threshold = int(parts[1])
            comparison = parts[2].lower()
            if comparison in ['more', 'less', 'morethan', 'lessthan', 'больше', 'меньше', 'более', 'менее']:
                logger.info(f"handle_analizvideo_menu: видео с {comparison} {threshold} просмотров")
                await message.answer(f"🎬 Ищу видео с {comparison} {threshold} просмотров...")
                response = await ai_manager.analyze_videos_by_views(threshold, comparison)
                success = await safe_send_message(message, response)
                if not success:
                    logger.error(f"handle_analizvideo_menu: не удалось отправить ответ для видео с {comparison} {threshold} просмотров")
                return
            else:
                logger.warning(f"handle_analizvideo_menu: некорректное сравнение '{comparison}'")
        except ValueError:
            logger.error(f"handle_analizvideo_menu: '{parts[1]}' не является числом")
        except Exception as e:
            logger.error(f"handle_analizvideo_menu: ошибка обработки: {e}")

    help_text = (
        "🤖 **АНАЛИЗ ВИДЕО ПО ПРОСМОТРАМ**\n"
        "Для использования укажите порог и тип сравнения:\n"
        "📋 <code>/analizvideo 100000 more</code> - видео с более 100к просмотров\n"
        "📋 <code>/analizvideo 50000 less</code> - видео с менее 50к просмотров\n"
        "📊 <b>Типы сравнения:</b>\n"
        "• more / больше / более\n"
        "• less / меньше / менее\n"
        "💡 <b>Или просто напишите:</b>\n"
        "• видео с более 100000 просмотров\n"
        "• видео менее 50000 просмотров"
    )
    success = await safe_send_message(message, help_text)
    if not success:
        await message.answer("❌ Не удалось отправить справку из-за сетевой ошибки.")

@router.message(Command("video100k"))
async def handle_video_100k(message: Message):
    """Обработчик для /video100k"""
    logger.info("ВЫЗВАН handle_video_100k")
    try:
        await message.answer("🎬 Ищу видео с более 100,000 просмотров...")
        response = await ai_manager.analyze_videos_by_views(100000, 'more')
        success = await safe_send_message(message, response)
        if not success:
            logger.error("handle_video_100k: не удалось отправить ответ")
    except Exception as e:
        logger.error(f"Ошибка в handle_video_100k: {e}")
        await message.answer("❌ Ошибка при анализе видео.")

@router.message(Command("video50k"))
async def handle_video_50k(message: Message):
    """Обработчик для /video50k"""
    logger.info("ВЫЗВАН handle_video_50k")
    try:
        await message.answer("🎬 Ищу видео с более 50,000 просмотров...")
        response = await ai_manager.analyze_videos_by_views(50000, 'more')
        success = await safe_send_message(message, response)
        if not success:
            logger.error("handle_video_50k: не удалось отправить ответ")
    except Exception as e:
        logger.error(f"Ошибка в handle_video_50k: {e}")
        await message.answer("❌ Ошибка при анализе видео.")

@router.message(Command("video25k"))
async def handle_video_25k(message: Message):
    """Обработчик для /video25k"""
    logger.info("ВЫЗВАН handle_video_25k")
    try:
        await message.answer("🎬 Ищу видео с более 25,000 просмотров...")
        response = await ai_manager.analyze_videos_by_views(25000, 'more')
        success = await safe_send_message(message, response)
        if not success:
            logger.error("handle_video_25k: не удалось отправить ответ")
    except Exception as e:
        logger.error(f"Ошибка в handle_video_25k: {e}")
        await message.answer("❌ Ошибка при анализе видео.")

@router.message(Command("platformanalysis", "obshiyanaliz", "analizplatformy", "общий_анализ", "fullanalysis", "analyzeall"))
async def handle_platform_analysis(message: Message):
    """Обработчик для общего анализа платформы"""
    logger.info("ВЫЗВАН handle_platform_analysis")
    try:
        await message.answer("🤖 Формирую общий анализ платформы...")
        response = await ai_manager.ai_general_analysis()
        success = await safe_send_message(message, response)
        if not success:
            logger.error("handle_platform_analysis: не удалось отправить ответ")
    except Exception as e:
        logger.error(f"Ошибка общего анализа: {e}")
        await message.answer("❌ Ошибка при анализе платформы. Проверьте подключение к AI.")

@router.message(Command("aispravka", "ai_справка", "айсправка", "aihelp", "ai_help", "айхелп"))
async def cmd_ai_help_unified(message: Message):
    """Универсальная AI справка"""
    logger.info("ВЫЗВАН cmd_ai_help_unified")
    help_text = """🤖 **AI АНАЛИТИКА - ВСЕ КОМАНДЫ:**

🎯 **АНАЛИЗ КРЕАТОРОВ:**
пример ввода: креатор (1-19)
пример ввода: (1-19) просто числами

🎬 **АНАЛИЗ ВИДЕО:**
/video100k - видео с 100к+ просмотров
/video50k - видео с 50к+ просмотров
/video25k - видео с 25к+ просмотров

🏆 **ТОПЫ И РЕЙТИНГИ:**
/top3 [метрика] - топ-3 по метрике
или фразами: топ 3 (метрика)


📈 **ЭКСТРЕМУМЫ (мин/макс):**
/extremes [метрика] - минимальные и максимальные значения
/maxmin [метрика] - альтернативная команда для экстремумов
или фразами: экстремум (метрика)

🌐 **АНАЛИЗ ПЛАТФОРМЫ:**
/platformanalysis - полный анализ платформы

🔍 **ПРОВЕРКА СИСТЕМЫ:**
/test_ai - проверка доступности AI аналитики

📝 **Текстовые запросы:**
• "анализ креатора 5" или просто "5"
• "топ 3 по лайкам" или "топ 3 лайков"
• "рейтинг по просмотрам"
• "кто больше видео" - максимум по видео
• "видео с более 100000 просмотров" - анализ видео
• "кто лучший/худший по просмотрам"
• "общий анализ платформы"

**Доступные метрики:** видео, просмотры, лайки, комментарии, жалобы, снапшоты, креаторы

📅 **АНАЛИЗ ПО ДАТАМ:**
Для анализа статистики по периодам (сегодня, вчера, неделя, месяц и т.д.)
спользуйте команду: /ai_date_help"""

    success = await safe_send_message(message, help_text)
    if not success:
        logger.error("cmd_ai_help_unified: не удалось отправить справку")

@router.message(Command("test_ai"))
async def cmd_test_ai(message: Message):
    """Тест систем"""
    logger.info("ВЫЗВАН cmd_test_ai")
    try:
        from managers.database_manager import VideoDatabaseManager
        db_manager = VideoDatabaseManager()
        db_ok = await db_manager.test_connection()

        ai_ok = False
        try:
            stats = await ai_manager._get_creator_stats(1)
            ai_ok = stats is not None and isinstance(stats, dict)
        except Exception as e:
            logger.error(f"Ошибка теста AI: {e}")

        response = "🤖 **ТЕСТ СИСТЕМ АНАЛИТИКИ**\n"
        response += f"🗄️ **База данных:** {'✅ Успешно' if db_ok else '❌ Ошибка'}\n"
        response += f"🧠 **AI Аналитика:** {'✅ Доступна' if ai_ok else '❌ Недоступна'}"

        success = await safe_send_message(message, response)
        if not success:
            logger.error("cmd_test_ai: не удалось отправить результаты теста")
    except Exception as e:
        logger.error(f"Ошибка в cmd_test_ai: {e}")
        await message.answer("❌ Ошибка при тестировании систем.")

# ========== ТЕКСТОВЫЕ AI КОМАНДЫ ==========
@router.message(StrictAICommandFilter())
async def handle_text_ai_commands(message: Message):
    """Обработка текстовых AI команд"""
    text = message.text.strip()
    text_lower = text.lower()
    logger.info(f"AIHandler получил текстовый запрос: '{text}'")
    
    try:
        # 1. Цифра (креатор)
        if text_lower.isdigit():
            try:
                creator_id = int(text_lower)
                if 1 <= creator_id <= MAX_AI_CREATOR_ID:
                    logger.info(f"Обрабатываем креатора #{creator_id} (по числу)")
                    await message.answer(f"🤖 Анализирую креатора #{creator_id}...")
                    response = await ai_manager.analyze_creator(creator_id)
                    success = await safe_send_message(message, response)
                    if not success:
                        logger.error(f"Не удалось отправить ответ для креатора #{creator_id}")
                    return
                else:
                    await message.answer(f"❌ ID креатора должен быть от 1 до {MAX_AI_CREATOR_ID}")
                    return
            except ValueError:
                pass
        
        # 2. Креатор с фразой
        match = re.match(r'^(?:креатор|анализ|покажи|проанализируй)\s+(\d+)$', text_lower)
        if match:
            creator_id = int(match.group(1))
            if 1 <= creator_id <= MAX_AI_CREATOR_ID:
                logger.info(f"Обрабатываем креатора #{creator_id} (по фразе)")
                await message.answer(f"🤖 Анализирую креатора #{creator_id}...")
                response = await ai_manager.analyze_creator(creator_id)
                success = await safe_send_message(message, response)
                if not success:
                    logger.error(f"Не удалось отправить ответ для креатора #{creator_id}")
                return
            else:
                await message.answer(f"❌ ID креатора должен быть от 1 до {MAX_AI_CREATOR_ID}")
                return
        
        # 3. Топ по метрике
        top_match = re.search(r'топ(?:\s+\d+)?(?:\s+по)?\s+(\w+)', text_lower)
        if top_match:
            metric_name = top_match.group(1)
            metric = METRIC_MAP.get(metric_name)
            if metric:
                logger.info(f"Обрабатываем топ по '{metric_name}' (-> '{metric}')")
                await message.answer(f"🏆 Формирую топ по '{metric_name}'...")
                response = await ai_manager.analyze_top_three(metric)
                success = await safe_send_message(message, response)
                if not success:
                    logger.error(f"Не удалось отправить ответ для топа по '{metric}'")
                return
        
        # 4. Рейтинг по метрике
        rating_match = re.search(r'рейтинг(?:\s+по)?\s+(\w+)', text_lower)
        if rating_match:
            metric_name = rating_match.group(1)
            metric = METRIC_MAP.get(metric_name)
            if metric:
                logger.info(f"Обрабатываем рейтинг по '{metric_name}' (-> '{metric}')")
                await message.answer(f"📊 Формирую рейтинг по '{metric_name}'...")
                response = await ai_manager.analyze_rating(metric)
                success = await safe_send_message(message, response)
                if not success:
                    logger.error(f"Не удалось отправить ответ для рейтинга по '{metric}'")
                return
        
        # Экстремумы
        extremes_match = re.search(r'(?:экстремум|кто\s+(?:больше|меньше)|максимум|минимум)\s+(видео|роликов|лайк(?:ов|и)?|просмотр(?:ов|ы)?|комментар(?:иев|ий|ии)?|жалоб(?:ы)?|снапшот(?:ов|ы)?|креатор(?:ов|ы)?)', text_lower)
        if extremes_match:
            metric_name = extremes_match.group(1)
            if 'лайк' in metric_name:
                metric_name = 'лайки' if 'и' in metric_name or 'ии' in metric_name else 'лайков'
            elif 'просмотр' in metric_name:
                metric_name = 'просмотры' if 'ы' in metric_name or 'ыи' in metric_name else 'просмотров'
            elif 'комментар' in metric_name:
                metric_name = 'комментарии' if 'ии' in metric_name or 'ии' in metric_name else 'комментариев'
            elif 'жалоб' in metric_name:
                metric_name = 'жалобы' if 'ы' in metric_name else 'жалоб'  # ИСПРАВЛЕНО: было 'ы' в metric_name
            elif 'снапшот' in metric_name:
                metric_name = 'снапшоты' if 'ы' in metric_name or 'ыи' in metric_name else 'снапшотов'
            elif 'креатор' in metric_name:
                metric_name = 'креаторы' if 'ы' in metric_name or 'и' in metric_name else 'креаторов'
            
            metric = METRIC_MAP.get(metric_name)
            if metric:
                logger.info(f"Обрабатываем экстремумы по '{metric_name}' (-> '{metric}')")
                await message.answer(f"📉 Формирую экстремумы по '{metric_name}'...")
                
                if metric == 'creators':
                    response = await ai_manager.analyze_top_three(metric)
                else:
                    response = await ai_manager.analyze_extremes(metric)
                
                success = await safe_send_message(message, response)
                if not success:
                    logger.error(f"Не удалось отправить ответ для экстремумов по '{metric}'")
                return
        
        # 6. Видео по просмотрам
        video_match = re.search(r'видео\s+(?:с\s+)?(?:более|менее|больше|меньше)\s+(\d+)\s+просмотр', text_lower)
        if video_match:
            threshold = int(video_match.group(1))
            comparison = 'more' if 'более' in text_lower or 'больше' in text_lower else 'less'
            logger.info(f"Видео с {comparison} {threshold} просмотров")
            await message.answer(f"🎬 Ищу видео с {comparison} {threshold} просмотров...")
            response = await ai_manager.analyze_videos_by_views(threshold, comparison)
            success = await safe_send_message(message, response)
            if not success:
                logger.error(f"Не удалось отправить ответ для видео с {comparison} {threshold} просмотров")
            return
        
        # 7. Сравнение креаторов
        compare_match = re.match(r'^сравни\s+(\d+)\s+и\s+(\d+)$', text_lower)
        if compare_match:
            creator1_id = int(compare_match.group(1))
            creator2_id = int(compare_match.group(2))
            if 1 <= creator1_id <= MAX_AI_CREATOR_ID and 1 <= creator2_id <= MAX_AI_CREATOR_ID:
                logger.info(f"Сравниваем креаторов #{creator1_id} и #{creator2_id}")
                await message.answer(f"⚖️ Сравниваю креаторов #{creator1_id} и #{creator2_id}...")
                response = await ai_manager.compare_creators(creator1_id, creator2_id)
                success = await safe_send_message(message, response)
                if not success:
                    logger.error(f"Не удалось отправить ответ для сравнения креаторов #{creator1_id} и #{creator2_id}")
                return
            else:
                await message.answer(f"❌ ID креаторов должны быть от 1 до {MAX_AI_CREATOR_ID}")
                return
        
        # 8. Вопросы: "у кого больше всего видео", "кто лучший по лайкам"
        questions_match = re.search(r'(?:у\s+кого|кто)\s+(?:больше|меньше|лучший|худший|сильнее|слабее)\s+(?:всего\s+)?(?:по\s+)?(видео|роликов|лайк(?:ов|и)?|просмотр(?:ов|ы)?|комментар(?:иев|ий|ии)?|жалоб(?:ы)?|снапшот(?:ов|ы)?|креатор(?:ов|ы)?)', text_lower)
        if questions_match:
            metric_name = questions_match.group(1)
            if 'лайк' in metric_name:
                metric_name = 'лайки' if 'и' in metric_name or 'ии' in metric_name else 'лайков'
            elif 'просмотр' in metric_name:
                metric_name = 'просмотры' if 'ы' in metric_name or 'ыи' in metric_name else 'просмотров'
            elif 'комментар' in metric_name:
                metric_name = 'комментарии' if 'ии' in metric_name or 'ии' in metric_name else 'комментариев'
            elif 'жалоб' in metric_name:
                metric_name = 'жалобы' if 'ы' in metric_name else 'жалоб'
            elif 'снапшот' in metric_name:
                metric_name = 'снапшоты' if 'ы' in metric_name or 'ыи' in metric_name else 'снапшотов'
            elif 'креатор' in metric_name:
                metric_name = 'креаторы' if 'ы' in metric_name or 'и' in metric_name else 'креаторов'
            
            metric = METRIC_MAP.get(metric_name)
            if metric:
                logger.info(f"Обрабатываем вопрос по '{metric_name}' (-> '{metric}')")
                await message.answer(f"🤔 Ищу ответ на ваш вопрос по '{metric_name}'...")
                
                if metric == 'creators':
                    response = await ai_manager.analyze_top_three(metric)
                else:
                    response = await ai_manager.analyze_extremes(metric)
                
                success = await safe_send_message(message, response)
                if not success:
                    logger.error(f"Не удалось отправить ответ для вопроса по '{metric}'")
                return
        
        # 9. Лидеры по метрике
        leaders_match = re.search(r'^лидер(?:ы)?(?:\s+по)?\s+(видео|роликов|лайк(?:ов|и)?|просмотр(?:ов|ы)?|комментар(?:иев|ий|ии)?|жалоб(?:ы)?|снапшот(?:ов|ы)?|креатор(?:ов|ы)?)$', text_lower)
        if leaders_match:
            metric_name = leaders_match.group(1)
            if 'лайк' in metric_name:
                metric_name = 'лайки' if 'и' in metric_name or 'ии' in metric_name else 'лайков'
            elif 'просмотр' in metric_name:
                metric_name = 'просмотры' if 'ы' in metric_name or 'ыи' in metric_name else 'просмотров'
            elif 'комментар' in metric_name:
                metric_name = 'комментарии' if 'ии' in metric_name or 'ии' in metric_name else 'комментариев'
            elif 'жалоб' in metric_name:
                metric_name = 'жалобы' if 'ы' in metric_name else 'жалоб'
            elif 'снапшот' in metric_name:
                metric_name = 'снапшоты' if 'ы' in metric_name or 'ыи' in metric_name else 'снапшотов'
            elif 'креатор' in metric_name:
                metric_name = 'креаторы' if 'ы' in metric_name or 'и' in metric_name else 'креаторов'
            
            metric = METRIC_MAP.get(metric_name)
            if metric:
                logger.info(f"Обрабатываем лидеров по '{metric_name}' (-> '{metric}')")
                await message.answer(f"👑 Формирую список лидеров по '{metric_name}'...")
                response = await ai_manager.analyze_top_three(metric)
                success = await safe_send_message(message, response)
                if not success:
                    logger.error(f"Не удалось отправить ответ для лидеров по '{metric}'")
                return
        
        # 10. Общий анализ
        if any(keyword in text_lower for keyword in ['общий анализ', 'анализ платформы', 'вся статистика']):
            logger.info("Общий анализ платформы")
            await message.answer("🤖 Формирую общий анализ платформы...")
            response = await ai_manager.ai_general_analysis()
            success = await safe_send_message(message, response)
            if not success:
                logger.error("Не удалось отправить ответ для общего анализа")
            return
        
        # 11. Не распознали
        logger.info(f"Не распознанная AI команда: '{text_lower}'")
        help_text = (
            "🤖 Не распознал AI команду.\n"
            "Попробуйте:\n"
            "• 'креатор 5'\n"
            "• 'топ 3 по лайкам'\n"
            "• 'рейтинг по просмотрам'\n"
            "• 'экстремум лайков'\n"
            "• 'видео с более 100000 просмотров'\n"
            "• 'общий анализ платформы'\n"
            "Или используйте команды из /aispravка"
        )
        await message.answer(help_text)
        
    except Exception as e:
        logger.error(f"Ошибка в handle_text_ai_commands: {e}")
        logger.error(traceback.format_exc())
        await message.answer("❌ Ошибка при обработке AI команды.")

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
async def safe_send_message(message: Message, text: str) -> bool:
    """Безопасная отправка сообщения"""
    try:
        text = html.escape(text)
        await message.answer(text)
        return True
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения: {e}")
        return False

logger.info("AI модуль загружен (ужесточенный фильтр)")