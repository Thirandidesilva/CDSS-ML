def test_create_and_list_dog(registered_owner):
    client, headers = registered_owner
    create = client.post(
        "/api/v1/dogs/create", json={"dog_name": "Rex", "dog_breed": "Labrador"}, headers=headers
    )
    assert create.status_code == 200
    dog_id = create.json()["response"][0]["dog_id"]

    listed = client.get("/api/v1/dogs", headers=headers)
    assert listed.status_code == 200
    assert any(d["dog_id"] == dog_id for d in listed.json()["response"])


def test_get_dog_profile(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    resp = client.get(f"/api/v1/dogs/{dog_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["response"][0]["dog_name"] == "Rex"


def test_get_nonexistent_dog_returns_404(registered_owner):
    client, headers = registered_owner
    resp = client.get("/api/v1/dogs/00000000-0000-0000-0000-000000000000", headers=headers)
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

    resp = api_client.get(f"/api/v1/dogs/{dog_id}", headers=other_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "2002"


def test_update_dog(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    resp = client.post(f"/api/v1/dogs/update/{dog_id}", json={"dog_age": 4}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["response"][0]["dog_age"] == 4


def test_delete_dog_then_disappears_from_list(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    resp = client.post(f"/api/v1/dogs/delete/{dog_id}", headers=headers)
    assert resp.status_code == 200

    listed = client.get("/api/v1/dogs", headers=headers)
    assert all(d["dog_id"] != dog_id for d in listed.json()["response"])


def test_get_all_dogs_requires_admin(owner_with_dog):
    client, headers, _dog_id = owner_with_dog
    resp = client.get("/api/v1/dogs/all", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "2002"
