def test_create_and_list_dog(registered_owner):
    client, headers = registered_owner
    create = client.post(
        "/api/v1/dogs/create", json={"dog_name": "Rex", "dog_breed": "Labrador"}, headers=headers
    )
    assert create.status_code == 200
    dog_id = create.json()["response"][0]["dog_id"]

    listed = client.post("/api/v1/dogs/list", json={}, headers=headers)
    assert listed.status_code == 200
    assert any(d["dog_id"] == dog_id for d in listed.json()["response"])


def test_get_dog_profile(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    resp = client.post("/api/v1/dogs/get", json={"dog_id": dog_id}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["response"][0]["dog_name"] == "Rex"


def test_get_nonexistent_dog_returns_404(registered_owner):
    client, headers = registered_owner
    resp = client.post(
        "/api/v1/dogs/get", json={"dog_id": "00000000-0000-0000-0000-000000000000"}, headers=headers
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "2001"


def test_get_someone_elses_dog_returns_403(api_client, owner_with_dog):
    _client, _headers, dog_id = owner_with_dog

    api_client.post("/api/v1/auth/register", json={
        "user_name": "second_owner", "email": "second@example.com", "password": "hunter2pass",
    })
    login = api_client.post("/api/v1/auth/login", json={
        "user_name_or_email": "second_owner", "password": "hunter2pass",
    })
    other_headers = {"Authorization": f"Bearer {login.json()['response'][0]['access_token']}"}

    resp = api_client.post("/api/v1/dogs/get", json={"dog_id": dog_id}, headers=other_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "2002"


def test_update_dog(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    resp = client.post(
        "/api/v1/dogs/update", json={"dog_id": dog_id, "dog_age": 4}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["response"][0]["dog_age"] == 4


def test_delete_dog_then_disappears_from_list(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    resp = client.post("/api/v1/dogs/delete", json={"dog_id": dog_id}, headers=headers)
    assert resp.status_code == 200

    listed = client.post("/api/v1/dogs/list", json={}, headers=headers)
    assert all(d["dog_id"] != dog_id for d in listed.json()["response"])


def test_get_all_dogs_requires_admin(owner_with_dog):
    client, headers, _dog_id = owner_with_dog
    resp = client.get("/api/v1/dogs/all", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "2002"


def test_list_dogs_with_explicit_own_user_id(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    user_id = client.get("/api/v1/users/me", headers=headers).json()["response"][0]["user_id"]
    resp = client.post("/api/v1/dogs/list", json={"user_id": user_id}, headers=headers)
    assert resp.status_code == 200
    assert any(d["dog_id"] == dog_id for d in resp.json()["response"])


def test_list_someone_elses_dogs_by_user_id_returns_403(api_client, owner_with_dog):
    _client, _headers, dog_id = owner_with_dog
    owner_user_id = _client.get("/api/v1/users/me", headers=_headers).json()["response"][0]["user_id"]

    api_client.post("/api/v1/auth/register", json={
        "user_name": "nosy_owner", "email": "nosy_owner@example.com", "password": "hunter2pass",
    })
    login = api_client.post("/api/v1/auth/login", json={
        "user_name_or_email": "nosy_owner", "password": "hunter2pass",
    })
    other_headers = {"Authorization": f"Bearer {login.json()['response'][0]['access_token']}"}

    resp = api_client.post("/api/v1/dogs/list", json={"user_id": owner_user_id}, headers=other_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "2002"
