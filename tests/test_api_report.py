NON_WITHHELD = {"Q4": 2, "Q5": 3, "Q6": 2, "Q7": 4, "Q8": 4, "Q9": 1,
                "Q10": 1, "Q11": 2, "Q12": 0, "Q13": 0, "Q14": 4, "Q15": 3}


def _submit(client, headers, dog_id):
    resp = client.post(
        "/api/v1/assessment/submit", json=dict(NON_WITHHELD, dog_id=dog_id), headers=headers
    )
    return resp.json()["response"][0]["assessment_id"]


def test_generate_and_list_report(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    assessment_id = _submit(client, headers, dog_id)

    generated = client.post(
        "/api/v1/report/generate", json={"assessment_id": assessment_id}, headers=headers
    )
    assert generated.status_code == 200
    report = generated.json()["response"][0]
    assert report["content"]["assessment_id"] == assessment_id
    assert "theta_irt" in report["content"] or "theta_calibrated" in report["content"]
    assert "flag_irt" in report["content"] and "flag_rf" in report["content"]
    assert report["report_format"] == "pdf"

    listed = client.get("/api/v1/report", headers=headers)
    assert listed.status_code == 200
    assert any(r["report_id"] == report["report_id"] for r in listed.json()["response"])


def test_generate_report_for_nonexistent_assessment_returns_404(registered_owner):
    client, headers = registered_owner
    resp = client.post(
        "/api/v1/report/generate",
        json={"assessment_id": "00000000-0000-0000-0000-000000000000"},
        headers=headers,
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "3001"


def test_download_report_streams_pdf(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    assessment_id = _submit(client, headers, dog_id)
    generated = client.post(
        "/api/v1/report/generate", json={"assessment_id": assessment_id}, headers=headers
    )
    report_id = generated.json()["response"][0]["report_id"]

    resp = client.get(f"/api/v1/report/download/{report_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "attachment" in resp.headers["content-disposition"]
    assert f"report_{report_id}.pdf" in resp.headers["content-disposition"]
    assert resp.content[:5] == b"%PDF-"


def test_download_report_with_missing_file_returns_404(owner_with_dog):
    import os

    client, headers, dog_id = owner_with_dog
    assessment_id = _submit(client, headers, dog_id)
    generated = client.post(
        "/api/v1/report/generate", json={"assessment_id": assessment_id}, headers=headers
    )
    report_id = generated.json()["response"][0]["report_id"]

    # Simulate the PDF file having gone missing from disk after generation.
    from api.services.report_storage import report_pdf_path

    os.remove(report_pdf_path(report_id))

    resp = client.get(f"/api/v1/report/download/{report_id}", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "4003"


def test_download_someone_elses_report_returns_403(api_client, owner_with_dog):
    client, headers, dog_id = owner_with_dog
    assessment_id = _submit(client, headers, dog_id)
    generated = client.post(
        "/api/v1/report/generate", json={"assessment_id": assessment_id}, headers=headers
    )
    report_id = generated.json()["response"][0]["report_id"]

    api_client.post("/api/v1/auth/register", json={
        "user_name": "nosy", "email": "nosy@example.com", "password": "hunter2pass",
    })
    login = api_client.post("/api/v1/auth/login", json={
        "user_name_or_email": "nosy", "password": "hunter2pass",
    })
    other_headers = {"Authorization": f"Bearer {login.json()['response'][0]['access_token']}"}

    resp = api_client.get(f"/api/v1/report/download/{report_id}", headers=other_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "2002"


def test_get_all_reports_requires_admin(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    _submit(client, headers, dog_id)
    resp = client.get("/api/v1/report/all", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "2002"


# ---------------------------------------------------------------- Chromium unavailable

def _failing_renderer():
    from api.services.report_pdf import LazyPdfRenderer

    def _boom():
        raise RuntimeError("Executable doesn't exist")

    return LazyPdfRenderer(factory=_boom)


def test_lazy_renderer_does_not_start_chromium_until_a_report_is_rendered():
    from api.services.report_pdf import LazyPdfRenderer

    started = []

    class _Fake:
        def render_pdf(self, context):
            return b"%PDF-fake"

        def close(self):
            started.append("closed")

    def _factory():
        started.append("started")
        return _Fake()

    lazy = LazyPdfRenderer(factory=_factory)
    assert started == []

    assert lazy.render_pdf({}) == b"%PDF-fake"
    assert lazy.render_pdf({}) == b"%PDF-fake"
    assert started == ["started"]   # launched once, then reused

    lazy.close()
    assert started == ["started", "closed"]


def test_lazy_renderer_retries_after_a_failed_start():
    from api.services.report_pdf import LazyPdfRenderer
    from api.errors import ApiError

    attempts = []

    class _Fake:
        def render_pdf(self, context):
            return b"%PDF-ok"

        def close(self):
            pass

    def _factory():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("not installed yet")
        return _Fake()

    lazy = LazyPdfRenderer(factory=_factory)
    try:
        lazy.render_pdf({})
        raised = None
    except ApiError as e:
        raised = e
    assert raised is not None and raised.code.value == "4004"
    # Installing Chromium later must work without restarting the server.
    assert lazy.render_pdf({}) == b"%PDF-ok"


def test_generate_without_chromium_is_503_and_saves_no_report(owner_with_dog, monkeypatch):
    client, headers, dog_id = owner_with_dog
    monkeypatch.setattr(client.app.state, "pdf_renderer", _failing_renderer())
    assessment_id = _submit(client, headers, dog_id)

    resp = client.post(
        "/api/v1/report/generate", json={"assessment_id": assessment_id}, headers=headers
    )

    assert resp.status_code == 503
    assert resp.json()["code"] == "4004"
    assert client.get("/api/v1/report", headers=headers).json()["response"] == []
    # The rest of the API is unaffected.
    assert client.get("/api/v1/users/me", headers=headers).status_code == 200


def test_app_boots_when_chromium_cannot_start(isolated_pipeline_env, test_db_engine, monkeypatch):
    from fastapi.testclient import TestClient

    from api.app import create_app
    from api.services import report_pdf

    def _no_chromium(self):
        raise RuntimeError("Executable doesn't exist")

    monkeypatch.setattr(report_pdf.PdfRenderer, "__init__", _no_chromium)

    # Before the fix, entering the lifespan here raised and the server exited with status 3.
    with TestClient(create_app()) as client:
        assert client.get("/docs").status_code == 200
