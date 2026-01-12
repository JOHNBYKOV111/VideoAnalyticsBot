import logging

logging.basicConfig(
    level=logging.INFO,  # уровень DEBUG подойдет для разработки, INFO для продакшена
    format="[%(asctime)s][%(levelname)s]: %(message)s",
    filename="bot.log",  # журнал будет записываться в файл
    filemode="a"  # режим добавления записей в конец файла
)

logger = logging.getLogger(__name__)  # получаем общий logger