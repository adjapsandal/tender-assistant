"""Общая обвязка для тестов.

Тесты идут по HTTP через httpx.ASGITransport: сервер не поднимается, но
запрос проходит весь стек зависимостей, включая аутентификацию по куке.

База нужна настоящая: модели используют pgvector (`Vector(1536)`), на
SQLite такая схема не создаётся. Параметры подключения берутся из
переменных TEST_POSTGRES_*, по умолчанию — Postgres из docker-compose
на порту 5433.
"""

import os

# Переменные окружения должны быть выставлены до импорта приложения:
# и config, и Database читают их на уровне модуля.
os.environ["POSTGRES_HOST"] = os.getenv("TEST_POSTGRES_HOST", "localhost")
os.environ["POSTGRES_PORT"] = os.getenv("TEST_POSTGRES_PORT", "5433")
os.environ["POSTGRES_USER"] = os.getenv("TEST_POSTGRES_USER", "postgres")
os.environ["POSTGRES_PASSWORD"] = os.getenv("TEST_POSTGRES_PASSWORD", "postgres")
os.environ["POSTGRES_DB"] = os.getenv("TEST_POSTGRES_DB", "tender_test")
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-32"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from web.dependencies import db  # noqa: E402
from web_main import app  # noqa: E402

# Кука с токеном помечена Secure, поэтому клиент должен считать соединение
# защищённым — иначе браузерная логика httpx её не сохранит.
BASE_URL = "https://test"


@pytest.fixture
async def _database():
    """Чистая схема на каждый тест.

    Не autouse: тесты, которым база не нужна, не должны её поднимать.
    Подключается через фикстуру client.
    """
    await db.connect()

    async with db.engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    await db.drop_tables()
    await db.create_tables()

    yield

    await db.drop_tables()
    await db.disconnect()


@pytest.fixture
async def client(_database):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE_URL) as ac:
        yield ac


async def register_and_login(ac: AsyncClient, email: str, company_name: str) -> dict:
    """Завести пользователя вместе с его компанией и войти.

    Регистрация создаёт отдельную компанию на каждого пользователя,
    поэтому два вызова дают две независимые компании.
    """
    password = "StrongPassw0rd!"

    response = await ac.post(
        "/api/auth/register",
        json={"email": email, "password": password, "company_name": company_name},
    )
    assert response.status_code == 201, response.text
    profile = response.json()

    response = await ac.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text

    return profile


@pytest.fixture
async def alice(client):
    """Первый пользователь, уже вошедший в систему."""
    profile = await register_and_login(client, "alice@example.com", "ООО «Альфа»")
    return profile


@pytest.fixture
async def bob_client(alice):
    """Второй пользователь в отдельном клиенте — со своей компанией и кукой."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE_URL) as ac:
        await register_and_login(ac, "bob@example.com", "ООО «Бета»")
        yield ac
