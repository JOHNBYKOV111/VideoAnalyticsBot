import re
from typing import Dict, Any, List
from datetime import datetime

class ResponseFormatter:
    """Форматирует SQL результаты в человеко-читаемые ответы"""
    
    @staticmethod
    def format_number(num: Any) -> str:
        """Форматирует число с разделителями"""
        try:
            if isinstance(num, (int, float)):
                if isinstance(num, float):
                    if num.is_integer():
                        return f"{int(num):,}".replace(",", " ")
                    return f"{num:,.2f}".replace(",", " ").replace(".", ",")
                return f"{num:,}".replace(",", " ")
            return str(num)
        except:
            return str(num)
    
    @staticmethod
    def format_datetime(dt_str: str) -> str:
        """Форматирует дату в читаемый вид"""
        if not dt_str:
            return ""
        
        try:
            # Убираем timezone если есть
            dt_str = str(dt_str)
            if '+' in dt_str:
                dt_str = dt_str.split('+')[0]
            if 'T' in dt_str:
                dt_str = dt_str.replace('T', ' ')
            
            # Парсим дату
            formats = [
                '%Y-%m-%d %H:%M:%S.%f',
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d'
            ]
            
            for fmt in formats:
                try:
                    dt = datetime.strptime(dt_str, fmt)
                    return dt.strftime('%d.%m.%Y %H:%M')
                except ValueError:
                    continue
            
            return dt_str[:16]
        except:
            return dt_str[:10] if len(dt_str) > 10 else dt_str
    
    @staticmethod
    def calculate_engagement(views: int, likes: int) -> float:
        """Рассчитывает engagement rate"""
        if views and views > 0:
            return (likes / views) * 100
        return 0.0
    
    @staticmethod
    def format_single_result(result: Dict[str, Any], query: str) -> str:
        """Форматирует один результат"""
        query_lower = query.lower()
        
        # Если это количество видео
        for key, value in result.items():
            if "count" in key.lower():
                count = value
                # Проверяем, это общее количество или по креатору
                if "сколько" in query_lower and "видео" in query_lower:
                    # Ищем номер креатора в запросе
                    numbers = re.findall(r'\d+', query)
                    if numbers and ("креатор" in query_lower or "creator" in query_lower or "автор" in query_lower):
                        return f"📊 У креатора №{numbers[0]}: {ResponseFormatter.format_number(count)} видео"
                    else:
                        return f"📊 Всего видео в базе: {ResponseFormatter.format_number(count)}"
        
        # Если это среднее значение
        for key, value in result.items():
            if "avg" in key.lower():
                if "просмотр" in query_lower:
                    return f"📈 Среднее количество просмотров на видео: {ResponseFormatter.format_number(value)}"
                elif "лайк" in query_lower:
                    return f"📈 Среднее количество лайков на видео: {ResponseFormatter.format_number(value)}"
                elif "комментар" in query_lower:
                    return f"📈 Среднее количество комментариев на видео: {ResponseFormatter.format_number(value)}"
                return f"📊 Среднее значение: {ResponseFormatter.format_number(value)}"
        
        # Если это сумма
        for key, value in result.items():
            if "sum" in key.lower() or "total" in key.lower():
                if "просмотр" in query_lower:
                    return f"👁️ Всего просмотров: {ResponseFormatter.format_number(value)}"
                elif "лайк" in query_lower:
                    return f"👍 Всего лайков: {ResponseFormatter.format_number(value)}"
                elif "комментар" in query_lower:
                    return f"💬 Всего комментариев: {ResponseFormatter.format_number(value)}"
                return f"📊 Сумма: {ResponseFormatter.format_number(value)}"
        
        # Если это детали видео
        if "views_count" in result and "likes_count" in result:
            video_id = result.get('id', 'N/A')
            if len(str(video_id)) > 10:
                video_id = str(video_id)[:8] + "..."
            
            creator_num = result.get('creator_human_number', '?')
            views = result.get('views_count', 0)
            likes = result.get('likes_count', 0)
            comments = result.get('comments_count', 0)
            reports = result.get('reports_count', 0)
            
            engagement = ResponseFormatter.calculate_engagement(views, likes)
            created_at = ResponseFormatter.format_datetime(result.get('video_created_at', ''))
            
            title = "🎬 **Информация о видео**"
            if "самое популярное" in query_lower or "самое просматриваемое" in query_lower:
                title = "🏆 **Самое популярное видео**"
            elif "лучшее" in query_lower:
                title = "⭐ **Лучшее видео**"
            
            return (
                f"{title}\n\n"
                f"📹 **ID:** `{video_id}`\n"
                f"👤 **Креатор №{creator_num}**\n"
                f"📅 **Создано:** {created_at}\n\n"
                f"📊 **Статистика:**\n"
                f"• 👁️ Просмотры: {ResponseFormatter.format_number(views)}\n"
                f"• 👍 Лайки: {ResponseFormatter.format_number(likes)}\n"
                f"• 💬 Комментарии: {ResponseFormatter.format_number(comments)}\n"
                f"• ⚠️ Репорты: {ResponseFormatter.format_number(reports)}\n"
                f"• 📈 Вовлеченность: {engagement:.1f}%\n\n"
                f"_Engagement = (лайки / просмотры) × 100%_"
            )
        
        # Если это статистика креатора
        if "video_count" in result:
            creator_num = result.get('creator_human_number', '?')
            video_count = result.get('video_count', 0)
            total_views = result.get('total_views', 0)
            total_likes = result.get('total_likes', 0)
            
            avg_views = total_views / video_count if video_count > 0 else 0
            avg_likes = total_likes / video_count if video_count > 0 else 0
            
            title = "👤 **Статистика креатора**"
            if "больше всего видео" in query_lower or "самый продуктивный" in query_lower:
                title = "👑 **Самый продуктивный креатор**"
            
            return (
                f"{title}\n\n"
                f"👤 **Креатор №{creator_num}**\n\n"
                f"📊 **Статистика:**\n"
                f"• 📹 Всего видео: {ResponseFormatter.format_number(video_count)}\n"
                f"• 👁️ Всего просмотров: {ResponseFormatter.format_number(total_views)}\n"
                f"• 👍 Всего лайков: {ResponseFormatter.format_number(total_likes)}\n"
                f"• 📈 Средние показатели на видео:\n"
                f"  - Просмотры: {ResponseFormatter.format_number(avg_views)}\n"
                f"  - Лайки: {ResponseFormatter.format_number(avg_likes)}"
            )
        
        # Дефолтный формат для одного результата
        response = "📊 **Результат анализа:**\n\n"
        for key, value in result.items():
            if "id" in key.lower() and len(str(value)) > 10:
                response += f"• **{key}:** `{str(value)[:8]}...`\n"
            elif "count" in key.lower() or "number" in key.lower():
                response += f"• **{key}:** {ResponseFormatter.format_number(value)}\n"
            elif "date" in key.lower() or "created" in key.lower() or "updated" in key.lower():
                response += f"• **{key}:** {ResponseFormatter.format_datetime(str(value))}\n"
            else:
                response += f"• **{key}:** {ResponseFormatter.format_number(value)}\n"
        
        return response
    
    @staticmethod
    def format_multiple_results(results: List[Dict[str, Any]], query: str) -> str:
        """Форматирует несколько результатов"""
        query_lower = query.lower()
        
        # Если это топ видео
        if "топ" in query_lower or "самые" in query_lower or "лучшие" in query_lower:
            # Определяем критерий из запроса
            if "лайк" in query_lower:
                criteria = "лайкам"
                sort_field = "likes_count"
            elif "просмотр" in query_lower:
                criteria = "просмотрам"
                sort_field = "views_count"
            elif "комментар" in query_lower:
                criteria = "комментариям"
                sort_field = "comments_count"
            else:
                criteria = "просмотрам"
                sort_field = "views_count"
            
            response = f"🏆 **Топ {len(results)} видео по {criteria}:**\n\n"
            
            for i, video in enumerate(results, 1):
                video_id = video.get('id', 'N/A')
                if len(str(video_id)) > 10:
                    video_id = str(video_id)[:8] + "..."
                
                creator_num = video.get('creator_human_number', '?')
                views = video.get('views_count', 0)
                likes = video.get('likes_count', 0)
                
                engagement = ResponseFormatter.calculate_engagement(views, likes)
                
                response += (
                    f"{i}. `{video_id}` (Креатор №{creator_num})\n"
                    f"   👁️ {ResponseFormatter.format_number(views)} | "
                    f"👍 {ResponseFormatter.format_number(likes)} | "
                    f"📈 {engagement:.1f}%\n\n"
                )
            
            return response
        
        # Если это список креаторов
        elif "креатор" in query_lower or "creator" in query_lower or "автор" in query_lower:
            response = "👥 **Статистика по креаторам:**\n\n"
            
            for i, creator in enumerate(results, 1):
                creator_num = creator.get('creator_human_number', '?')
                video_count = creator.get('video_count', 0)
                total_views = creator.get('total_views', 0)
                total_likes = creator.get('total_likes', 0)
                
                response += (
                    f"{i}. **Креатор №{creator_num}**\n"
                    f"   📹 Видео: {ResponseFormatter.format_number(video_count)}\n"
                    f"   👁️ Просмотры: {ResponseFormatter.format_number(total_views)}\n"
                    f"   👍 Лайки: {ResponseFormatter.format_number(total_likes)}\n\n"
                )
            
            return response
        
        # Общий формат для табличных данных
        else:
            response = f"📊 **Найдено записей:** {len(results)}\n\n"
            
            # Показываем только первые 5 результатов
            for i, row in enumerate(results[:5], 1):
                response += f"{i}. "
                fields_displayed = 0
                
                # Приоритетные поля для отображения
                priority_fields = ['creator_human_number', 'views_count', 'likes_count',
                                 'comments_count', 'video_created_at', 'count', 'avg', 'sum']
                
                for field in priority_fields:
                    if field in row and fields_displayed < 2:
                        value = row[field]
                        if 'date' in field or 'created' in field:
                            value = ResponseFormatter.format_datetime(str(value))
                        else:
                            value = ResponseFormatter.format_number(value)
                        
                        response += f"{field}: {value} | "
                        fields_displayed += 1
                
                # Если не нашли приоритетные, берем первые 2
                if fields_displayed == 0:
                    for key, value in list(row.items())[:2]:
                        response += f"{key}: {ResponseFormatter.format_number(value)} | "
                
                response = response.rstrip(' | ')
                response += "\n"
            
            if len(results) > 5:
                response += f"\n... и ещё {len(results) - 5} записей"
            
            return response
    
    @staticmethod
    def format_response(query: str, results: List[Dict[str, Any]]) -> str:
        """Основная функция форматирования"""
        if not results:
            return "📊 По вашему запросу ничего не найдено."
        
        # Один результат
        if len(results) == 1:
            return ResponseFormatter.format_single_result(results[0], query)
        
        # Несколько результатов
        return ResponseFormatter.format_multiple_results(results, query)