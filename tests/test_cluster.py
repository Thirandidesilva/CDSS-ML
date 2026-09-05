import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import cluster  # noqa: E402
import rules    # noqa: E402

RESPONSES = pd.read_csv(ROOT / "data" / "raw" / "responses.csv")


def test_phenotype_labels_follow_profile_not_index():
    for seed in (42, 7):
        _, profiles = cluster.fit_clusters(RESPONSES, random_state=seed)
        mapping = cluster.label_clusters_by_profile(profiles)
        assert set(mapping.values()) == set(rules.PHENOTYPE_LABELS)


def test_check_stability_ari():
    aris = cluster.check_stability(RESPONSES, n_seeds=5, base_seed=42)
    assert min(aris) > 0.8
