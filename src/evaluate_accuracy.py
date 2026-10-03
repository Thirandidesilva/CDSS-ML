"""Accuracy evaluation, one block per pipeline component (IRT, clustering, Random
Forest) since each is a different kind of model and needs a different kind of metric —
see docs/CHAPTER5_EVALUATION_RESULTS.md for why AUC/F1 apply only to the forest.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_auc_score,
    silhouette_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler, label_binarize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cluster       # noqa: E402
import irt           # noqa: E402
import score_cohort  # noqa: E402

RESULTS = ROOT / "results"


def evaluate_irt(responses: pd.DataFrame) -> dict:
    scored = score_cohort.score_cohort()
    params = pd.read_csv(ROOT / "data" / "reference" / "params_own.csv").set_index("item")

    rel_observed = irt.marginal_reliability(scored.theta_se, scored.theta_irt, denominator="observed")
    rel_prior = irt.marginal_reliability(scored.theta_se, denominator="prior")
    disc_min_item = params.discrimination_a.idxmin()
    disc_max_item = params.discrimination_a.idxmax()

    return {
        "n": len(scored),
        "marginal_reliability_observed": round(rel_observed, 4),
        "marginal_reliability_prior": round(rel_prior, 4),
        "se_theta_mean": round(float(scored.theta_se.mean()), 4),
        "se_theta_max": round(float(scored.theta_se.max()), 4),
        "discrimination_min": {"item": disc_min_item, "value": round(float(params.discrimination_a[disc_min_item]), 4)},
        "discrimination_max": {"item": disc_max_item, "value": round(float(params.discrimination_a[disc_max_item]), 4)},
        "archive_reproduction": "see tests/test_irt.py::test_grm_reproduces_archive (r = 1.0000, max diff < 0.001)",
    }


def evaluate_clustering(responses: pd.DataFrame) -> dict:
    labels, profiles = cluster.fit_clusters(responses)
    X = StandardScaler().fit_transform(responses[irt.ITEMS_ALL].to_numpy(float))
    silhouette = silhouette_score(X, labels)
    aris = cluster.check_stability(responses)

    return {
        "n": len(responses),
        "k": 3,
        "silhouette_score": round(float(silhouette), 4),
        "stability_ari_min": round(float(min(aris)), 4),
        "stability_ari_mean": round(float(np.mean(aris)), 4),
        "n_seeds": len(aris) + 1,  # cluster.check_stability compares 10 seeds against the first, giving 9 ARI values
        "n_comparisons": len(aris),
    }


def evaluate_random_forest(responses: pd.DataFrame) -> dict:
    labels, profiles = cluster.fit_clusters(responses)
    mapping = cluster.label_clusters_by_profile(profiles)
    phenotype = labels.map(mapping)

    X = responses[irt.ITEMS_ALL]
    model = RandomForestClassifier(n_estimators=200, random_state=42)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    y_pred = cross_val_predict(model, X, phenotype, cv=cv, method="predict")
    y_proba = cross_val_predict(model, X, phenotype, cv=cv, method="predict_proba")

    class_order = sorted(phenotype.unique())
    y_true_bin = label_binarize(phenotype, classes=class_order)
    macro_auc = roc_auc_score(y_true_bin, y_proba, multi_class="ovr", average="macro")

    report = classification_report(phenotype, y_pred, output_dict=True)
    cm = confusion_matrix(phenotype, y_pred, labels=class_order)

    return {
        "n": len(responses),
        "features": list(irt.ITEMS_ALL),
        "cv_scheme": "StratifiedKFold(n_splits=5, shuffle=True, random_state=42) — same scheme as train_rf.py",
        "accuracy": round(float(report["accuracy"]), 4),
        "macro_f1": round(float(report["macro avg"]["f1-score"]), 4),
        "macro_roc_auc_ovr": round(float(macro_auc), 4),
        "per_class": {
            cls: {
                "precision": round(report[cls]["precision"], 4),
                "recall": round(report[cls]["recall"], 4),
                "f1_score": round(report[cls]["f1-score"], 4),
                "support": int(report[cls]["support"]),
            }
            for cls in class_order
        },
        "confusion_matrix": {"labels": class_order, "matrix": cm.tolist()},
        "sklearn_version": sklearn.__version__,
    }


def main():
    responses = pd.read_csv(ROOT / "data" / "raw" / "responses.csv")

    result = {
        "irt_measurement_model": evaluate_irt(responses),
        "phenotype_clustering": evaluate_clustering(responses),
        "random_forest_classifier": evaluate_random_forest(responses),
    }

    RESULTS.mkdir(exist_ok=True)
    dest = RESULTS / "accuracy_evaluation.json"
    with open(dest, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nwrote {dest}\n")

    irt_block = result["irt_measurement_model"]
    print("IRT / GRM (severity measurement model)")
    print(f"  marginal reliability: observed={irt_block['marginal_reliability_observed']}  "
          f"prior={irt_block['marginal_reliability_prior']}")
    print(f"  SE(theta): mean={irt_block['se_theta_mean']}  max={irt_block['se_theta_max']}")
    print(f"  discrimination: min={irt_block['discrimination_min']}  max={irt_block['discrimination_max']}")

    clus_block = result["phenotype_clustering"]
    print("\nClustering (phenotype assignment, k-means)")
    print(f"  silhouette (k=3): {clus_block['silhouette_score']}")
    print(f"  stability ARI: min={clus_block['stability_ari_min']}  mean={clus_block['stability_ari_mean']}")

    rf_block = result["random_forest_classifier"]
    print("\nRandom Forest (phenotype confidence classifier)")
    print(f"  accuracy={rf_block['accuracy']}  macro_f1={rf_block['macro_f1']}  "
          f"macro_roc_auc_ovr={rf_block['macro_roc_auc_ovr']}")
    print(f"  confusion matrix {rf_block['confusion_matrix']['labels']}:")
    for row in rf_block['confusion_matrix']['matrix']:
        print(f"    {row}")


if __name__ == "__main__":
    main()
