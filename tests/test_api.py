import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import api  # noqa: E402

NON_WITHHELD = {"Q4": 2, "Q5": 3, "Q6": 2, "Q7": 4, "Q8": 4, "Q9": 1,
                "Q10": 1, "Q11": 2, "Q12": 0, "Q13": 0, "Q14": 4, "Q15": 3}
WITHHELD = {"Q4": 2, "Q5": 2, "Q6": 1, "Q7": 3, "Q8": 1, "Q9": 0,
            "Q10": 4, "Q11": 2, "Q12": 2, "Q13": 1, "Q14": 3, "Q15": 0}


@pytest.fixture(scope="module")
def client():
    return TestClient(api.create_app())


def test_openapi_docs_render(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/assess" in resp.json()["paths"]


def test_normal_case_returns_full_audit(client):
    resp = client.post("/assess", json=NON_WITHHELD)
    assert resp.status_code == 200
    body = resp.json()
    assert body["recommendation"]["withheld"] is False
    for key in ("theta", "theta_se", "severity", "phenotype", "rf_confidence",
                "flag_irt", "flag_rf"):
        assert key in body


def test_withheld_case_returns_200_not_an_error(client):
    resp = client.post("/assess", json=WITHHELD)
    assert resp.status_code == 200
    body = resp.json()
    assert body["recommendation"]["withheld"] is True
    assert body["recommendation"]["withheld_reason"] is not None


def test_missing_item_returns_422_naming_field(client):
    payload = {k: v for k, v in NON_WITHHELD.items() if k != "Q15"}
    resp = client.post("/assess", json=payload)
    assert resp.status_code == 422
    assert any("Q15" in str(e["loc"]) for e in resp.json()["detail"])


def test_out_of_range_value_returns_422_naming_field(client):
    payload = dict(NON_WITHHELD, Q4=7)
    resp = client.post("/assess", json=payload)
    assert resp.status_code == 422
    assert any("Q4" in str(e["loc"]) for e in resp.json()["detail"])


def test_wrong_type_returns_422_naming_field(client):
    payload = dict(NON_WITHHELD, Q4="high")
    resp = client.post("/assess", json=payload)
    assert resp.status_code == 422
    assert any("Q4" in str(e["loc"]) for e in resp.json()["detail"])
