import re


def _extract_code(body: str) -> str:
    match = re.search(r"\d{6}", body)
    assert match, f"no 6-digit code found in email body: {body!r}"
    return match.group(0)


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


def test_forget_password_then_reset(api_client, sent_emails):
    api_client.post("/api/v1/auth/register", json={
        "user_name": "dana", "email": "dana@example.com", "password": "old-password",
    })
    forgot = api_client.post("/api/v1/auth/forget-password", json={"email": "dana@example.com"})
    assert forgot.status_code == 200
    assert forgot.json()["code"] == "0000"
    assert "reset_token" not in forgot.json()["response"][0]  # no longer handed back in-band

    code = _extract_code(sent_emails[-1][2])
    verified = api_client.post(
        "/api/v1/auth/forget-password/verify-otp", json={"email": "dana@example.com", "otp": code}
    )
    assert verified.status_code == 200
    token = verified.json()["response"][0]["reset_token"]

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


def test_forget_username(api_client, sent_emails):
    # No OTP step — one call, one email, since a username isn't a secret worth gating.
    api_client.post("/api/v1/auth/register", json={
        "user_name": "erin", "email": "erin@example.com", "password": "correcthorse",
    })
    resp = api_client.post("/api/v1/auth/forget-username", json={"email": "erin@example.com"})
    assert resp.status_code == 200
    assert resp.json()["code"] == "0000"
    assert "user_name" not in resp.json()["response"][0]  # never handed back in-band, only emailed

    # the username itself only ever appears in the (captured, not returned) email
    username_email = sent_emails[-1]
    assert username_email[0] == "erin@example.com"
    assert "erin" in username_email[2]


def test_forget_username_unknown_email_returns_business_code(api_client, sent_emails):
    resp = api_client.post("/api/v1/auth/forget-username", json={"email": "nobody@example.com"})
    assert resp.status_code == 200
    assert resp.json()["code"] == "1003"
    assert sent_emails == []  # no email sent for a non-existent account


def test_otp_expired_is_rejected(api_client, sent_emails, test_db_engine):
    api_client.post("/api/v1/auth/register", json={
        "user_name": "grace", "email": "grace@example.com", "password": "correcthorse",
    })
    api_client.post("/api/v1/auth/forget-password", json={"email": "grace@example.com"})
    code = _extract_code(sent_emails[-1][2])

    # Force the stored code into the past instead of sleeping or mocking the clock.
    # Must use test_db_engine directly (the same DB the API's overridden get_db uses) —
    # api.db.SessionLocal points at create_app()'s own separate throwaway DB, not this one.
    from datetime import datetime, timedelta, timezone

    from sqlalchemy.orm import Session

    from api.enums import OtpPurpose
    from api.models import OtpCode, User

    with Session(test_db_engine) as db:
        user = db.query(User).filter(User.email == "grace@example.com").one()
        row = (
            db.query(OtpCode)
            .filter(OtpCode.user_id == user.user_id, OtpCode.purpose == OtpPurpose.FORGET_PASSWORD)
            .one()
        )
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()

    resp = api_client.post(
        "/api/v1/auth/forget-password/verify-otp", json={"email": "grace@example.com", "otp": code}
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == "1006"


def test_otp_too_many_attempts_locks_out_even_correct_code(api_client, sent_emails):
    api_client.post("/api/v1/auth/register", json={
        "user_name": "henry", "email": "henry@example.com", "password": "correcthorse",
    })
    api_client.post("/api/v1/auth/forget-password", json={"email": "henry@example.com"})
    code = _extract_code(sent_emails[-1][2])

    for _ in range(5):  # default otp_max_attempts
        wrong = api_client.post(
            "/api/v1/auth/forget-password/verify-otp",
            json={"email": "henry@example.com", "otp": "000000" if code != "000000" else "111111"},
        )
        assert wrong.json()["code"] == "1006"

    resp = api_client.post(
        "/api/v1/auth/forget-password/verify-otp", json={"email": "henry@example.com", "otp": code}
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == "1006"


def test_requesting_new_otp_invalidates_previous_one(api_client, sent_emails):
    api_client.post("/api/v1/auth/register", json={
        "user_name": "iris", "email": "iris@example.com", "password": "correcthorse",
    })
    api_client.post("/api/v1/auth/forget-password", json={"email": "iris@example.com"})
    first_code = _extract_code(sent_emails[-1][2])

    api_client.post("/api/v1/auth/forget-password", json={"email": "iris@example.com"})
    second_code = _extract_code(sent_emails[-1][2])

    stale = api_client.post(
        "/api/v1/auth/forget-password/verify-otp", json={"email": "iris@example.com", "otp": first_code}
    )
    assert stale.json()["code"] == "1006"

    fresh = api_client.post(
        "/api/v1/auth/forget-password/verify-otp", json={"email": "iris@example.com", "otp": second_code}
    )
    assert fresh.status_code == 200
    assert fresh.json()["code"] == "0000"


# ---------------------------------------------------------------- email provider failures

def _resend_refuses(monkeypatch):
    """Makes the real send_email run, but Resend itself refuse — exactly what a sandbox
    account does for any recipient other than its owner."""
    import resend
    from resend.exceptions import ResendError

    def _refuse(params):
        raise ResendError(
            code=403, error_type="validation_error",
            message="You can only send testing emails to your own email address (owner@example.com).",
            suggested_action="verify a domain",
        )

    monkeypatch.setattr(resend.Emails, "send", _refuse)


def test_forget_username_when_resend_refuses_is_a_clean_502_not_a_500(registered_owner, monkeypatch):
    client, _ = registered_owner
    _resend_refuses(monkeypatch)

    resp = client.post("/api/v1/auth/forget-username", json={"email": "owner1@example.com"})

    assert resp.status_code == 502
    assert resp.json()["code"] == "1007"
    # The provider's own wording (it names the account owner's address) stays in the logs.
    assert "owner@example.com" not in resp.text
    assert "testing emails" not in resp.text


def test_forget_password_when_resend_refuses_is_a_clean_502(registered_owner, monkeypatch):
    client, _ = registered_owner
    _resend_refuses(monkeypatch)

    resp = client.post("/api/v1/auth/forget-password", json={"email": "owner1@example.com"})

    assert resp.status_code == 502
    assert resp.json()["code"] == "1007"


def test_a_network_failure_reaching_resend_is_also_a_502(registered_owner, monkeypatch):
    import requests
    import resend

    def _down(params):
        raise requests.ConnectionError("dns failure")

    monkeypatch.setattr(resend.Emails, "send", _down)
    client, _ = registered_owner
    resp = client.post("/api/v1/auth/forget-username", json={"email": "owner1@example.com"})
    assert resp.status_code == 502
    assert resp.json()["code"] == "1007"


def test_unknown_email_is_still_reported_before_any_email_is_attempted(api_client, monkeypatch):
    import resend

    monkeypatch.setattr(resend.Emails, "send", lambda params: (_ for _ in ()).throw(AssertionError("must not send")))
    resp = api_client.post("/api/v1/auth/forget-username", json={"email": "nobody@example.com"})
    assert resp.json()["code"] == "1003"
