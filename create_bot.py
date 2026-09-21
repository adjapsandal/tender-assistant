import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from common.bot_cmds_list import private
from common.config import config

logger = logging.getLogger(__name__)


def create_bot() -> Bot:
    if not config.TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")
    return Bot(token=config.TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def create_dispatcher() -> Dispatcher:
    return Dispatcher(storage=MemoryStorage())


async def set_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(private)
