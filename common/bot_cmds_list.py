"""
Список команд бота для главного меню.
"""

from aiogram.types import BotCommand

# Команды для личных сообщений
private = [
    BotCommand(command="start", description="Запустить бота"),
]
