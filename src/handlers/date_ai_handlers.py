from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import asyncio
from aiogram import Router, F
from aiogram.types import Message, BotCommand
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.markdown import hbold, hcode, hitalic
import logging
from ..managers.date_ai_manager import DateAIManager, PeriodType
import time

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)

# Состояния для FSM
class StatsStates(StatesGroup):
    waiting_custom_start = State()
    waiting_custom_end = State()
    waiting_creator_id = State()
    waiting_question = State()


class DateAIHandlers:
    """
    Обработчики для DateAIManager
    """
    
    def __init__(self, manager: DateAIManager):
        self.manager = manager
        self.router = Router()
        self._init_commands()
        self._register_handlers()
        # Кэш для частых запросов
        self._creators_cache: Optional[List[int]] = None
        self._cache_time: Optional[float] = None

    def _init_commands(self):
        """Инициализация команды бота"""
        self.commands = [
            BotCommand(command="start", description="Начало работы"),
            BotCommand(command="help", description="Помощь по командам"),
            BotCommand(command="ai_date_help", description="Справочник команд AI анализатора"),
            BotCommand(command="today", description="Статистика за сегодня"),
            BotCommand(command="yesterday", description="Статистика за вчера"),
            BotCommand(command="week", description="Статистика за неделю"),
            BotCommand(command="month", description="Статистика за месяц"),
            BotCommand(command="custom", description="Кастомный период"),
            BotCommand(command="creators", description="Список креаторов"),
            BotCommand(command="creator", description="Статистика по креатору"),
            BotCommand(command="system", description="Системная информация"),
            BotCommand(command="ask", description="Задать вопрос AI"),
        ]

    def _register_handlers(self):
        """Регистрация обработчиков"""
        # Основные команды
        self.router.message.register(self.cmd_start, CommandStart())
        self.router.message.register(self.cmd_help, Command("help"))
        self.router.message.register(self.cmd_ai_date_help, Command("ai_date_help"))
        self.router.message.register(self.cmd_today, Command("today"))
        self.router.message.register(self.cmd_yesterday, Command("yesterday"))
        self.router.message.register(self.cmd_week, Command("week"))
        self.router.message.register(self.cmd_month, Command("month"))
        self.router.message.register(self.cmd_custom, Command("custom"))
        self.router.message.register(self.cmd_creators, Command("creators"))
        self.router.message.register(self.cmd_creator, Command("creator"))
        self.router.message.register(self.cmd_system, Command("system"))
        self.router.message.register(self.cmd_ask, Command("ask"))
        
        # Обработчики состояний
        self.router.message.register(
            self.process_custom_start,
            StateFilter(StatsStates.waiting_custom_start)
        )
        self.router.message.register(
            self.process_custom_end,
            StateFilter(StatsStates.waiting_custom_end)
        )
        self.router.message.register(
            self.process_creator_id,
            StateFilter(StatsStates.waiting_creator_id)
        )
        self.router.message.register(
            self.process_question,
            StateFilter(StatsStates.waiting_question)
        )
        
        logger.info("[DateAIHandlers] Обработчики зарегистрированы")

    # ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========

    def _get_target_year(self) -> int:
        """Получение target_year"""
        if hasattr(self.manager, 'data_period') and self.manager.data_period:
            return self.manager.data_period.target_year
        return 2023  # значение по умолчанию

    async def _load_stats_with_ai(self, message: Message, stats_method, *args) -> bool:
        """Универсальный метод загрузки статистики с AI анализом"""
        try:
            await message.answer("⏳ Загружаю статистику...")
            stats = await stats_method(*args)
            
            if not stats.get('has_data', False):
                await message.answer(
                    self._format_no_data_message(stats),
                    parse_mode="HTML"
                )
                return False
            
            await message.answer("🤖 Анализирую данные с помощью AI...")
            ai_analysis = await self.manager.analyze_with_ai(stats)
            response = self._format_stats_message(stats, ai_analysis)
            await message.answer(response, parse_mode="HTML")
            return True
            
        except Exception as e:
            logger.error(f"[Handlers] Ошибка при запросе статистики: {e}", exc_info=True)
            await message.answer(
                f"❌ Ошибка при получении статистики:\n{hcode(str(e))}",
                parse_mode="HTML"
            )
            return False

    async def _get_available_creators(self) -> List[int]:
        """Список доступных креаторов с кэшированием"""
        if self._creators_cache and self._cache_time and (time.time() - self._cache_time < 300):
            return self._creators_cache
        
        try:
            # Возможные методы из DateAIManager
            if hasattr(self.manager, 'get_available_creator_ids'):
                self._creators_cache = await self.manager.get_available_creator_ids()
            elif hasattr(self.manager, 'get_creators_with_data'):
                self._creators_cache = await self.manager.get_creators_with_data()
            else:
                # Если метод не найден, возвращаем пустой список
                logger.warning("[Handlers] Метод получения списка креаторов не найден в DateAIManager")
                self._creators_cache = []
            
            self._cache_time = time.time()
            return self._creators_cache
        except Exception as e:
            logger.error(f"[Handlers] Ошибка получения списка креаторов: {e}", exc_info=True)
            return []

    # ========== ОСНОВНЫЕ КОМАНДЫ ==========

    async def cmd_start(self, message: Message):
        """Начало работы"""
        target_year = self._get_target_year()
        welcome_text = f"""
🎬 {hbold('Анализатор статистики видеоплатформы')}

📊 {hitalic('Доступные команды:')}
👉 /today - статистика за сегодня
👉 /yesterday - статистика за вчера
👉 /week - статистика за неделю
👉 /month - статистика за месяц
👉 /custom - произвольный период
👉 /creators - список креаторов
👉 /creator - статистика по креатору
👉 /system - системная информация
👉 /ask - задать вопрос AI
👉 /ai_date_help - справочник команд AI анализатора

ℹ️ {hitalic('Важно:')}
• Данные ограничены {target_year} годом
• Видео создавались в августе-октябре
• Статистика собиралась в ноябре-декабре
• Креаторы обозначены номерами 1-19
"""
        await message.answer(welcome_text, parse_mode="HTML")
    
    async def cmd_help(self, message: Message):
        """Помощь по командам"""
        target_year = self._get_target_year()
        help_text = f"""
📚 {hbold('Справка по командам')}

{hbold('📈 Статистика:')}
👉 /today - статистика за текущий день
👉 /yesterday - статистика за вчерашний день  
👉 /week - статистика за текущую неделю
👉 /month - статистика за текущий месяц
👉 /custom - статистика за произвольный период

{hbold('👥 Креаторы:')}
👉 /creators - список всех креаторов с данными
👉 /creator - детальная статистика по креатору

{hbold('⚙️ Система:')}
👉 /system - информация о системе и фильтрах
👉 /ask - задать вопрос AI о статистике
👉 /ai_date_help - полный справочник команд AI анализатора

{hbold('📋 Ограничения данных:')}
• Год данных: {target_year}
• Видео: август, сентябрь, октябрь
• Статистика: ноябрь, декабрь
"""
        await message.answer(help_text, parse_mode="HTML")
    
    async def cmd_ai_date_help(self, message: Message):
        """Справочное окно со всеми командами AI анализатора"""
        help_text = f"""
🤖 {hbold('СПРАВОЧНИК КОМАНД AI АНАЛИЗАТОРА СТАТИСТИКИ')}
🎬 {hitalic('Анализатор видеоплатформы')}

📊 {hbold('📈 ОСНОВНЫЕ КОМАНДЫ СТАТИСТИКИ:')}

👉 /today - Статистика за сегодняшний день
👉 /yesterday - Статистика за вчерашний день
👉 /week - Статистика за текущую неделю
👉 /month - Статистика за текущий месяц
👉 /custom - Статистика за произвольный период (ввод дат)

👥 {hbold('👤 КОМАНДЫ ПО КРЕАТОРАМ:')}

👉 /creators - Показать список всех доступных креаторов
👉 /creator - Получить детальную статистику по конкретному креатору

⚙️ {hbold('🔧 СИСТЕМНЫЕ КОМАНДЫ:')}

👉 /system - Показать системную информацию и настройки
"""
        await message.answer(help_text, parse_mode="HTML")
    
    async def cmd_today(self, message: Message):
        """Статистика за сегодня"""
        today = datetime.now()
        target_year = self._get_target_year()
        
        # Временная логика для отладки
        logger.info(f"[cmd_today] Текущая дата: {today}, target_year: {target_year}")
        
        # Проверяем, есть ли данные за текущий день в целевом году
        try:
            # Статистика, даже если год не совпадает
            # Менеджер обработки отсутсвия данных
            await self._load_stats_with_ai(message, self.manager.get_daily_stats, today)
        except Exception as e:
            logger.error(f"[cmd_today] Ошибка: {e}", exc_info=True)
            await message.answer(
                f"📅 {hbold('Сегодня')} ({today.strftime('%d.%m.%Y')})\n\n"
                f"⚠️ Произошла ошибка при получении данных\n"
                f"Проверьте наличие данных за {target_year} год",
                parse_mode="HTML"
            )
    
    async def cmd_yesterday(self, message: Message):
        """Статистика за вчера"""
        yesterday = datetime.now() - timedelta(days=1)
        target_year = self._get_target_year()
        
        logger.info(f"[cmd_yesterday] Дата: {yesterday}, target_year: {target_year}")
        
        try:
            await self._load_stats_with_ai(message, self.manager.get_daily_stats, yesterday)
        except Exception as e:
            logger.error(f"[cmd_yesterday] Ошибка: {e}", exc_info=True)
            await message.answer(
                f"📅 {hbold('Вчера')} ({yesterday.strftime('%d.%m.%Y')})\n\n"
                f"⚠️ Произошла ошибка при получении данных\n"
                f"Проверьте наличие данных за {target_year} год",
                parse_mode="HTML"
            )
    
    async def cmd_week(self, message: Message):
        """Статистика за неделю"""
        today = datetime.now()
        target_year = self._get_target_year()
        
        logger.info(f"[cmd_week] Текущая дата: {today}, target_year: {target_year}")
        
        try:
            await self._load_stats_with_ai(message, self.manager.get_weekly_stats, today)
        except Exception as e:
            logger.error(f"[cmd_week] Ошибка: {e}", exc_info=True)
            await message.answer(
                f"📅 {hbold('Неделя')}\n\n"
                f"⚠️ Произошла ошибка при получении данных\n"
                f"Проверьте наличие данных за {target_year} год",
                parse_mode="HTML"
            )
    
    async def cmd_month(self, message: Message):
        """Статистика за текущий месяц"""
        today = datetime.now()
        target_year = self._get_target_year()
        
        logger.info(f"[cmd_month] Текущая дата: {today}, target_year: {target_year}")
        
        month_names = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                      'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
        month_name = month_names[today.month - 1]
        
        try:
            await message.answer(f"⏳ Загружаю статистику за {month_name}...")
            await self._load_stats_with_ai(message, self.manager.get_monthly_stats, today.year, today.month)
        except Exception as e:
            logger.error(f"[cmd_month] Ошибка: {e}", exc_info=True)
            await message.answer(
                f"📅 {hbold('Месяц')} {month_name}\n\n"
                f"⚠️ Произошла ошибка при получении данных\n"
                f"Проверьте наличие данных за {target_year} год",
                parse_mode="HTML"
            )
    
    async def cmd_custom(self, message: Message, state: FSMContext):
        """Кастомный период - начало ввода"""
        target_year = self._get_target_year()
        await message.answer(
            f"📅 {hbold('Кастомный период')}\n\n"
            f"Доступны данные только за {target_year} год\n"
            f"Введите начальную дату в формате {hcode('ДД.ММ.ГГГГ')}:\n"
            f"Пример: {hcode('01.11.' + str(target_year))}",
            parse_mode="HTML"
        )
        await state.set_state(StatsStates.waiting_custom_start)
    
    async def process_custom_start(self, message: Message, state: FSMContext):
        """Обработка начальной даты кастомного периода"""
        target_year = self._get_target_year()
        try:
            date_str = message.text.strip()
            start_date = datetime.strptime(date_str, '%d.%m.%Y')
            
            if start_date.year != target_year:
                await message.answer(
                    f"⚠️ Нет данных за {start_date.year} год\n"
                    f"Доступны данные только за {target_year} год\n"
                    f"Введите дату в пределах {target_year} года:",
                    parse_mode="HTML"
                )
                return
            
            await state.update_data(start_date=start_date)
            await message.answer(
                f"📅 Начальная дата: {hbold(start_date.strftime('%d.%m.%Y'))}\n"
                f"Теперь введите конечную дату в формате {hcode('ДД.ММ.ГГГГ')}:",
                parse_mode="HTML"
            )
            await state.set_state(StatsStates.waiting_custom_end)
            
        except ValueError:
            await message.answer(
                f"❌ Неверный формат даты\n"
                f"Введите дату в формате {hcode('ДД.ММ.ГГГГ')}:\n"
                f"Пример: {hcode('01.11.' + str(target_year))}",
                parse_mode="HTML"
            )
    
    async def process_custom_end(self, message: Message, state: FSMContext):
        """Обработка конечной даты кастомного периода"""
        target_year = self._get_target_year()
        try:
            date_str = message.text.strip()
            end_date = datetime.strptime(date_str, '%d.%m.%Y')
            
            data = await state.get_data()
            start_date = data.get('start_date')
            if not start_date:
                await message.answer("❌ Ошибка: не найдена начальная дата")
                await state.clear()
                return
            
            if end_date.year != target_year:
                await message.answer(
                    f"⚠️ Нет данных за {end_date.year} год\n"
                    f"Доступны данные только за {target_year} год",
                    parse_mode="HTML"
                )
                await state.clear()
                return
            
            if end_date < start_date:
                await message.answer(
                    "❌ Конечная дата должна быть позже начальной",
                    parse_mode="HTML"
                )
                await state.clear()
                return
            
            await message.answer(
                f"⏳ Загружаю статистику за период:\n"
                f"{hbold(start_date.strftime('%d.%m.%Y'))} - {hbold(end_date.strftime('%d.%m.%Y'))}",
                parse_mode="HTML"
            )
            
            try:
                stats = await self.manager.get_custom_period_stats(start_date, end_date)
                
                if not stats.get('has_data', False):
                    await message.answer(
                        self._format_no_data_message(stats),
                        parse_mode="HTML"
                    )
                    await state.clear()
                    return
                
                await message.answer("🤖 Анализирую данные с помощью AI...")
                ai_analysis = await self.manager.analyze_with_ai(stats)
                response = self._format_stats_message(stats, ai_analysis)
                await message.answer(response, parse_mode="HTML")
                
            except Exception as e:
                logger.error(f"[Handlers] Ошибка при запросе кастомной статистики: {e}", exc_info=True)
                await message.answer(
                    f"❌ Ошибка при получении статистики:\n{hcode(str(e))}",
                    parse_mode="HTML"
                )
            await state.clear()
            
        except ValueError:
            await message.answer(
                f"❌ Неверный формат даты\n"
                f"Введите дату в формате {hcode('ДД.ММ.ГГГГ')}:\n"
                f"Пример: {hcode('31.12.' + str(target_year))}",
                parse_mode="HTML"
            )

    async def cmd_creators(self, message: Message):
        """Список всех креаторов с данными"""
        try:
            creator_ids = await self._get_available_creators()
            
            if not creator_ids:
                await message.answer(
                    "📭 Нет данных о креаторах\n"
                    "После фильтрации данных не осталось креаторов с видео",
                    parse_mode="HTML"
                )
                return
            
            response = f"👥 {hbold('Креаторы с данными')}\n\n"
            response += f"Всего креаторов: {len(creator_ids)}\n"
            response += f"Доступные ID: {', '.join(map(str, creator_ids))}\n\n"
            
            response += f"ℹ️ {hitalic('Используйте /creator для детальной статистики')}"
            
            await message.answer(response, parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"[Handlers] Ошибка при получении списка креаторов: {e}", exc_info=True)
            await message.answer(
                f"❌ Ошибка при получении списка креаторов:\n{hcode(str(e))}",
                parse_mode="HTML"
            )

    async def cmd_creator(self, message: Message, state: FSMContext):
        """Запрос статистики по конкретному креатору"""
        available_ids = await self._get_available_creators()
        if not available_ids:
            await message.answer("📭 Нет данных о креаторах", parse_mode="HTML")
            return
        
        await message.answer(
            f"👥 {hbold('Выберите креатора')}\n\n"
            f"Доступные ID: {', '.join(map(str, available_ids))}\n"
            f"Введите ID креатора вручную (1-19):",
            parse_mode="HTML"
        )
        await state.set_state(StatsStates.waiting_creator_id)

    async def process_creator_id(self, message: Message, state: FSMContext):
        """Обработка введенного ID креатора"""
        try:
            creator_id = int(message.text.strip())
            if creator_id < 1 or creator_id > 19:
                await message.answer("❌ ID креатора должен быть от 1 до 19", parse_mode="HTML")
                return
            await self._show_creator_stats(message, creator_id)
            await state.clear()
        except ValueError:
            await message.answer("❌ Введите число от 1 до 19", parse_mode="HTML")

    async def _show_creator_stats(self, message: Message, creator_id: int, period_type: PeriodType = PeriodType.ALL_TIME,
                                 start_date: Optional[datetime] = None):
        """Показать статистику по креатору"""
        try:
            await message.answer(f"⏳ Загружаю статистику по креатору #{creator_id}...")
            
            # Статистика в зависимости от типа периода
            if period_type == PeriodType.ALL_TIME:
                stats = await self.manager.get_creator_stats(creator_id, period_type)
            elif start_date:
                stats = await self.manager.get_creator_stats(creator_id, period_type, start_date)
            else:
                stats = await self.manager.get_creator_stats(creator_id, period_type)
            
            if not stats.get('has_data', False):
                target_year = self._get_target_year()
                await message.answer(
                    f"🎬 {hbold(f'Креатор #{creator_id}')}\n\n"
                    f"📭 Нет данных за выбранный период\n\n"
                    f"ℹ️ {hitalic('Доступны только данные за:')}\n"
                    f"• {target_year} год\n"
                    f"• Видео: август-октябрь\n"
                    f"• Статистика: ноябрь-декабрь",
                    parse_mode="HTML"
                )
                return
            
            period_names = {
                PeriodType.ALL_TIME.value: "за всё время",
                PeriodType.DAY.value: "за день",
                PeriodType.WEEK.value: "за неделю",
                PeriodType.MONTH.value: "за месяц",
                PeriodType.CUSTOM.value: "за выбранный период"
            }
            period_desc = period_names.get(stats['period_type'], stats['period_type'])
            
            response = f"🎬 {hbold(f'Креатор #{creator_id}')}\n"
            response += f"📊 {hitalic(period_desc.capitalize())}\n\n"
            response += f"📈 {hbold('Статистика:')}\n"
            response += f"├ Видео: {stats['total_videos']}\n"
            response += f"├ Новых видео: {stats['new_videos']}\n"
            response += f"├ Прирост просмотров: {stats['views_gained']:,}\n"
            response += f"├ Прирост лайков: {stats['likes_gained']:,}\n"
            response += f"└ Вовлеченность: {stats['engagement_rate']}%\n\n"
            
            response += f"ℹ️ {hitalic('Данные отфильтрованы:')}\n"
            response += f"• Год: {self._get_target_year()}\n"
            response += f"• Видео: август-октябрь\n"
            response += f"• Статистика: ноябрь-декабрь"
            
            await message.answer(response, parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"[Handlers] Ошибка при получении статистики креатора: {e}", exc_info=True)
            await message.answer(
                f"❌ Ошибка при получении статистики:\n{hcode(str(e))}",
                parse_mode="HTML"
            )

    async def cmd_system(self, message: Message):
        """Системная информация"""
        try:
            system_info = await self.manager.get_system_info()
            response = f"⚙️ {hbold('Системная информация')}\n\n"
            response += f"📅 {hbold('Год данных:')} {system_info['data_year']}\n"
            response += f"🔐 {hbold('Кэш:')} {system_info['cache_size']} записей (TTL: {system_info['cache_ttl']}с)\n\n"
            
            creator_ids = system_info['available_creator_ids']
            if creator_ids:
                response += f"👥 {hbold('Креаторы с данными:')}\n"
                response += f"{', '.join(map(str, creator_ids))}\n"
                response += f"Всего: {len(creator_ids)}\n\n"
            else:
                response += f"👥 {hbold('Креаторы:')} нет данных\n\n"
            
            filters = system_info['filters']
            video_months_names = ['август', 'сентябрь', 'октябрь']
            stats_months_names = ['ноябрь', 'декабрь']
            response += f"🔍 {hbold('Примененные фильтры:')}\n"
            response += f"📹 {hbold('Создание видео:')}\n"
            response += f"├ Месяцы: {', '.join(video_months_names)}\n"
            response += f"├ Начало: {filters['video_creation']['start']}\n"
            response += f"└ Конец: {filters['video_creation']['end']}\n\n"
            response += f"📊 {hbold('Статистика просмотров:')}\n"
            response += f"├ Месяцы: {', '.join(stats_months_names)}\n"
            response += f"├ Начало: {filters['stats_collection']['start']}\n"
            response += f"└ Конец: {filters['stats_collection']['end']}\n\n"
            
            if system_info['gigachat_available']:
                response += f"🤖 {hbold('GigaChat:')} доступен\n"
            else:
                response += f"🤖 {hbold('GigaChat:')} не настроен\n"
            
            await message.answer(response, parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"[Handlers] Ошибка при получении системной информации: {e}", exc_info=True)
            await message.answer(
                f"❌ Ошибка при получении системной информации:\n{hcode(str(e))}",
                parse_mode="HTML"
            )

    async def cmd_ask(self, message: Message, state: FSMContext):
        """Задать вопрос AI"""
        target_year = self._get_target_year()
        await message.answer(
            f"🤖 {hbold('AI Аналитик статистики')}\n\n"
            f"Задайте вопрос о статистике видеоплатформы.\n"
            f"Примеры вопросов:\n"
            f"• Какие креаторы самые популярные?\n"
            f"• Сколько всего видео было создано?\n"
            f"• Какая общая статистика по просмотрам?\n\n"
            f"ℹ️ AI будет отвечать на основе отфильтрованных данных за {target_year} год.",
            parse_mode="HTML"
        )
        await state.set_state(StatsStates.waiting_question)

    async def process_question(self, message: Message, state: FSMContext):
        """Обработка вопроса пользователя"""
        question = message.text.strip()
        if not question:
            await message.answer("❌ Вопрос не может быть пустым")
            return
        
        await message.answer("🤖 Думаю над ответом...")
        try:
            answer = await self.manager.answer_question(question)
            response = f"❓ {hbold('Ваш вопрос:')}\n{question}\n\n"
            response += f"🤖 {hbold('Ответ AI:')}\n{answer}\n\n"
            response += f"ℹ️ {hitalic('На основе данных за ' + str(self._get_target_year()) + ' год')}"
            await message.answer(response, parse_mode="HTML")
            await state.clear()
        except Exception as e:
            logger.error(f"[Handlers] Ошибка при обработке вопроса: {e}", exc_info=True)
            await message.answer(
                f"❌ Ошибка при обработке вопроса:\n{hcode(str(e))}",
                parse_mode="HTML"
            )
            await state.clear()

    # ========== ФОРМАТИРОВАНИЕ СООБЩЕНИЙ ==========

    def _format_no_data_message(self, stats: Dict[str, Any]) -> str:
        """Форматирование сообщения об отсутствии данных"""
        period_type = stats.get('period_type', 'unknown')
        start = stats.get('start_date', datetime.now())
        end = stats.get('end_date', datetime.now())
        target_year = self._get_target_year()
        
        if period_type == "day":
            day_name = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][start.weekday()]
            header = f"📅 {hbold(start.strftime('%d.%m.%Y'))} ({day_name})\n\n"
        elif period_type == "week":
            monday = start
            sunday = monday + timedelta(days=6)
            header = f"📆 {hbold('Неделя')} {monday.strftime('%d.%m')}-{sunday.strftime('%d.%m.%Y')}\n\n"
        elif period_type == "month":
            month_names = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                          'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
            header = f"🗓️ {hbold(month_names[start.month-1])} {start.year}\n\n"
        else:
            header = f"📅 {hbold('Период')} {start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}\n\n"
        
        message = header
        message += f"📭 {hbold('Нет данных')}\n\n"
        if 'message' in stats:
            message += f"{stats['message']}\n\n"
        message += f"ℹ️ {hitalic('Доступны данные только за:')}\n"
        message += f"• {target_year} год\n"
        message += f"• Видео: август-октябрь\n"
        message += f"• Статистика: ноябрь-декабрь"
        return message

    def _format_stats_message(self, stats: Dict[str, Any], ai_analysis: str) -> str:
        """Форматирование сообщения со статистикой"""
        period_type = stats.get('period_type', 'unknown')
        start = stats.get('start_date', datetime.now())
        end = stats.get('end_date', datetime.now())
        target_year = self._get_target_year()
        
        if period_type == "day":
            day_name = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][start.weekday()]
            header = f"📅 {hbold(start.strftime('%d.%m.%Y'))} ({day_name})\n\n"
        elif period_type == "week":
            monday = start
            sunday = monday + timedelta(days=6)
            header = f"📆 {hbold('Неделя')} {monday.strftime('%d.%m')}-{sunday.strftime('%d.%m.%Y')}\n\n"
        elif period_type == "month":
            month_names = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                          'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
            header = f"🗓️ {hbold(month_names[start.month-1])} {start.year}\n\n"
        else:
            header = f"📅 {hbold('Период')} {start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}\n\n"
        
        type_descriptions = {
            "video_creation": "📹 Только создание видео",
            "stats_only": "📊 Только статистика просмотров",
            "mixed": "📈 Смешанные данные"
        }
        data_type_desc = type_descriptions.get(stats.get('data_type', ''), stats.get('data_type', ''))
        if data_type_desc:
            header += f"{data_type_desc}\n\n"
        
        stats_text = f"📈 {hbold('Статистика:')}\n"
        stats_text += f"├ Анализировано видео: {stats.get('total_videos_analyzed', 0)}\n"
        stats_text += f"├ Новых видео: {stats.get('new_videos', 0)}\n"
        stats_text += f"├ Активных креаторов: {stats.get('active_creators', 0)}\n"
        stats_text += f"├ Прирост просмотров: {stats.get('views_gained', 0):,}\n"
        stats_text += f"├ Прирост лайков: {stats.get('likes_gained', 0):,}\n"
        stats_text += f"└ Вовлеченность: {stats.get('engagement_rate', 0)}%\n\n"
        
        top_text = ""
        if stats.get('top_creators'):
            top_text = f"🏆 {hbold('Топ креаторов:')}\n"
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            for i, creator in enumerate(stats['top_creators'][:5]):
                cid = creator.get('human_id', creator.get('creator_id', 'N/A'))
                top_text += f"{medals[i]} {hbold(f'Креатор #{cid}')}: "
                top_text += f"+{creator.get('views_gained', 0):,} просмотров"
                if creator.get('new_videos', 0) > 0:
                    top_text += f" (+{creator['new_videos']} видео)"
                top_text += "\n"
            top_text += "\n"
        
        ai_text = f"🤖 {hbold('AI анализ:')}\n{ai_analysis}\n\n"
        filters_text = f"🔍 {hitalic('Примененные фильтры:')}\n"
        if 'filters_applied' in stats:
            filters = stats['filters_applied']
            filters_text += f"• Год: {filters.get('year', 'Н/Д')}\n"
            filters_text += f"• Видео: {filters.get('video_creation_months', 'Н/Д')}\n"
            filters_text += f"• Статистика: {filters.get('stats_months', 'Н/Д')}\n"
        else:
            filters_text += f"• Год: {target_year}\n"
            filters_text += f"• Видео: август-октябрь\n"
            filters_text += f"• Статистика: ноябрь-декабрь\n"
        
        return header + stats_text + top_text + ai_text + filters_text

    # ========== УТИЛИТНЫЕ МЕТОДЫ ==========

    def get_bot_commands(self) -> List[BotCommand]:
        """Список команд для бота"""
        return self.commands

    def get_router(self) -> Router:
        """Router для регистрации в диспетчере"""
        return self.router


# ========== ФАБРИКА ДЛЯ СОЗДАНИЯ ОБРАБОТЧИКОВ ==========

async def create_date_ai_handlers(manager: DateAIManager) -> Optional[DateAIHandlers]:
    """Создание и инициализирование обработчиков"""
    try:
        handlers = DateAIHandlers(manager)
        logger.info("[DateAIHandlers] Обработчики успешно созданы")
        return handlers
    except Exception as e:
        logger.error(f"[DateAIHandlers] Ошибка создания обработчиков: {e}", exc_info=True)
        return None