"""Регрессия на закрытие API.

До правок авторизацию требовали только четыре эндпоинта из двадцати семи:
остальные отдавали данные любому анониму, а компания была захардкожена
как `COMPANY_ID = 5`, поэтому пользователь работал не со своей компанией,
а с чужой.

Здесь проверяется и то, и другое: каждый непубличный маршрут отвечает 401
без куки, и данные одной компании не видны другой.
"""

import pytest
from fastapi.routing import APIRoute

from web_main import app

# Единственные маршруты, которые обязаны работать без авторизации.
PUBLIC_ROUTES = {
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
}

# Служебные маршруты FastAPI, к приложению отношения не имеют.
SKIPPED_PREFIXES = ("/openapi.json", "/docs", "/redoc")


def _protected_routes():
    routes = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path.startswith(SKIPPED_PREFIXES):
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            if (method, route.path) in PUBLIC_ROUTES:
                continue
            routes.append((method, route.path))
    return sorted(routes)


PROTECTED_ROUTES = _protected_routes()


def test_route_inventory_is_not_empty():
    """Страховка: если маршруты перестанут находиться, тест ниже станет пустым."""
    assert len(PROTECTED_ROUTES) >= 20


@pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
async def test_route_requires_authentication(client, method, path):
    """Любой непубличный маршрут без куки отвечает 401."""
    url = path.format(
        **{
            "tender_id": 1,
            "sku_id": 1,
            "won_tender_id": 1,
            "document_id": 1,
            "file_id": "1",
            "tender_number": "123",
            "filename": "a.docx",
        }
    )

    response = await client.request(method, url, json={})

    assert response.status_code == 401, f"{method} {path} доступен без авторизации: {response.status_code}"


async def test_sku_list_is_scoped_to_own_company(client, alice, bob_client):
    created = await client.post(
        "/api/skus",
        json={"name": "Контейнеры", "keywords": "контейнер, бак"},
    )
    assert created.status_code == 201

    own = await client.get("/api/skus")
    assert own.status_code == 200
    assert len(own.json()) == 1

    # У второй компании своих наборов нет — чужой она видеть не должна.
    other = await bob_client.get("/api/skus")
    assert other.status_code == 200
    assert other.json() == []


async def test_foreign_sku_cannot_be_updated(client, alice, bob_client):
    created = await client.post(
        "/api/skus",
        json={"name": "Пробирки", "keywords": "пробирка"},
    )
    sku_id = created.json()["id"]

    response = await bob_client.put(
        f"/api/skus/{sku_id}",
        json={"name": "Взломано"},
    )
    assert response.status_code == 404

    # Убеждаемся, что значение действительно не изменилось.
    own = await client.get("/api/skus")
    assert own.json()[0]["name"] == "Пробирки"


async def test_foreign_sku_cannot_be_deleted(client, alice, bob_client):
    created = await client.post(
        "/api/skus",
        json={"name": "Пакеты", "keywords": "пакет"},
    )
    sku_id = created.json()["id"]

    response = await bob_client.delete(f"/api/skus/{sku_id}")
    assert response.status_code == 404

    own = await client.get("/api/skus")
    assert len(own.json()) == 1


async def test_foreign_tender_is_not_found(client, alice, bob_client):
    """Тендера с таким id нет ни у кого — ответ 404, а не 500 и не чужие данные."""
    response = await bob_client.get("/api/tenders/1")
    assert response.status_code == 404


async def test_won_tenders_list_is_scoped_to_own_company(client, alice, bob_client):
    response = await bob_client.get("/api/won-tenders")

    assert response.status_code == 200
    assert response.json()["count"] == 0
