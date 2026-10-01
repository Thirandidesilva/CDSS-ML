import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import irt          # noqa: E402
import longitudinal  # noqa: E402

BASE_ANSWERS = {q: 1 for q in irt.ITEMS_ALL}


def test_track_sentinel_items_reports_no_change():
    changes = longitudinal.track_sentinel_items(BASE_ANSWERS, BASE_ANSWERS)
    assert set(changes.keys()) == set(longitudinal.SENTINEL_ITEMS)
    assert all(c["delta"] == 0 and not c["changed"] for c in changes.values())


def test_track_sentinel_items_reports_a_real_change():
    after = dict(BASE_ANSWERS, Q8=4)
    changes = longitudinal.track_sentinel_items(BASE_ANSWERS, after)
    assert changes["Q8"] == {"before": 1, "after": 4, "delta": 3, "changed": True}
    assert changes["Q5"]["changed"] is False


def test_track_theta_change_no_change_is_not_detectable():
    result = longitudinal.track_theta_change(0.0, 0.0, 0.4, 0.4)
    assert result["delta"] == 0.0
    assert result["detectable"] is False


def test_track_theta_change_single_band_move_is_not_detectable():
    # one band is 0.769 theta wide; a single-band move must stay below MDC95 (1.508)
    result = longitudinal.track_theta_change(0.0, 0.769, 0.4, 0.4)
    assert result["detectable"] is False


def test_track_theta_change_large_move_is_detectable():
    result = longitudinal.track_theta_change(-1.0, 1.0, 0.3, 0.3)
    assert result["detectable"] is True
