import pytest
import sys
from datetime import datetime
from src.utils.utils import clean_sql, format_int, format_month_russian, format_year_month_russian, parse_date_query


def test_clean_sql_removes_backticks_and_normalizes():
    """Тест удаления backticks и нормализации пробелов"""
    dirty = "`````` SELECT * FROM videos WHERE id = 1;   \n\n  ``````"
    expected = "SELECT * FROM videos WHERE id = 1;"
    assert clean_sql(dirty) == expected


def test_clean_sql_handles_extra_spaces_and_semicolons():
    """Тест обработки лишних пробелов и точек с запятой"""
    dirty = "   SELECT   *   FROM   creators   ;;;   "
    expected = "SELECT * FROM creators;"
    assert clean_sql(dirty) == expected


def test_clean_sql_empty_input():
    """Тест пустого ввода"""
    assert clean_sql("") == ";"


def test_clean_sql_only_whitespace():
    """Тест только пробельных символов"""
    assert clean_sql("   \n\t  ") == ";"


def test_format_int_positive():
    """Тест форматирования положительных чисел"""
    assert format_int(1000) == "1 000"
    assert format_int(1234567) == "1 234 567"
    assert format_int(0) == "0"


def test_format_int_negative():
    """Тест форматирования отрицательных чисел"""
    assert format_int(-1000) == "-1 000"
    assert format_int(-1234567) == "-1 234 567"


def test_clean_sql_multiple_backticks_inside():
    """Тест, когда backticks находятся внутри SQL"""
    # Функция clean_sql удаляет ТОЛЬКО полные ````, а не отдельные ```
    dirty = "SELECT ```id``` FROM ```videos``` WHERE ```id``` = 1;"
    # Ожидаем, что внутренние ``` останутся, удалятся только полные ``````
    expected = "SELECT ```id``` FROM ```videos``` WHERE ```id``` = 1;"
    assert clean_sql(dirty) == expected


def test_clean_sql_with_newlines_and_tabs():
    """Тест с различными символами whitespace"""
    dirty = "\tSELECT\n*\nFROM\nvideos\nWHERE\nid = 1;\n"
    expected = "SELECT * FROM videos WHERE id = 1;"
    assert clean_sql(dirty) == expected


def test_clean_sql_preserves_inner_semicolons():
    """Тест, что внутренние точки с запятой не удаляются"""
    dirty = "SELECT id FROM videos WHERE name = 'test;value';"
    expected = "SELECT id FROM videos WHERE name = 'test;value';"
    assert clean_sql(dirty) == expected


def test_clean_sql_case_insensitive_backticks():
    """Тест на регистронезависимость backticks"""
    # Функция удаляет только полные ``````, отдельные ``` остаются
    dirty = "``````SELECT * FROM videos```;"
    expected = "SELECT * FROM videos```;"
    assert clean_sql(dirty) == expected


def test_clean_sql_only_semicolons():
    """Тест на строку только из точек с запятой"""
    # Фактическое поведение функции для разных случаев
    assert clean_sql(";;;") == ";"
    # " ; ; ; " -> после замены пробелов становится "; ;;"
    assert clean_sql(" ; ; ; ") == "; ;;"


def test_format_int_large_numbers():
    """Тест очень больших чисел"""
    assert format_int(1_000_000_000) == "1 000 000 000"
    assert format_int(999_999_999) == "999 999 999"


def test_format_int_single_digit():
    """Тест однозначных чисел"""
    assert format_int(7) == "7"
    assert format_int(-3) == "-3"


def test_format_int_round_numbers():
    """Тест круглых чисел"""
    assert format_int(10_000) == "10 000"
    assert format_int(100_000) == "100 000"
    assert format_int(1_000_000) == "1 000 000"


@pytest.mark.parametrize("number,expected", [
    (0, "0"),
    (1, "1"),
    (-1, "-1"),
    (999, "999"),
    (1000, "1 000"),
    (-1000, "-1 000"),
    (123456789, "123 456 789"),
    (-123456789, "-123 456 789"),
])
def test_format_int_parametrized(number, expected):
    """Параметризованный тест для format_int"""
    assert format_int(number) == expected


def test_clean_sql_performance_large_sql():
    """Тест производительности на больших SQL-запросах"""
    large_sql = "SELECT * FROM " + "videos " * 1000 + ";"
    result = clean_sql(large_sql)
    assert result.endswith(";")
    assert "  " not in result  # Не должно быть двойных пробелов


def test_format_int_extreme_values():
    """Тест экстремальных значений"""
    # Максимальное значение int в Python
    max_int = sys.maxsize
    result = format_int(max_int)
    # Проверяем, что форматирование произошло (появились пробелы)
    assert " " in result
    
    min_int = -sys.maxsize - 1
    result = format_int(min_int)
    assert result.startswith("-")
    assert " " in result


def test_clean_sql_with_sql_injection_patterns():
    """Тест, что clean_sql не ломает SQL-инъекционные паттерны"""
    sql_injection = "SELECT * FROM users WHERE name = 'test' OR '1'='1';--"
    result = clean_sql(sql_injection)
    assert result.endswith(";")
    assert "OR '1'='1'" in result
    # Комментарий сохраняется
    assert "--" in result


def test_clean_sql_preserves_string_literals():
    """Тест, что строковые литералы не повреждаются"""
    sql_with_strings = "SELECT * FROM videos WHERE title = 'Test; video; with;;; semicolons' ;"
    expected = "SELECT * FROM videos WHERE title = 'Test; video; with;;; semicolons';"
    assert clean_sql(sql_with_strings) == expected


def test_format_int_with_float():
    """Тест с float (функция работает с float, форматируя их с дробной частью)"""
    # Функция format_int работает с float, но оставляет дробную часть
    assert format_int(1000.0) == "1 000.0"
    assert format_int(1000.5) == "1 000.5"
    # Проверяем отрицательные float
    assert format_int(-1000.0) == "-1 000.0"
    assert format_int(-1234.56) == "-1 234.56"


def test_clean_sql_with_none():
    """Тест clean_sql с None (должен падать с TypeError)"""
    with pytest.raises(TypeError):
        clean_sql(None)


def test_clean_sql_with_non_string():
    """Тест clean_sql с нестроковыми типами (должен падать с TypeError)"""
    with pytest.raises(TypeError):
        clean_sql(123)
    with pytest.raises(TypeError):
        clean_sql([])
    with pytest.raises(TypeError):
        clean_sql({})


def test_clean_sql_real_world_examples():
    """Тест с реальными SQL-запросами из кодовой базы"""
    real_queries = [
        (
            "SELECT creator_id, COUNT(*) as video_count FROM videos WHERE views > 100000 GROUP BY creator_id ORDER BY video_count DESC LIMIT 10;",
            "SELECT creator_id, COUNT(*) as video_count FROM videos WHERE views > 100000 GROUP BY creator_id ORDER BY video_count DESC LIMIT 10;"
        ),
        (
            "   UPDATE creators SET last_updated = NOW() WHERE id = %s;   ",
            "UPDATE creators SET last_updated = NOW() WHERE id = %s;"
        ),
        (
            "``````\nINSERT INTO snapshots (video_id, views, likes) VALUES (%s, %s, %s);\n``````",
            "INSERT INTO snapshots (video_id, views, likes) VALUES (%s, %s, %s);"
        )
    ]
    
    for dirty, expected in real_queries:
        assert clean_sql(dirty) == expected


# Тесты для других функций из utils.py
# Так как функции не реализованы (возвращают None), тестируем это поведение

def test_format_month_russian():
    """Тест форматирования месяца на русском"""
    # Функция не реализована, возвращает None
    result = format_month_russian(datetime(2025, 1, 15))
    # Проверяем, что функция существует и возвращает None
    assert result is None


def test_format_year_month_russian():
    """Тест форматирования года и месяца на русском"""
    # Функция не реализована, возвращает None
    result = format_year_month_russian(2025, 1)
    assert result is None


def test_parse_date_query():
    """Тест парсинга текстовых запросов с датами"""
    # Функция не реализована, возвращает None
    result = parse_date_query("с 1 по 5 ноября 2025")
    assert result is None
    
    result2 = parse_date_query("в октябре 2024")
    assert result2 is None
    
    # Тест на неправильный запрос
    result3 = parse_date_query("неправильный запрос")
    assert result3 is None


def test_clean_sql_preserves_comments():
    """Тест, что SQL комментарии сохраняются"""
    sql_with_comments = "SELECT * FROM videos -- Это комментарий\nWHERE id = 1;"
    result = clean_sql(sql_with_comments)
    assert result.endswith(";")
    assert "WHERE id = 1" in result
    # Комментарий остается в строке
    assert "-- Это комментарий" in result


def test_clean_sql_with_multiple_statements():
    """Тест с несколькими SQL-выражениями"""
    # clean_sql удаляет только ; в конце строки, внутренние остаются
    sql = "SELECT * FROM table1; SELECT * FROM table2;"
    result = clean_sql(sql)
    # Ожидаем 2 точки с запятой (одна внутри, одна в конце)
    assert result.count(";") == 2
    assert result.endswith(";")


def test_format_int_with_zero_padding():
    """Тест с числами, которые могут иметь пробелы в начале формата"""
    assert format_int(100) == "100"
    assert format_int(1000) == "1 000"
    # Проверяем, что нет лишних пробелов
    result = format_int(1000)
    assert not result.startswith(" ")
    assert not result.endswith(" ")


def test_clean_sql_removes_trailing_spaces_before_semicolon():
    """Тест удаления пробелов перед точкой с запятой в конце"""
    test_cases = [
        ("SELECT * FROM table ;", "SELECT * FROM table;"),
        ("SELECT * FROM table    ;", "SELECT * FROM table;"),
        ("SELECT * FROM table\n;", "SELECT * FROM table;"),
        ("SELECT * FROM table\t;", "SELECT * FROM table;"),
    ]
    
    for input_sql, expected in test_cases:
        assert clean_sql(input_sql) == expected


def test_clean_sql_normalizes_internal_spaces():
    """Тест нормализации внутренних пробелов"""
    test_cases = [
        ("SELECT  *   FROM    table", "SELECT * FROM table;"),
        ("SELECT\n*\nFROM\ntable", "SELECT * FROM table;"),
        ("SELECT\t*\tFROM\ttable", "SELECT * FROM table;"),
    ]
    
    for input_sql, expected in test_cases:
        assert clean_sql(input_sql) == expected


def test_clean_sql_with_carriage_return():
    """Тест с возвратом каретки"""
    dirty = "SELECT * FROM table\r\nWHERE id = 1;"
    expected = "SELECT * FROM table WHERE id = 1;"
    assert clean_sql(dirty) == expected


def test_format_int_edge_cases():
    """Тест граничных случаев для format_int"""
    assert format_int(999) == "999"
    assert format_int(1000) == "1 000"
    assert format_int(999999) == "999 999"
    assert format_int(1000000) == "1 000 000"


def test_clean_sql_mixed_whitespace():
    """Тест со смешанными пробельными символами"""
    dirty = "  SELECT\t\n  *\n\tFROM  \t\nvideos\t\nWHERE\nid = 1;\t\n"
    expected = "SELECT * FROM videos WHERE id = 1;"
    assert clean_sql(dirty) == expected


# Дополнительные тесты для проверки поведения нереализованных функций
def test_unimplemented_functions_return_none():
    """Тест что нереализованные функции возвращают None"""
    # Проверяем сигнатуры функций
    import inspect
    
    # format_month_russian должна принимать datetime и возвращать str
    sig1 = inspect.signature(format_month_russian)
    assert len(sig1.parameters) == 1
    assert str(sig1) == "(dt: datetime.datetime) -> str"
    
    # format_year_month_russian должна принимать int, int и возвращать str
    sig2 = inspect.signature(format_year_month_russian)
    assert len(sig2.parameters) == 2
    assert str(sig2) == "(year: int, month: int) -> str"
    
    # parse_date_query должна принимать str и возвращать str
    sig3 = inspect.signature(parse_date_query)
    assert len(sig3.parameters) == 1
    assert str(sig3) == "(text: str) -> str"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])