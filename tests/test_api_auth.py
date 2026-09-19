def test_openapi_docs_render(api_client):
    resp = api_client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/api/v1/assessment/submit" in resp.json()["paths"]


def test_register_then_login(api_client):
    resp = api_client.post("/api/v1/auth/register", json={
        "user_name": "alice", "email": "alice@example.com", "password": "correcthorse",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "0000"
    assert body["response"][0]["user_name"] == "alice"

    login = api_client.post("/api/v1/auth/login", json={
        "user_name_or_email": "alice", "password": "correcthorse",
    })
    assert login.status_code == 200
    login_body = login.json()
    assert login_body["code"] == "0000"
    assert "access_token" in login_body["response"][0]


def test_duplicate_email_returns_business_code(api_client):
    payload = {"user_name": "bob", "email": "bob@example.com", "password": "hunter2pass"}
    api_client.post("/api/v1/auth/register", json=payload)
    resp = api_client.post(
        "/api/v1/auth/register",
        json={"user_name": "bob2", "email": "bob@example.com", "password": "hunter2pass"},
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == "1002"


def test_login_wrong_password_returns_business_code(api_client):
    api_client.post("/api/v1/auth/register", json={
        "user_name": "carol", "email": "carol@example.com", "password": "correcthorse",
    })
    resp = api_client.post("/api/v1/auth/login", json={
        "user_name_or_email": "carol", "password": "wrong-password",
    })
    assert resp.status_code == 200
    assert resp.json()["code"] == "1001"


def test_missing_token_returns_401(api_client):
    resp = api_client.get("/api/v1/users/me")
    assert resp.status_code == 401
    assert resp.json()["code"] == "1000"


def test_forget_password_then_reset(api_client):
    api_client.post("/api/v1/auth/register", json={
        "user_name": "dana", "email": "dana@example.com", "password": "old-password",
    })
    forgot = api_client.post("/api/v1/auth/forget-password", json={"email": "dana@example.com"})
    assert forgot.status_code == 200
    token = forgot.json()["response"][0]["reset_token"]

    reset = api_client.post(
        "/api/v1/auth/reset-password", json={"reset_token": token, "new_password": "new-password"}
    )
    assert reset.status_code == 200
    assert reset.json()["code"] == "0000"

    old_login = api_client.post(
        "/api/v1/auth/login", json={"user_name_or_email": "dana", "password": "old-password"}
    )
    assert old_login.json()["code"] == "1001"

    new_login = api_client.post(
        "/api/v1/auth/login", json={"user_name_or_email": "dana", "password": "new-password"}
    )
    assert new_login.json()["code"] == "0000"

    # single-use: the same token can't be replayed after the password changed
    replay = api_client.post(
        "/api/v1/auth/reset-password", json={"reset_token": token, "new_password": "another"}
    )
    assert replay.json()["code"] == "1004"


def test_forget_username(api_client):
    api_client.post("/api/v1/auth/register", json={
        "user_name": "erin", "email": "erin@example.com", "password": "correcthorse",
    })
    resp = api_client.post("/api/v1/auth/forget-username", json={"email": "erin@example.com"})
    assert resp.status_code == 200
    assert resp.json()["response"][0]["user_name"] == "erin"
