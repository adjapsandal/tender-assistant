from database.connection import Database

db = Database()


async def get_session():
    if db.session_factory is None:
        await db.connect()

    async with db.session_factory() as session:
        yield session


async def startup_db():
    # Схему разворачивает Alembic (`alembic upgrade head`). Раньше приложение
    # на старте вызывало create_all: он создаёт таблицы в обход миграций,
    # молча пропускает уже существующие и не применяет изменения схемы,
    # из-за чего база и миграции расходятся.
    await db.connect()


async def shutdown_db():
    await db.disconnect()
