import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from api.services.report_chart import layout_severity_chart  # noqa: E402
from api.services.report_sources import detect_sources  # noqa: E402


def test_chart_single_point_is_not_connected():
    lay = layout_severity_chart([("12 Sep 2026", 1.15)], cut_75=0.5, cut_90=1.0)
    assert not lay.connected
    assert len(lay.markers) == 1


def test_chart_multi_point_is_connected_with_three_bands():
    lay = layout_severity_chart(
        [("12 Jun 2026", 0.62), ("07 Aug 2026", 0.95), ("12 Sep 2026", 1.15)],
        cut_75=0.5, cut_90=1.0,
    )
    assert lay.connected
    assert len(lay.markers) == 3
    assert [b.label for b in lay.bands] == ["Low", "Moderate", "High"]
    xs = [m.x for m in lay.markers]
    assert xs == sorted(xs)  # chronological, left to right


def test_chart_higher_theta_is_drawn_higher():
    lay = layout_severity_chart([("a", 0.2), ("b", 1.1)], cut_75=0.5, cut_90=1.0)
    assert lay.markers[1].y < lay.markers[0].y  # y grows downwards


def test_chart_handles_negative_theta_without_clamping_to_zero():
    # theta_calibrated can legitimately be negative; y_min must not be hardcoded to 0.
    lay = layout_severity_chart([("12 Sep 2026", -0.376)], cut_75=0.5, cut_90=1.0)
    assert min(v for _, v in lay.gridlines) < 0


def test_chart_needs_at_least_one_point():
    import pytest

    with pytest.raises(ValueError):
        layout_severity_chart([], cut_75=0.5, cut_90=1.0)


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


# ---------------------------------------------------------------- ReportLab renderer

def _context(**overrides):
    import run_pipeline

    ctx = {
        "report_display_id": "PWS-2026-0421", "generated_at_display": "03 Oct 2026, 10:15",
        "assessment_date_display": "03 Oct 2026", "dog_name": "Bruno & Co",
        "dog_breed_display": "Labrador Retriever", "dog_age_display": "4 years",
        "dog_gender_display": "Male", "owner_display_name": "T. De Silva",
        "assessments_on_record": 3, "severity_band": "High", "phenotype": "Separation-related",
        "rf_confidence_pct": 72, "theta": 1.15, "theta_se": 0.21,
        "theta_ci_low": 0.74, "theta_ci_high": 1.56,
        "subscale_rows": [
            {"label": "Fear", "value": 2.0, "pct": 50.0, "is_highlight": False},
            {"label": "Separation-related", "value": 3.2, "pct": 80.0, "is_highlight": True},
        ],
        "recommendation_header": "High severity • Separation-related presentation",
        "recommendation_rationale": "Scores concentrate on separation items.",
        "recommendation_bullets": ["Book a consultation.", "Begin graded absence training."],
        "recommendation_caveats": ["Owner-reported data only."],
        "recommendation_sources": ["MSD Veterinary Manual"],
        "alert_banner": {"lead": "Veterinary review recommended.", "body": "High severity."},
        "chart": {"points": [("12 Jun 2026", 0.62), ("03 Oct 2026", 1.15)], "cut_75": 0.5, "cut_90": 1.0},
        "questionnaire_rows": [
            {"item_code": c, "text": run_pipeline.ITEM_TEXT[c], "subscale_label": "Fear",
             "value": 3, "likert_label": "Often"}
            for c in sorted(run_pipeline.ITEM_TEXT, key=lambda c: int(c[1:]))
        ],
    }
    ctx.update(overrides)
    return ctx


def _pages(pdf: bytes) -> int:
    import re

    return len(re.findall(rb"/Type /Page\b", pdf))


def _uncompressed(monkeypatch):
    from reportlab import rl_config

    monkeypatch.setattr(rl_config, "pageCompression", 0)


def test_renderer_produces_a_two_page_pdf():
    from api.services.report_pdf import PdfRenderer

    pdf = PdfRenderer().render_pdf(_context())
    assert pdf.startswith(b"%PDF-")
    assert _pages(pdf) == 2


def test_renderer_draws_the_report_content(monkeypatch):
    from api.services.report_pdf import PdfRenderer

    _uncompressed(monkeypatch)
    pdf = PdfRenderer().render_pdf(_context())
    for text in (b"Bruno &amp; Co", b"Labrador Retriever", b"PWS-2026-0421", b"Veterinary review recommended."):
        assert text.replace(b"&amp;", b"&") in pdf, text


def test_renderer_omits_the_banner_when_there_is_none(monkeypatch):
    from api.services.report_pdf import PdfRenderer

    _uncompressed(monkeypatch)
    pdf = PdfRenderer().render_pdf(_context(alert_banner=None))
    assert b"Veterinary review recommended." not in pdf


def test_renderer_survives_text_outside_latin_1_and_a_single_point():
    from api.services.report_pdf import PdfRenderer

    pdf = PdfRenderer().render_pdf(_context(
        dog_name="සුබි Rex",
        chart={"points": [("03 Oct 2026", -0.376)], "cut_75": 0.5, "cut_90": 1.0},
    ))
    assert pdf.startswith(b"%PDF-")


def test_renderer_failure_is_a_503_not_a_crash():
    import pytest

    from api.errors import ApiError
    from api.services.report_pdf import PdfRenderer

    with pytest.raises(ApiError) as caught:
        PdfRenderer().render_pdf({"report_display_id": "PWS-1"})  # incomplete context
    assert caught.value.code.value == "4004"
