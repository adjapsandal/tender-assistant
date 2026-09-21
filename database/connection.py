import os
from collections.abc import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from database.models import Base

load_dotenv()


class Database:
    def __init__(self):
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker | None = None

    def get_url(self) -> str:
        postgres_user = os.getenv("POSTGRES_USER", "postgres")
        postgres_password = os.getenv("POSTGRES_PASSWORD", "postgres")
        postgres_host = os.getenv("POSTGRES_HOST", "localhost")
        postgres_port = os.getenv("POSTGRES_PORT", "5432")
        postgres_db = os.getenv("POSTGRES_DB", "tender_db")

        return (
            f"postgresql+asyncpg://{postgres_user}:{postgres_password}"
            f"@{postgres_host}:{postgres_port}/{postgres_db}"
        )

    async def connect(self, echo: bool = False) -> None:
        if self.engine is not None:
            return

        database_url = self.get_url()

        self.engine = create_async_engine(
            database_url,
            echo=echo,
            poolclass=NullPool,
        )

        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def disconnect(self) -> None:
        if self.engine is None:
            return

        await self.engine.dispose()
        self.engine = None
        self.session_factory = None

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        if self.session_factory is None:
            await self.connect()

        async with self.session_factory() as session:
            yield session

    async def create_tables(self) -> None:
        if self.engine is None:
            await self.connect()

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_tables(self) -> None:
        if self.engine is None:
            await self.connect()

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)


db = Database()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session for dependency injection"""
    async with db.get_session() as session:
        yield session
