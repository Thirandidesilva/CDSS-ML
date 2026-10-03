import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import run_pipeline  # noqa: E402

# Settings() requires these; tests never touch a real DB, so the values just need to be
# well-formed. Set once, before any Settings()/get_settings() call in the whole session.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET", "test-secret-key-do-not-use-in-prod")
# Resend fields are required (no default) so a real deployment fails loudly if
# unconfigured — tests never send real email (see sent_emails below), so these values
# just need to be well-formed enough for Settings() to construct.
os.environ.setdefault("RESEND_API_KEY", "test")
os.environ.setdefault("EMAIL_FROM_ADDRESS", "noreply@example.com")


@pytest.fixture
def isolated_pipeline_env(tmp_path, monkeypatch):
    """Copies real reference/results artifacts into tmp_path and points run_pipeline
    at them, so tests never read/write the real (git-tracked) data/reference or results.
    """
    ref = tmp_path / "reference"
    results = tmp_path / "results"
    models = tmp_path / "models"
    ref.mkdir()
    results.mkdir()
    models.mkdir()

    shutil.copy(ROOT / "data" / "reference" / "params_own.csv", ref / "params_own.csv")
    shutil.copy(ROOT / "results" / "scored_responses.csv", results / "scored_responses.csv")
    shutil.copy(ROOT / "results" / "phenotype_profiles.csv", results / "phenotype_profiles.csv")
    shutil.copy(ROOT / "models" / "phenotype_rf.joblib", models / "phenotype_rf.joblib")
    shutil.copy(ROOT / "models" / "phenotype_rf_metadata.json", models / "phenotype_rf_metadata.json")

    monkeypatch.setattr(run_pipeline, "REF", ref)
    monkeypatch.setattr(run_pipeline, "RESULTS", results)
    monkeypatch.setattr(run_pipeline, "MODELS", models)
    return run_pipeline


@pytest.fixture
def test_db_engine():
    """A fresh in-memory SQLite DB per test. StaticPool keeps it alive across the
    TestClient's requests; the FK pragma matters because SQLite disables foreign key
    enforcement by default, unlike Postgres."""
    from sqlalchemy import create_engine, event
    from sqlalchemy.pool import StaticPool

    from api.db import Base

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def api_client(isolated_pipeline_env, test_db_engine):
    """A TestClient wired to the throwaway DB above and to the fixture pipeline data,
    so API tests never touch a real database or the real data/reference|results files.
    """
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from api.app import create_app
    from api.db import get_db

    TestSession = sessionmaker(bind=test_db_engine, autoflush=False, autocommit=False)

    def _override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db
    # A context manager, not a bare TestClient(app): Starlette only runs ASGI
    # startup/shutdown (lifespan) handlers inside __enter__/__exit__.
    with TestClient(app) as client:
        yield client


@pytest.fixture
def registered_owner(api_client):
    """Registers and logs in one owner-role user. Returns (client, auth_headers)."""
    resp = api_client.post("/api/v1/auth/register", json={
        "user_name": "owner1", "email": "owner1@example.com", "password": "hunter2pass",
    })
    assert resp.status_code == 200, resp.text

    login = api_client.post("/api/v1/auth/login", json={
        "user_name_or_email": "owner1", "password": "hunter2pass",
    })
    assert login.status_code == 200, login.text
    token = login.json()["response"][0]["access_token"]
    return api_client, {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sent_emails(monkeypatch):
    """Captures (to, subject, body) tuples instead of really sending — patches the
    attribute on the email module itself (not a name imported elsewhere), which is
    exactly what routers/auth.py's `email_service.send_email(...)` call style is for.
    """
    sent = []

    def _fake_send(to, subject, body):
        sent.append((to, subject, body))

    from api.services import email as email_service

    monkeypatch.setattr(email_service, "send_email", _fake_send)
    return sent


@pytest.fixture
def owner_with_dog(registered_owner):
    """Builds on registered_owner by also creating one dog. Returns (client, headers, dog_id)."""
    client, headers = registered_owner
    resp = client.post(
        "/api/v1/dogs/create", json={"dog_name": "Rex", "dog_breed": "Labrador"}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    dog_id = resp.json()["response"][0]["dog_id"]
    return client, headers, dog_id
