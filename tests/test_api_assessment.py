import pytest

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

    listed = client.post("/api/v1/assessment/list-by-dog", json={"dog_id": dog_id}, headers=headers)
    assert listed.status_code == 200
    assert any(a["assessment_id"] == assessment_id for a in listed.json()["response"])

    result = client.post("/api/v1/assessment/get", json={"assessment_id": assessment_id}, headers=headers)
    assert result.status_code == 200
    assert result.json()["response"][0]["assessment_id"] == assessment_id


def test_get_nonexistent_assessment_returns_404(registered_owner):
    client, headers = registered_owner
    resp = client.post(
        "/api/v1/assessment/get",
        json={"assessment_id": "00000000-0000-0000-0000-000000000000"},
        headers=headers,
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "3001"


def test_delete_assessment_then_disappears_from_list(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    submitted = client.post(
        "/api/v1/assessment/submit", json=dict(NON_WITHHELD, dog_id=dog_id), headers=headers
    )
    assessment_id = submitted.json()["response"][0]["assessment_id"]

    deleted = client.post("/api/v1/assessment/delete", json={"assessment_id": assessment_id}, headers=headers)
    assert deleted.status_code == 200

    listed = client.post("/api/v1/assessment/list-by-dog", json={"dog_id": dog_id}, headers=headers)
    assert all(a["assessment_id"] != assessment_id for a in listed.json()["response"])


def test_get_all_assessment_requires_admin(owner_with_dog):
    client, headers, _dog_id = owner_with_dog
    resp = client.get("/api/v1/assessment/all", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "2002"


def test_get_all_assessments_groups_by_dog_id(owner_with_dog, test_db_engine):
    client, headers, dog_id = owner_with_dog
    client.post("/api/v1/assessment/submit", json=dict(NON_WITHHELD, dog_id=dog_id), headers=headers)
    client.post("/api/v1/assessment/submit", json=dict(NON_WITHHELD, dog_id=dog_id), headers=headers)

    # No self-service way to become admin — elevate directly via the DB, same technique
    # test_otp_expired_is_rejected already uses for direct row manipulation in tests.
    from sqlalchemy.orm import Session

    from api.enums import UserRole
    from api.models import User

    with Session(test_db_engine) as db:
        owner = db.query(User).filter(User.user_name == "owner1").one()
        owner.role = UserRole.ADMIN
        db.commit()

    resp = client.get("/api/v1/assessment/all", headers=headers)
    assert resp.status_code == 200
    groups = resp.json()["response"]
    assert len(groups) == 1  # one dog only
    group = groups[0]
    assert group["dog_id"] == dog_id
    assert "dog_id" not in group["assessments"][0]  # hoisted out, not repeated per item
    assert len(group["assessments"]) == 2
    assert {a["session_number"] for a in group["assessments"]} == {1, 2}


def test_stats_on_dog_with_no_assessments(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    resp = client.post("/api/v1/assessment/stats", json={"dog_id": dog_id}, headers=headers)
    assert resp.status_code == 200
    stats = resp.json()["response"][0]
    assert stats["assessment_count"] == 0
    assert stats["theta"] is None
    assert stats["severity_band_counts"] == {}


def test_stats_on_dog_with_assessments(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    client.post("/api/v1/assessment/submit", json=dict(NON_WITHHELD, dog_id=dog_id), headers=headers)
    client.post("/api/v1/assessment/submit", json=dict(NON_WITHHELD, dog_id=dog_id), headers=headers)

    resp = client.post("/api/v1/assessment/stats", json={"dog_id": dog_id}, headers=headers)
    assert resp.status_code == 200
    stats = resp.json()["response"][0]
    assert stats["assessment_count"] == 2
    # isolated_pipeline_env only ships params_own.csv, so both submissions share the
    # same score_model_name — theta's n should equal the full count, not a subset.
    assert stats["theta"]["n"] == 2
    assert isinstance(stats["theta"]["average"], float)
    assert isinstance(stats["theta_se"]["average"], float)
    assert isinstance(stats["rf_confidence"]["average"], float)
    assert set(stats["subscales"].keys()) == {
        "separation", "noise", "fear", "aggression", "compulsive", "physiological",
    }
    assert sum(stats["severity_band_counts"].values()) == 2


def test_stats_on_someone_elses_dog_returns_403(api_client, owner_with_dog):
    _client, _headers, dog_id = owner_with_dog
    api_client.post("/api/v1/auth/register", json={
        "user_name": "stats_intruder", "email": "stats_intruder@example.com", "password": "hunter2pass",
    })
    login = api_client.post("/api/v1/auth/login", json={
        "user_name_or_email": "stats_intruder", "password": "hunter2pass",
    })
    other_headers = {"Authorization": f"Bearer {login.json()['response'][0]['access_token']}"}

    resp = api_client.post("/api/v1/assessment/stats", json={"dog_id": dog_id}, headers=other_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "2002"


def test_weekly_summary_with_no_activity(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    resp = client.post("/api/v1/assessment/weekly-summary", json={}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()["response"][0]
    assert len(body["dogs"]) == 1
    dog_summary = body["dogs"][0]
    assert dog_summary["dog_id"] == dog_id
    assert len(dog_summary["days"]) == 7
    assert all(day["assessed"] is False for day in dog_summary["days"])


def test_weekly_summary_after_submitting_today(owner_with_dog):
    from datetime import datetime, timezone

    client, headers, dog_id = owner_with_dog
    client.post("/api/v1/assessment/submit", json=dict(NON_WITHHELD, dog_id=dog_id), headers=headers)

    resp = client.post("/api/v1/assessment/weekly-summary", json={}, headers=headers)
    assert resp.status_code == 200
    dog_summary = resp.json()["response"][0]["dogs"][0]

    today = datetime.now(timezone.utc).date()
    todays_entry = next(d for d in dog_summary["days"] if d["date"] == today.isoformat())
    assert todays_entry["assessed"] is True
    assert todays_entry["assessment_count"] == 1
    other_days = [d for d in dog_summary["days"] if d["date"] != today.isoformat()]
    assert all(d["assessed"] is False for d in other_days)


def test_weekly_summary_for_someone_else_returns_403(api_client, owner_with_dog):
    _client, _headers, _dog_id = owner_with_dog
    owner_user_id = _client.get("/api/v1/users/me", headers=_headers).json()["response"][0]["user_id"]

    api_client.post("/api/v1/auth/register", json={
        "user_name": "weekly_intruder", "email": "weekly_intruder@example.com", "password": "hunter2pass",
    })
    login = api_client.post("/api/v1/auth/login", json={
        "user_name_or_email": "weekly_intruder", "password": "hunter2pass",
    })
    other_headers = {"Authorization": f"Bearer {login.json()['response'][0]['access_token']}"}

    resp = api_client.post(
        "/api/v1/assessment/weekly-summary", json={"user_id": owner_user_id}, headers=other_headers
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "2002"


# ---------------------------------------------------------------- anxiety_index / created_at

def _band_for_index(index):
    # The documented contract: Low < 1/3 <= Moderate < 2/3 <= High.
    return "Low" if index < 1 / 3 else ("Moderate" if index < 2 / 3 else "High")


def test_anxiety_index_pins_the_band_cut_points():
    from api.services.assessment_stats import anxiety_index

    cut_75, cut_90, cut_99 = 0.5855, 1.101, 2.0202
    assert anxiety_index(cut_75, cut_75, cut_90, cut_99) == pytest.approx(1 / 3, abs=1e-3)
    assert anxiety_index(cut_90, cut_75, cut_90, cut_99) == pytest.approx(2 / 3, abs=1e-3)
    assert anxiety_index(cut_99, cut_75, cut_90, cut_99) == 1.0


def test_anxiety_index_is_clamped_to_zero_and_one():
    from api.services.assessment_stats import anxiety_index

    assert anxiety_index(-50.0, 0.5855, 1.101, 2.0202) == 0.0
    assert anxiety_index(50.0, 0.5855, 1.101, 2.0202) == 1.0


def test_anxiety_index_never_decreases_as_theta_rises():
    from api.services.assessment_stats import anxiety_index

    thetas = [x / 20 for x in range(-80, 120)]
    values = [anxiety_index(t, 0.5855, 1.101, 2.0202) for t in thetas]
    assert values == sorted(values)


def test_anxiety_index_always_agrees_with_the_severity_band():
    # The whole point: the number can never contradict the Low/Moderate/High label.
    from api.services.assessment_stats import anxiety_index
    from calibrate import assign_band

    for cut_99 in (2.0202, None):
        for i in range(-300, 400):
            theta = i / 100
            band = assign_band(theta, 0.5855, 1.101)
            assert _band_for_index(anxiety_index(theta, 0.5855, 1.101, cut_99)) == band, (theta, cut_99)


def test_anxiety_index_without_a_99th_percentile_still_reaches_one():
    from api.services.assessment_stats import anxiety_index

    assert anxiety_index(0.0, 0.5855, 1.101) < 1 / 3
    assert anxiety_index(5.0, 0.5855, 1.101) == 1.0


def test_band_cut_points_read_the_norms_table():
    import pandas as pd

    from api.services.assessment_stats import band_cut_points

    full = pd.DataFrame({"percentile": [50, 75, 90, 99], "theta_cutpoint": [0.0, 0.5, 1.0, 2.0]})
    assert band_cut_points(full) == (0.5, 1.0, 2.0)
    no_99 = pd.DataFrame({"percentile": [50, 75, 90], "theta_cutpoint": [0.0, 0.5, 1.0]})
    assert band_cut_points(no_99) == (0.5, 1.0, None)


def test_submit_returns_an_index_that_matches_the_band_and_a_timestamp(owner_with_dog):
    from datetime import datetime

    client, headers, dog_id = owner_with_dog
    resp = client.post(
        "/api/v1/assessment/submit", json=dict(NON_WITHHELD, dog_id=dog_id), headers=headers
    )
    result = resp.json()["response"][0]

    assert 0.0 <= result["anxiety_index"] <= 1.0
    assert _band_for_index(result["anxiety_index"]) == result["severity_band"]
    # An ISO timestamp the app can parse for "completed on", explicitly UTC so a phone in
    # another timezone shows the right local time.
    assert result["created_at"].endswith("Z")
    # (Python 3.9's fromisoformat predates the "Z" suffix; Dart's DateTime.parse accepts it.)
    created = datetime.fromisoformat(result["created_at"].replace("Z", "+00:00"))
    assert created.utcoffset().total_seconds() == 0


def test_list_and_get_return_the_same_index_and_timestamp_as_submit(owner_with_dog):
    client, headers, dog_id = owner_with_dog
    submitted = client.post(
        "/api/v1/assessment/submit", json=dict(NON_WITHHELD, dog_id=dog_id), headers=headers
    ).json()["response"][0]

    listed = client.post(
        "/api/v1/assessment/list-by-dog", json={"dog_id": dog_id}, headers=headers
    ).json()["response"][0]
    fetched = client.post(
        "/api/v1/assessment/get", json={"assessment_id": submitted["assessment_id"]}, headers=headers
    ).json()["response"][0]

    for other in (listed, fetched):
        assert other["anxiety_index"] == submitted["anxiety_index"]
        assert other["created_at"] == submitted["created_at"]


# ---------------------------------------------------------------- weekly summary time zones

def _pin_time(monkeypatch, client, test_db_engine, headers, dog_id, *, now, assessed_at):
    """Submits one assessment, moves its created_at to `assessed_at` and pins the server's
    clock to `now` (both UTC), so the week can be checked for any offset."""
    from datetime import timezone

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from api.models import Assessment
    from api.routers import assessment as assessment_router

    client.post("/api/v1/assessment/submit", json=dict(NON_WITHHELD, dog_id=dog_id), headers=headers)
    with Session(test_db_engine) as session:
        row = session.scalars(select(Assessment)).one()
        row.created_at = assessed_at.replace(tzinfo=timezone.utc)
        session.commit()
    monkeypatch.setattr(assessment_router, "_now_utc", lambda: now.replace(tzinfo=timezone.utc))


def _weekly(client, headers, **payload):
    resp = client.post("/api/v1/assessment/weekly-summary", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["response"][0]


def test_weekly_summary_counts_an_evening_assessment_on_the_users_day(
    owner_with_dog, test_db_engine, monkeypatch
):
    from datetime import datetime

    client, headers, dog_id = owner_with_dog
    # Saturday 3 Oct 2026, 20:00 UTC is already Sunday 4 Oct, 00:30 in UTC+5:30.
    _pin_time(
        monkeypatch, client, test_db_engine, headers, dog_id,
        now=datetime(2026, 10, 4, 5, 0), assessed_at=datetime(2026, 10, 3, 20, 0),
    )

    def assessed_day(summary):
        days = summary["dogs"][0]["days"]
        return [d["weekday"] for d in days if d["assessed"]]

    assert assessed_day(_weekly(client, headers)) == ["Saturday"]  # UTC, as before
    assert assessed_day(_weekly(client, headers, utc_offset_minutes=330)) == ["Sunday"]


def test_weekly_summary_week_follows_the_users_clock(owner_with_dog, test_db_engine, monkeypatch):
    from datetime import datetime

    client, headers, dog_id = owner_with_dog
    # Monday 5 Oct 03:00 UTC is still Sunday evening (22:00) in UTC-5, so for that user
    # the current week is still 28 Sep to 4 Oct and the Sunday assessment is in it.
    _pin_time(
        monkeypatch, client, test_db_engine, headers, dog_id,
        now=datetime(2026, 10, 5, 3, 0), assessed_at=datetime(2026, 10, 5, 2, 30),
    )

    utc_week = _weekly(client, headers)
    assert utc_week["week_start"] == "2026-10-05"  # a new week, assessment on its Monday

    local_week = _weekly(client, headers, utc_offset_minutes=-300)
    assert local_week["week_start"] == "2026-09-28"
    assert local_week["week_end"] == "2026-10-04"
    sunday = local_week["dogs"][0]["days"][6]
    assert sunday["date"] == "2026-10-04" and sunday["assessed"] is True


def test_weekly_summary_rejects_an_impossible_offset(owner_with_dog):
    client, headers, _dog_id = owner_with_dog
    for offset in (-841, 841):
        resp = client.post(
            "/api/v1/assessment/weekly-summary", json={"utc_offset_minutes": offset}, headers=headers
        )
        assert resp.status_code == 422
