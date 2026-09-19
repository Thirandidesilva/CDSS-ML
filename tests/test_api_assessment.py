# Under the isolated_pipeline_env fixture (params_own.csv + cohort-relative norms
# derived on the fly, not the calibrated production defaults), theta_se for these two
# payloads lands on opposite sides of SE_THRESHOLD=0.50 the other way round from how
# they were named against the retired /assess endpoint's real (calibrated) data —
# verified directly against run_pipeline.score_case() under this exact fixture.
NON_WITHHELD = {"Q4": 2, "Q5": 2, "Q6": 1, "Q7": 3, "Q8": 1, "Q9": 0,
                "Q10": 4, "Q11": 2, "Q12": 2, "Q13": 1, "Q14": 3, "Q15": 0}
WITHHELD = {"Q4": 2, "Q5": 3, "Q6": 2, "Q7": 4, "Q8": 4, "Q9": 1,
            "Q10": 1, "Q11": 2, "Q12": 0, "Q13": 0, "Q14": 4, "Q15": 3}


def test_get_all_questions(owner_with_dog):
    client, headers, _dog_id = owner_with_dog
    resp = client.get("/api/v1/assessment/questions", headers=headers)
    assert resp.status_code == 200
    codes = {q["item_code"] for q in resp.json()["response"]}
    assert codes == {f"Q{i}" for i in range(4, 16)}


def test_normal_case_returns_full_audit(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    resp = client.post(
        "/api/v1/assessment/submit", json=dict(NON_WITHHELD, dog_id=dog_id), headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "0000"
    result = body["response"][0]
    assert result["recommendation"]["withheld"] is False
    for key in ("theta_irt", "theta_se", "severity_band", "phenotype", "rf_confidence",
                "flag_irt", "flag_rf", "session_number"):
        assert key in result
    assert result["session_number"] == 1


def test_withheld_case_returns_200_not_an_error(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    resp = client.post(
        "/api/v1/assessment/submit", json=dict(WITHHELD, dog_id=dog_id), headers=headers
    )
    assert resp.status_code == 200
    result = resp.json()["response"][0]
    assert result["recommendation"]["withheld"] is True
    assert result["recommendation"]["withheld_reason"] is not None


def test_missing_item_returns_422_naming_field(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    payload = {k: v for k, v in NON_WITHHELD.items() if k != "Q15"}
    resp = client.post(
        "/api/v1/assessment/submit", json=dict(payload, dog_id=dog_id), headers=headers
    )
    assert resp.status_code == 422
    assert any("Q15" in str(e["loc"]) for e in resp.json()["detail"])


def test_out_of_range_value_returns_422_naming_field(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    payload = dict(NON_WITHHELD, Q4=7, dog_id=dog_id)
    resp = client.post("/api/v1/assessment/submit", json=payload, headers=headers)
    assert resp.status_code == 422
    assert any("Q4" in str(e["loc"]) for e in resp.json()["detail"])


def test_wrong_type_returns_422_naming_field(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    payload = dict(NON_WITHHELD, Q4="high", dog_id=dog_id)
    resp = client.post("/api/v1/assessment/submit", json=payload, headers=headers)
    assert resp.status_code == 422
    assert any("Q4" in str(e["loc"]) for e in resp.json()["detail"])


def test_submit_for_someone_elses_dog_returns_403(api_client, owner_with_dog):
    _client, _headers, dog_id = owner_with_dog
    api_client.post("/api/v1/auth/register", json={
        "user_name": "intruder", "email": "intruder@example.com", "password": "hunter2pass",
    })
    login = api_client.post("/api/v1/auth/login", json={
        "user_name_or_email": "intruder", "password": "hunter2pass",
    })
    other_headers = {"Authorization": f"Bearer {login.json()['response'][0]['access_token']}"}

    resp = api_client.post(
        "/api/v1/assessment/submit", json=dict(NON_WITHHELD, dog_id=dog_id), headers=other_headers
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "2002"


def test_session_number_increments(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    first = client.post(
        "/api/v1/assessment/submit", json=dict(NON_WITHHELD, dog_id=dog_id), headers=headers
    )
    second = client.post(
        "/api/v1/assessment/submit", json=dict(NON_WITHHELD, dog_id=dog_id), headers=headers
    )
    assert first.json()["response"][0]["session_number"] == 1
    assert second.json()["response"][0]["session_number"] == 2


def test_list_dog_assessment_and_get_result(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    submitted = client.post(
        "/api/v1/assessment/submit", json=dict(NON_WITHHELD, dog_id=dog_id), headers=headers
    )
    assessment_id = submitted.json()["response"][0]["assessment_id"]

    listed = client.get(f"/api/v1/assessment/dog/{dog_id}", headers=headers)
    assert listed.status_code == 200
    assert any(a["assessment_id"] == assessment_id for a in listed.json()["response"])

    result = client.get(f"/api/v1/assessment/{assessment_id}", headers=headers)
    assert result.status_code == 200
    assert result.json()["response"][0]["assessment_id"] == assessment_id


def test_get_nonexistent_assessment_returns_404(registered_owner):
    client, headers = registered_owner
    resp = client.get("/api/v1/assessment/00000000-0000-0000-0000-000000000000", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "3001"


def test_delete_assessment_then_disappears_from_list(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    submitted = client.post(
        "/api/v1/assessment/submit", json=dict(NON_WITHHELD, dog_id=dog_id), headers=headers
    )
    assessment_id = submitted.json()["response"][0]["assessment_id"]

    deleted = client.post(f"/api/v1/assessment/delete/{assessment_id}", headers=headers)
    assert deleted.status_code == 200

    listed = client.get(f"/api/v1/assessment/dog/{dog_id}", headers=headers)
    assert all(a["assessment_id"] != assessment_id for a in listed.json()["response"])


def test_get_all_assessment_requires_admin(owner_with_dog):
    client, headers, _dog_id = owner_with_dog
    resp = client.get("/api/v1/assessment/all", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "2002"
