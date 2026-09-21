"""Регистрация, вход и выход."""


async def test_register_creates_user_and_company(client):
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "new@example.com",
            "password": "StrongPassw0rd!",
            "company_name": "ООО «Новая»",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert body["company_id"] > 0
    assert body["is_active"] is True
    # Пароль не должен возвращаться ни в каком виде.
    assert "password" not in body
    assert "hashed_password" not in body


async def test_register_rejects_duplicate_email(client, alice):
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "alice@example.com",
            "password": "AnotherPassw0rd!",
            "company_name": "ООО «Клон»",
        },
    )

    assert response.status_code == 400


async def test_login_sets_cookie(client):
    await client.post(
        "/api/auth/register",
        json={
            "email": "login@example.com",
            "password": "StrongPassw0rd!",
            "company_name": "ООО «Вход»",
        },
    )

    response = await client.post(
        "/api/auth/login",
        json={"email": "login@example.com", "password": "StrongPassw0rd!"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]

    cookie = response.cookies.get("access_token")
    assert cookie

    set_cookie_header = response.headers["set-cookie"].lower()
    # Токен не должен быть доступен из JavaScript.
    assert "httponly" in set_cookie_header


async def test_login_rejects_wrong_password(client, alice):
    response = await client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "WrongPassword!"},
    )

    assert response.status_code == 401


async def test_login_rejects_unknown_email(client):
    response = await client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "StrongPassw0rd!"},
    )

    assert response.status_code == 401


async def test_me_requires_authentication(client):
    response = await client.get("/api/auth/me")

    assert response.status_code == 401


async def test_me_returns_current_user(client, alice):
    response = await client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == "alice@example.com"
    assert response.json()["company_id"] == alice["company_id"]


async def test_logout_clears_cookie(client, alice):
    response = await client.post("/api/auth/logout")
    assert response.status_code == 200

    response = await client.get("/api/auth/me")
    assert response.status_code == 401


async def test_two_users_get_separate_companies(client, alice, bob_client):
    response = await bob_client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["company_id"] != alice["company_id"]
