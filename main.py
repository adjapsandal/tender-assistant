import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))

load_dotenv()

from create_bot import create_bot, create_dispatcher, set_bot_commands
from database.connection import Database
from handlers.user_private import router, set_bot
from middlewares.db import DBMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def main():
    bot = create_bot()
    dp = create_dispatcher()

    db = Database()
    await db.connect()
    logger.info("Database connected")

    dp.update.middleware(DBMiddleware(db))
    set_bot(bot)
    dp.include_router(router)

    await set_bot_commands(bot)
    logger.info("Bot commands set")

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Starting polling...")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        logger.info("Stopping bot...")
        await db.disconnect()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {e}", exc_info=True)
        sys.exit(1)
