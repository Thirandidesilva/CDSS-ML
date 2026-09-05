"""Clusters dogs into anxiety phenotypes via k-means and labels clusters by profile shape."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import irt  # noqa: E402

NOISE_ITEMS = ["Q7", "Q8"]


def fit_clusters(items: pd.DataFrame, k_range=range(2, 7), random_state: int = 42,
                  use_k: int = 3):
    """k-means on standardised items; reports silhouette across k_range, but fits
    with use_k (default 3), since rules.py's fixed 9-cell contract requires exactly
    three phenotype labels regardless of which k silhouette alone would prefer.
    """
    X = StandardScaler().fit_transform(items[irt.ITEMS_ALL].to_numpy(float))

    scores = {}
    for k in k_range:
        km = KMeans(n_clusters=k, n_init=10, random_state=random_state).fit(X)
        scores[k] = silhouette_score(X, km.labels_)

    print("silhouette by k:", {k: round(v, 4) for k, v in scores.items()})
    silhouette_best = max(scores, key=scores.get)
    if silhouette_best != use_k:
        print(f"NOTE: silhouette prefers k={silhouette_best} ({scores[silhouette_best]:.4f}) "
              f"over k={use_k} ({scores[use_k]:.4f}); using k={use_k} anyway because "
              f"rules.py's fixed 9-cell matrix requires exactly three phenotypes "
              f"(architecture constraint, not a statistical free choice).")

    km = KMeans(n_clusters=use_k, n_init=10, random_state=random_state).fit(X)
    labels = pd.Series(km.labels_, index=items.index, name="cluster_id")
    profiles = items[irt.ITEMS_ALL].groupby(labels).mean()
    return labels, profiles


def label_clusters_by_profile(profiles: pd.DataFrame) -> dict[int, str]:
    """Map cluster id -> Mild/Noise-specific/Generalised by profile SHAPE, never by index."""
    other_items = [q for q in irt.ITEMS_ALL if q not in NOISE_ITEMS]
    overall = profiles[irt.ITEMS_ALL].mean(axis=1)
    noise = profiles[NOISE_ITEMS].mean(axis=1)
    other = profiles[other_items].mean(axis=1)

    mild_id = int(overall.idxmin())
    remaining = [c for c in profiles.index if c != mild_id]
    contrast = noise.loc[remaining] - other.loc[remaining]
    noise_specific_id = int(contrast.idxmax())
    generalised_id = int([c for c in remaining if c != noise_specific_id][0])

    return {mild_id: "Mild", noise_specific_id: "Noise-specific", generalised_id: "Generalised"}


def check_stability(items: pd.DataFrame, k: int = 3, n_seeds: int = 10, base_seed: int = 42):
    """Re-clusters from different random seeds; agreement (via adjusted Rand index)
    between the resulting dog-level phenotype labels is the evidence cluster identity
    is stable, not an artifact of one k-means initialisation.
    """
    X = StandardScaler().fit_transform(items[irt.ITEMS_ALL].to_numpy(float))

    label_sets = []
    for seed in range(base_seed, base_seed + n_seeds):
        km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(X)
        cluster_ids = pd.Series(km.labels_, index=items.index)
        profiles = items[irt.ITEMS_ALL].groupby(cluster_ids).mean()
        mapping = label_clusters_by_profile(profiles)
        label_sets.append(cluster_ids.map(mapping))

    ref = label_sets[0]
    aris = [adjusted_rand_score(ref, other) for other in label_sets[1:]]
    print(f"stability check: {n_seeds} seeds, ARI vs first seed: "
          f"min {min(aris):.4f}  mean {np.mean(aris):.4f}")
    return aris


if __name__ == "__main__":
    responses = pd.read_csv(ROOT / "data" / "raw" / "responses.csv")
    labels, profiles = fit_clusters(responses)
    mapping = label_clusters_by_profile(profiles)

    phenotype = labels.map(mapping)
    print("\ncluster sizes:", phenotype.value_counts().to_dict())

    out = profiles.rename(index=mapping)
    out.index.name = "phenotype"
    dest = ROOT / "results" / "phenotype_profiles.csv"
    out.to_csv(dest)
    print(f"\nwrote {dest}")
    print(out.to_string())

    print()
    check_stability(responses)
