import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import rules  # noqa: E402


def _evaluate(band, phenotype, **kw):
    defaults = dict(flag_irt=False, flag_rf=False, theta_se=0.3, rf_confidence=0.9)
    defaults.update(kw)
    return rules.evaluate(band, phenotype, **defaults)


def test_all_nine_cells_have_evidence():
    seen_ids = set()
    for band, phenotype in itertools.product(rules.SEVERITY_BANDS, rules.PHENOTYPE_LABELS):
        rec = _evaluate(band, phenotype)
        assert rec.evidence
        assert rec.rule_id not in seen_ids
        seen_ids.add(rec.rule_id)
    assert len(seen_ids) == 9


def test_flag_irt_withholds_regardless_of_phenotype_confidence():
    rec = _evaluate("High", "Generalised", flag_irt=True, flag_rf=False, theta_se=0.8)
    assert rec.withheld
    assert rec.withheld_reason is not None


def test_flag_rf_downgrades_not_withholds():
    rec = _evaluate("Moderate", "Noise-specific", flag_irt=False, flag_rf=True, rf_confidence=0.4)
    assert not rec.withheld
    assert "noise" not in rec.action.lower()
    assert any("confidence" in c.lower() for c in rec.caveats)


def test_both_flags_withholds_via_irt():
    rec = _evaluate("High", "Noise-specific", flag_irt=True, flag_rf=True,
                     theta_se=0.9, rf_confidence=0.2)
    assert rec.withheld


def test_no_flags_includes_phenotype_content():
    rec = _evaluate("Moderate", "Noise-specific", flag_irt=False, flag_rf=False)
    assert "noise" in rec.action.lower()


def test_invalid_band_raises():
    try:
        _evaluate("Extreme", "Mild")
    except ValueError:
        return
    raise AssertionError("expected ValueError for invalid band")


def test_invalid_phenotype_raises():
    try:
        _evaluate("Low", "Aggressive")
    except ValueError:
        return
    raise AssertionError("expected ValueError for invalid phenotype")


def test_to_dict_is_json_serialisable():
    rec = _evaluate("High", "Generalised")
    json.dumps(rec.to_dict())


def test_screening_caveat_always_present():
    for flags in [dict(flag_irt=False, flag_rf=False), dict(flag_irt=True, flag_rf=False),
                  dict(flag_irt=False, flag_rf=True)]:
        rec = _evaluate("High", "Generalised", **flags)
        assert rules.SCREENING_CAVEAT in rec.caveats


def test_aversive_technique_caveat_present_unless_withheld():
    shown = _evaluate("Moderate", "Mild", flag_irt=False, flag_rf=False)
    assert rules.UNIVERSAL_CAVEAT in shown.caveats
    withheld = _evaluate("Moderate", "Mild", flag_irt=True, flag_rf=False, theta_se=0.9)
    assert rules.UNIVERSAL_CAVEAT not in withheld.caveats


def test_single_band_change_is_not_detectable():
    # one band is 0.769 theta wide; typical SE ~0.4 each
    result = rules.detectable_change(0.0, 0.769, 0.4, 0.4)
    assert not result["detectable"]


def test_larger_change_is_detectable():
    result = rules.detectable_change(0.0, 2.0, 0.4, 0.4)
    assert result["detectable"]
