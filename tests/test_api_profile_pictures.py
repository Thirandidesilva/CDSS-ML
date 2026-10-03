import base64
import hashlib
from types import SimpleNamespace

import pytest
import requests

from api.services import cloudinary

SECRET = "test-api-secret"
CONFIGURED = SimpleNamespace(
    cloudinary_cloud_name="democloud", cloudinary_api_key="111222333", cloudinary_api_secret=SECRET
)
UNCONFIGURED = SimpleNamespace(
    cloudinary_cloud_name=None, cloudinary_api_key=None, cloudinary_api_secret=None
)

PHOTO_BYTES = b"\xff\xd8\xff\xe0fake-jpeg-bytes"
PHOTO = "data:image/jpeg;base64," + base64.b64encode(PHOTO_BYTES).decode()
HOSTED_URL = "https://res.cloudinary.com/democloud/image/upload/v1/photo.jpg"


class FakeCloudinary:
    """Stands in for requests.post so no test ever contacts Cloudinary."""

    def __init__(self):
        self.calls = []
        self.status = 200
        self.body = {"secure_url": HOSTED_URL}
        self.error = None

    def post(self, url, data=None, files=None, timeout=None):
        self.calls.append(SimpleNamespace(url=url, data=data, files=files, timeout=timeout))
        if self.error:
            raise self.error
        return SimpleNamespace(status_code=self.status, json=lambda: self.body)


@pytest.fixture
def fake_cloudinary(monkeypatch):
    fake = FakeCloudinary()
    monkeypatch.setattr(cloudinary, "get_settings", lambda: CONFIGURED)
    monkeypatch.setattr(cloudinary.requests, "post", fake.post)
    return fake


def _expected_signature(fields: dict) -> str:
    # Independent of services/cloudinary.py: Cloudinary's documented rule — signed fields
    # sorted by name, "&"-joined, secret appended, SHA-1.
    signed = {k: fields[k] for k in ("allowed_formats", "invalidate", "overwrite", "public_id", "timestamp")}
    text = "&".join(f"{k}={signed[k]}" for k in sorted(signed)) + SECRET
    return hashlib.sha1(text.encode()).hexdigest()


def _me(client, headers):
    return client.get("/api/v1/users/me", headers=headers).json()["response"][0]


# ------------------------------------------------------------------ users/update

def test_user_photo_is_uploaded_and_the_cloudinary_url_is_stored(registered_owner, fake_cloudinary):
    client, headers = registered_owner
    resp = client.post("/api/v1/users/update", json={"profile_picture": PHOTO}, headers=headers)

    assert resp.status_code == 200
    assert resp.json()["response"][0]["profile_picture"] == HOSTED_URL
    assert _me(client, headers)["profile_picture"] == HOSTED_URL

    call = fake_cloudinary.calls[0]
    assert call.url == "https://api.cloudinary.com/v1_1/democloud/image/upload"
    assert call.data["public_id"] == f"pawsitivity/users/{_me(client, headers)['user_id']}"
    assert call.data["api_key"] == "111222333"
    assert call.data["overwrite"] == "true" and call.data["invalidate"] == "true"
    assert call.data["signature"] == _expected_signature(call.data)
    filename, raw, mime = call.files["file"]
    assert raw == PHOTO_BYTES and mime == "image/jpeg"


def test_the_api_secret_never_leaves_the_server(registered_owner, fake_cloudinary):
    client, headers = registered_owner
    resp = client.post("/api/v1/users/update", json={"profile_picture": PHOTO}, headers=headers)
    sent = fake_cloudinary.calls[0]
    assert SECRET not in sent.data.values()
    assert SECRET not in resp.text


def test_an_existing_url_is_stored_as_is_without_touching_cloudinary(registered_owner, fake_cloudinary):
    client, headers = registered_owner
    resp = client.post(
        "/api/v1/users/update", json={"profile_picture": "https://example.com/me.jpg"}, headers=headers
    )
    assert resp.json()["response"][0]["profile_picture"] == "https://example.com/me.jpg"
    assert fake_cloudinary.calls == []


def test_uploads_not_configured_is_503_and_nothing_changes(registered_owner, monkeypatch):
    monkeypatch.setattr(cloudinary, "get_settings", lambda: UNCONFIGURED)
    client, headers = registered_owner
    resp = client.post(
        "/api/v1/users/update", json={"first_name": "Changed", "profile_picture": PHOTO}, headers=headers
    )
    assert resp.status_code == 503
    assert resp.json()["code"] == "5001"
    me = _me(client, headers)
    assert me["first_name"] is None and me["profile_picture"] is None


@pytest.mark.parametrize("bad", [
    "data:text/plain;base64," + base64.b64encode(b"hello").decode(),   # not an image type
    "data:image/jpeg;base64,this is not base64!!",                       # not decodable
    "data:image/jpeg;base64,",                                           # no payload
    "data:image/gif;base64," + base64.b64encode(b"GIF89a").decode(),     # type not allowed
    "data:image/jpeg,not-base64-encoded",                                # missing ;base64
])
def test_invalid_images_are_400_before_any_upload(registered_owner, fake_cloudinary, bad):
    client, headers = registered_owner
    resp = client.post("/api/v1/users/update", json={"profile_picture": bad}, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "5003"
    assert fake_cloudinary.calls == []


def test_oversized_image_is_400(registered_owner, fake_cloudinary, monkeypatch):
    monkeypatch.setattr(cloudinary, "MAX_IMAGE_BYTES", 8)
    client, headers = registered_owner
    resp = client.post("/api/v1/users/update", json={"profile_picture": PHOTO}, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "5003"
    assert fake_cloudinary.calls == []


@pytest.mark.parametrize("failure", ["network", "rejected", "no_url"])
def test_cloudinary_failures_are_502_and_the_profile_is_untouched(registered_owner, fake_cloudinary, failure):
    if failure == "network":
        fake_cloudinary.error = requests.ConnectionError("boom: secret details")
    elif failure == "rejected":
        fake_cloudinary.status = 401
        fake_cloudinary.body = {"error": {"message": "Invalid api_key 111222333"}}
    else:
        fake_cloudinary.body = {"public_id": "x"}
    client, headers = registered_owner

    resp = client.post(
        "/api/v1/users/update", json={"first_name": "Changed", "profile_picture": PHOTO}, headers=headers
    )

    assert resp.status_code == 502
    assert resp.json()["code"] == "5002"
    assert "111222333" not in resp.text and "secret" not in resp.text.lower()
    me = _me(client, headers)
    assert me["first_name"] is None and me["profile_picture"] is None


# ------------------------------------------------------------------ dogs

def test_dog_created_with_a_photo_stores_the_cloudinary_url(registered_owner, fake_cloudinary):
    client, headers = registered_owner
    resp = client.post(
        "/api/v1/dogs/create", json={"dog_name": "Rex", "profile_picture": PHOTO}, headers=headers
    )
    assert resp.status_code == 200
    dog = resp.json()["response"][0]
    assert dog["profile_picture"] == HOSTED_URL
    assert fake_cloudinary.calls[0].data["public_id"] == f"pawsitivity/dogs/{dog['dog_id']}"
    assert fake_cloudinary.calls[0].data["signature"] == _expected_signature(fake_cloudinary.calls[0].data)


def test_dog_create_with_a_failed_upload_creates_no_dog(registered_owner, fake_cloudinary):
    fake_cloudinary.error = requests.ConnectionError("down")
    client, headers = registered_owner
    resp = client.post(
        "/api/v1/dogs/create", json={"dog_name": "Rex", "profile_picture": PHOTO}, headers=headers
    )
    assert resp.status_code == 502
    assert client.post("/api/v1/dogs/list", json={}, headers=headers).json()["response"] == []


def test_dog_update_with_a_photo(owner_with_dog, fake_cloudinary):
    client, headers, dog_id = owner_with_dog
    resp = client.post(
        "/api/v1/dogs/update",
        json={"dog_id": dog_id, "dog_name": "Rexy", "profile_picture": PHOTO},
        headers=headers,
    )
    assert resp.status_code == 200
    dog = resp.json()["response"][0]
    assert dog["dog_name"] == "Rexy" and dog["profile_picture"] == HOSTED_URL
    assert fake_cloudinary.calls[0].data["public_id"] == f"pawsitivity/dogs/{dog_id}"


def test_dog_update_with_a_failed_upload_changes_nothing(owner_with_dog, fake_cloudinary):
    fake_cloudinary.status = 500
    client, headers, dog_id = owner_with_dog
    resp = client.post(
        "/api/v1/dogs/update",
        json={"dog_id": dog_id, "dog_name": "Rexy", "profile_picture": PHOTO},
        headers=headers,
    )
    assert resp.status_code == 502
    dog = client.post("/api/v1/dogs/get", json={"dog_id": dog_id}, headers=headers).json()["response"][0]
    assert dog["dog_name"] == "Rex" and dog["profile_picture"] is None


def test_someone_elses_dog_is_403_and_nothing_is_uploaded(owner_with_dog, fake_cloudinary):
    client, _, dog_id = owner_with_dog
    client.post("/api/v1/auth/register", json={
        "user_name": "intruder", "email": "intruder@example.com", "password": "hunter2pass",
    })
    token = client.post("/api/v1/auth/login", json={
        "user_name_or_email": "intruder", "password": "hunter2pass",
    }).json()["response"][0]["access_token"]

    resp = client.post(
        "/api/v1/dogs/update",
        json={"dog_id": dog_id, "profile_picture": PHOTO},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert fake_cloudinary.calls == []


def test_signing_changes_when_any_signed_field_changes():
    base = {"public_id": "a", "timestamp": "1", "overwrite": "true"}
    original = cloudinary.sign_params(base, SECRET)
    assert cloudinary.sign_params({**base, "public_id": "b"}, SECRET) != original
    assert cloudinary.sign_params({**base, "timestamp": "2"}, SECRET) != original
    assert cloudinary.sign_params(base, "other-secret") != original
