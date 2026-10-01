def test_get_profile(registered_owner):
    client, headers = registered_owner
    resp = client.get("/api/v1/users/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()["response"][0]
    assert body["user_name"] == "owner1"
    assert "password_hash" not in body
    assert "password" not in body


def test_update_profile(registered_owner):
    client, headers = registered_owner
    resp = client.post(
        "/api/v1/users/update", json={"first_name": "Owner", "phone_number": "0771234567"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()["response"][0]
    assert body["first_name"] == "Owner"
    assert body["phone_number"] == "0771234567"


def test_delete_profile_then_token_still_decodes_but_account_inactive(registered_owner):
    client, headers = registered_owner
    resp = client.post("/api/v1/users/delete", headers=headers)
    assert resp.status_code == 200

    after = client.get("/api/v1/users/me", headers=headers)
    assert after.status_code == 401
    assert after.json()["code"] == "1000"


def test_get_all_users_requires_admin(registered_owner):
    client, headers = registered_owner
    resp = client.get("/api/v1/users", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "2002"
