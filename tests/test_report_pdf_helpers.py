import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from api.services.report_chart import render_severity_chart_svg  # noqa: E402
from api.services.report_sources import detect_sources  # noqa: E402


def test_chart_single_point_has_no_polyline():
    svg = render_severity_chart_svg([("12 Sep 2026", 1.15)], cut_75=0.5, cut_90=1.0)
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "<polyline" not in svg
    assert svg.count("<circle") == 1


def test_chart_multi_point_has_one_polyline_and_bands():
    svg = render_severity_chart_svg(
        [("12 Jun 2026", 0.62), ("07 Aug 2026", 0.95), ("12 Sep 2026", 1.15)],
        cut_75=0.5, cut_90=1.0,
    )
    assert svg.count("<polyline") == 1
    assert svg.count("<circle") == 3
    assert svg.count("<rect") == 3  # Low/Moderate/High bands


def test_chart_handles_negative_theta_without_clamping_to_zero():
    # theta_calibrated can legitimately be negative; y_min must not be hardcoded to 0.
    svg = render_severity_chart_svg([("12 Sep 2026", -0.376)], cut_75=0.5, cut_90=1.0)
    assert svg.startswith("<svg")


def test_detect_sources_neither():
    assert detect_sources("no citations here") == []


def test_detect_sources_msd_only():
    assert detect_sources("cites MSD Veterinary Manual") == ["MSD Veterinary Manual"]


def test_detect_sources_aaha_only():
    assert detect_sources("cites AAHA guidelines") == ["AAHA Behaviour Management Guidelines"]


def test_detect_sources_both_in_fixed_order():
    assert detect_sources("cites AAHA", "and also MSD") == [
        "MSD Veterinary Manual", "AAHA Behaviour Management Guidelines",
    ]
