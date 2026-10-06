"""Refresh tokens: the access token lasts 30 minutes and the app trades its refresh token
for a new pair shortly before that, without the user signing in again."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models import RefreshToken

CREDENTIALS = {"user_name": "refresher", "email": "refresher@example.com", "password": "hunter2pass"}


@pytest.fixture
def signed_in(api_client):
    """(client, login answer) for a freshly registered and logged-in owner."""
    api_client.post("/api/v1/auth/register", json=CREDENTIALS)
    login = api_client.post("/api/v1/auth/login", json={
        "user_name_or_email": CREDENTIALS["user_name"], "password": CREDENTIALS["password"],
    })
    assert login.status_code == 200, login.text
    return api_client, login.json()["response"][0]


def _refresh(client, token):
    return client.post("/api/v1/auth/refresh", json={"refresh_token": token})


def _stored(engine):
    with Session(engine) as session:
        return list(session.scalars(select(RefreshToken).order_by(RefreshToken.created_at)))


def test_login_returns_a_refresh_token_and_both_lifetimes(signed_in):
    _client, answer = signed_in
    assert answer["refresh_token"]
    from api.config import get_settings

    settings = get_settings()
    assert answer["expires_in"] == settings.access_token_expire_minutes * 60
    assert answer["refresh_expires_in"] == settings.refresh_token_expire_days * 24 * 60 * 60


def test_the_default_access_token_lifetime_is_thirty_minutes():
    from api.config import Settings

    assert Settings.model_fields["access_token_expire_minutes"].default == 30
    assert Settings.model_fields["refresh_token_expire_days"].default == 30


def test_the_access_token_lifetime_follows_the_setting(api_client, monkeypatch):
    from api.config import get_settings

    monkeypatch.setattr(get_settings(), "access_token_expire_minutes", 15)
    api_client.post("/api/v1/auth/register", json=CREDENTIALS)
    login = api_client.post("/api/v1/auth/login", json={
        "user_name_or_email": "refresher", "password": "hunter2pass",
    })
    assert login.json()["response"][0]["expires_in"] == 15 * 60


def test_refresh_gives_a_working_access_token_and_a_new_refresh_token(signed_in):
    client, answer = signed_in
    resp = _refresh(client, answer["refresh_token"])
    assert resp.status_code == 200, resp.text
    renewed = resp.json()["response"][0]

    assert renewed["refresh_token"] != answer["refresh_token"]
    assert renewed["expires_in"] == answer["expires_in"]
    me = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {renewed['access_token']}"})
    assert me.status_code == 200
    assert me.json()["response"][0]["user_name"] == "refresher"


def test_refresh_needs_no_access_token(signed_in):
    client, answer = signed_in
    # No Authorization header at all: the access token has usually just expired.
    assert _refresh(client, answer["refresh_token"]).status_code == 200


def test_the_new_refresh_token_can_be_used_in_turn(signed_in):
    client, answer = signed_in
    second = _refresh(client, answer["refresh_token"]).json()["response"][0]
    third = _refresh(client, second["refresh_token"])
    assert third.status_code == 200


def test_a_refresh_token_used_long_ago_is_a_theft_signal_and_ends_the_family(signed_in, test_db_engine):
    client, answer = signed_in
    newer = _refresh(client, answer["refresh_token"]).json()["response"][0]

    # Pretend the first token was traded in a while ago, outside the grace window.
    with Session(test_db_engine) as session:
        first = session.scalars(select(RefreshToken).order_by(RefreshToken.created_at)).first()
        first.used_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        session.commit()

    replay = _refresh(client, answer["refresh_token"])
    assert replay.status_code == 401
    assert replay.json()["code"] == "1008"
    # The copy and the legitimate newer token are both finished.
    assert _refresh(client, newer["refresh_token"]).status_code == 401


def test_a_quick_repeat_is_forgiven_for_a_lost_answer(signed_in):
    client, answer = signed_in
    _refresh(client, answer["refresh_token"])
    # The phone never saw that answer and sends the same token again moments later.
    again = _refresh(client, answer["refresh_token"])
    assert again.status_code == 200
    assert again.json()["response"][0]["refresh_token"]


def test_an_expired_refresh_token_is_refused(signed_in, test_db_engine):
    client, answer = signed_in
    with Session(test_db_engine) as session:
        row = session.scalars(select(RefreshToken)).one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()

    resp = _refresh(client, answer["refresh_token"])
    assert resp.status_code == 401
    assert resp.json()["code"] == "1008"


def test_unknown_and_malformed_tokens_are_refused(api_client):
    for token in ("not-a-real-token", "", "a" * 500):
        resp = _refresh(api_client, token)
        assert resp.status_code == 401, token
        assert resp.json()["code"] == "1008"


def test_an_access_token_is_not_a_refresh_token_and_the_reverse(signed_in):
    client, answer = signed_in
    assert _refresh(client, answer["access_token"]).status_code == 401

    me = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {answer['refresh_token']}"})
    assert me.status_code == 401


def test_only_the_hash_is_stored(signed_in, test_db_engine):
    _client, answer = signed_in
    rows = _stored(test_db_engine)
    assert len(rows) == 1
    assert answer["refresh_token"] not in (rows[0].token_hash, str(rows[0].token_id))
    assert len(rows[0].token_hash) == 64


def test_logout_ends_the_session_and_never_fails(signed_in):
    client, answer = signed_in
    out = client.post("/api/v1/auth/logout", json={"refresh_token": answer["refresh_token"]})
    assert out.status_code == 200
    assert _refresh(client, answer["refresh_token"]).status_code == 401

    # Signing out with a token the server has never seen still succeeds.
    assert client.post("/api/v1/auth/logout", json={"refresh_token": "nope"}).status_code == 200


def test_logging_out_one_session_leaves_another_signed_in(signed_in):
    client, first = signed_in
    second = client.post("/api/v1/auth/login", json={
        "user_name_or_email": "refresher", "password": "hunter2pass",
    }).json()["response"][0]

    client.post("/api/v1/auth/logout", json={"refresh_token": first["refresh_token"]})

    assert _refresh(client, first["refresh_token"]).status_code == 401
    assert _refresh(client, second["refresh_token"]).status_code == 200


def test_deleting_the_account_ends_every_session(signed_in):
    client, answer = signed_in
    client.post("/api/v1/users/delete", headers={"Authorization": f"Bearer {answer['access_token']}"})

    resp = _refresh(client, answer["refresh_token"])
    assert resp.status_code == 401
    assert resp.json()["code"] == "1008"
