import re
from datetime import datetime

def clean_sql(sql: str) -> str:
    sql = re.sub(r'``````', '', sql, flags=re.DOTALL | re.IGNORECASE)
    sql = re.sub(r'\s+', ' ', sql).strip()
    # Удаляем пробелы перед ; и сами ; в конце
    sql = re.sub(r'\s*;+\s*$', '', sql)
    return sql + ';'

def format_int(n: int) -> str:
    return f"{n:,}".replace(",", " ")

def format_month_russian(dt: datetime) -> str:
    ...

def format_year_month_russian(year: int, month: int) -> str:
    ...

def parse_date_query(text: str) -> str:
    ...

#   GigaChat АНАЛИЗ
async def gigachat_analyze(question: str, context: dict) -> str:
    prompt = f"""
    Ты аналитик видео платформы. Ответь на вопрос: "{question}"
    
    Доступные данные:
    - {len(context.get('videos', []))} видео с просмотрами, лайками, датами создания
    - Снапшоты: {context.get('total_snapshots', 0)}
    
    Примеры вопросов:
    - Сколько видео у креатора 15 с 1 по 5 ноября 2025?
    - У какого креатора больше всего видео >100k просмотров?
    
    Дай точный числовой ответ + краткое объяснение. Только факты из данных.
    """
    
    # GigaChat интеграция (из config)
    response = await gigachat.generate(prompt)
    return response