"""Recomputes every ML evaluation metric in the project live, straight from the code and data.

Usage: python src/show_metrics.py [--quick]
  --quick  skip the slow parts (GRM refit stability, Darwin's Ark band check, German benchmark)

Read-only: the evaluation functions are imported and called; no __main__ block that writes
a results/params/model file is ever run.
"""
from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import silhouette_score
from sklearn.model_selection import KFold, StratifiedKFold, cross_val_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import benchmark_german_dogs  # noqa: E402
import calibrate  # noqa: E402
import cluster  # noqa: E402
import corroborate_cbarq  # noqa: E402
import evaluate_accuracy  # noqa: E402
import fit_params  # noqa: E402
import irt  # noqa: E402
import rules  # noqa: E402
import run_pipeline  # noqa: E402

COLOUR = sys.stdout.isatty()
B, C, N = (("\033[1m", "\033[36m", "\033[0m") if COLOUR else ("",) * 3)


def table(title: str, rows: list[tuple[str, str]]) -> None:
    w = max(len(r[0]) for r in rows) + 2
    print(f"\n{C}{B}{title}{N}")
    print(f"{'Metric':<{w}}Value")
    print("-" * (w + 52))
    for metric, value in rows:
        print(f"{metric:<{w}}{value}")


def quiet(fn, *args, **kwargs):
    """Call a function whose own progress prints we do not want in the demo output."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def dist(series: pd.Series) -> str:
    return ", ".join(f"{k} {v}" for k, v in series.value_counts().items())


def main() -> int:
    quick = "--quick" in sys.argv[1:]
    res = ROOT / "results"
    responses = pd.read_csv(ROOT / "data" / "raw" / "responses.csv")
    items, a, b = irt.load_params(ROOT / "data" / "reference" / "params_own.csv")

    # ---- IRT / graded response model -------------------------------------------------
    est = irt.grm_eap(responses[items], items, a, b)
    disc = pd.Series(a, index=items)
    archive = pd.read_csv(res / "scored_responses.csv").set_index("ID")["theta_irt"]
    live = pd.Series(est.theta.to_numpy(), index=responses["ID"])
    r = float(np.corrcoef(live, archive.loc[live.index])[0, 1])
    max_diff = float((live - archive.loc[live.index]).abs().max())

    rows = [
        ("Cohort size", str(len(responses))),
        ("Items calibrated", str(len(items))),
        ("Marginal reliability (observed variance denominator)",
         f"{irt.marginal_reliability(est.theta_se, est.theta, denominator='observed'):.4f}"),
        ("Marginal reliability (prior variance denominator)",
         f"{irt.marginal_reliability(est.theta_se, denominator='prior'):.4f}"),
        ("Mean SE (theta)", f"{est.theta_se.mean():.4f}"),
        ("Max SE (theta)", f"{est.theta_se.max():.4f}"),
        ("Theta range", f"{est.theta.min():+.3f} to {est.theta.max():+.3f}"),
        ("Lowest discrimination", f"{disc.idxmin()}, {disc.min():.4f}"),
        ("Highest discrimination", f"{disc.idxmax()}, {disc.max():.4f}"),
        ("GRM archive reproduction fidelity", f"r = {r:.4f}, max diff = {max_diff:.6f}"),
    ]
    if not quick:
        _, best_ll, ll_spread, a_spread = quiet(fit_params.check_stability, responses, n_restarts=5, seed=0)
        rows += [
            ("EM refit: starts (1 deterministic + 5 random)", "6"),
            ("EM refit: best log-likelihood", f"{best_ll:.3f}"),
            ("EM refit: log-likelihood spread across starts", f"{ll_spread:.4f}"),
            ("EM refit: max discrimination spread across starts", f"{max(a_spread.values()):.4f}"),
        ]
    table("IRT severity measurement model (graded response model)", rows)

    # ---- K-means phenotypes ----------------------------------------------------------
    X = StandardScaler().fit_transform(responses[irt.ITEMS_ALL].to_numpy(float))
    sil = {k: silhouette_score(X, KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(X))
           for k in range(2, 7)}
    labels, profiles = quiet(cluster.fit_clusters, responses)
    mapping = cluster.label_clusters_by_profile(profiles)
    phenotype = labels.map(mapping)
    aris = quiet(cluster.check_stability, responses)
    table("Phenotype assignment (K-means clustering)", [
        ("Cohort size", str(len(responses))),
        ("Number of clusters (k)", str(labels.nunique())),
        ("Silhouette score by k (2..6)", ", ".join(f"k={k}: {v:.4f}" for k, v in sil.items())),
        ("Silhouette score at k=3", f"{sil[3]:.4f}"),
        ("Phenotype sizes", dist(phenotype)),
        ("Cluster stability (ARI, 10 re-seedings vs first seed) - min", f"{min(aris):.4f}"),
        ("Cluster stability (ARI, 10 re-seedings vs first seed) - mean", f"{np.mean(aris):.4f}"),
        ("Cluster stability (ARI) - comparisons", str(len(aris))),
    ])

    # ---- Random Forest ---------------------------------------------------------------
    rf = quiet(evaluate_accuracy.evaluate_random_forest, responses)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    model = RandomForestClassifier(n_estimators=200, random_state=42)
    fold_acc = cross_val_score(model, responses[irt.ITEMS_ALL], phenotype, cv=cv)
    model.fit(responses[irt.ITEMS_ALL], phenotype)
    imp = pd.Series(model.feature_importances_, index=irt.ITEMS_ALL).sort_values(ascending=False)
    table("Phenotype confidence classifier (Random Forest, stratified 5-fold CV)", [
        ("Cohort size", str(rf["n"])),
        ("Accuracy (out-of-fold predictions)", f"{rf['accuracy']:.4f}"),
        ("Accuracy (mean of 5 folds, as train_rf.py)", f"{fold_acc.mean():.4f}"),
        ("Accuracy per fold", ", ".join(f"{s:.3f}" for s in fold_acc)),
        ("Macro F1", f"{rf['macro_f1']:.4f}"),
        ("Macro ROC-AUC (one-vs-rest)", f"{rf['macro_roc_auc_ovr']:.4f}"),
        ("Top 5 feature importances", ", ".join(f"{k} {v:.3f}" for k, v in imp.head(5).items())),
    ])
    rows = []
    for cls, m in rf["per_class"].items():
        rows.append((cls, f"precision {m['precision']:.4f}   recall {m['recall']:.4f}   "
                          f"F1 {m['f1_score']:.4f}   support {m['support']}"))
    table("Random Forest per-phenotype results", rows)

    labs = rf["confusion_matrix"]["labels"]
    print(f"\n{C}{B}Confusion matrix (rows = true, columns = predicted){N}")
    print(f"{'':<18}" + "".join(f"{l:>16}" for l in labs))
    for lab, row in zip(labs, rf["confusion_matrix"]["matrix"]):
        print(f"{lab:<18}" + "".join(f"{v:>16}" for v in row))

    # ---- Full scoring pipeline over the cohort (no output file written) --------------
    pm = run_pipeline.load_scoring_model()
    scored = pd.read_csv(res / "scored_responses.csv")
    out = []
    for _, row in scored.iterrows():
        o = run_pipeline.score_case({q: int(row[q]) for q in irt.ITEMS_ALL}, pm, verbose=False)
        out.append(dict(theta=o["theta"], se=o["theta_se"], severity=o["severity"], phenotype=o["phenotype"],
                        conf=o["rf_confidence"], f_irt=o["flag_irt"], f_rf=o["flag_rf"],
                        rule=o["recommendation"]["rule_id"], withheld=o["recommendation"]["withheld"],
                        urgency=o["recommendation"]["urgency"]))
    df = pd.DataFrame(out)
    nw = int(df.withheld.sum())
    table(f"End-to-end pipeline over the cohort (scoring model: {pm[0]}, {len(pm[1])} items)", [
        ("Dogs scored", str(len(df))),
        ("Severity distribution (Low/Moderate/High)", dist(df.severity)),
        ("Phenotype distribution", dist(df.phenotype)),
        ("Urgency distribution", dist(df.urgency)),
        ("Mean / max SE (theta)", f"{df.se.mean():.4f} / {df.se.max():.4f}"),
        (f"Measurement-imprecision flag (SE > {rules.SE_THRESHOLD})", f"{int(df.f_irt.sum())} of {len(df)} dogs"),
        (f"Phenotype-uncertainty flag (RF confidence < {rules.CONF_THRESHOLD})",
         f"{int(df.f_rf.sum())} of {len(df)} dogs"),
        ("Mean RF confidence", f"{df.conf.mean():.4f}"),
        ("Recommendation withheld", f"{nw} of {len(df)} dogs ({100 * nw / len(df):.1f}%)"),
        ("Distinct rules fired", str(df.rule.nunique())),
    ])

    # ---- Longitudinal change detection ------------------------------------------------
    mdc_mean = rules.detectable_change(0.0, 0.0, float(df.se.mean()), float(df.se.mean()))["mdc95"]
    mdc_max = rules.detectable_change(0.0, 0.0, float(df.se.max()), float(df.se.max()))["mdc95"]
    table("Longitudinal change detection (minimum detectable change, MDC95)", [
        ("MDC95 at the mean cohort SE", f"{mdc_mean:.4f} theta units"),
        ("MDC95 at the max cohort SE", f"{mdc_max:.4f} theta units"),
        ("Severity band cut-points (75th / 90th percentile theta)",
         ", ".join(f"{int(p)}th {t:+.3f}" for p, t in pm[4].set_index('percentile').loc[[75, 90], 'theta_cutpoint'].items())),
    ])

    # ---- Darwin's Ark calibration check ----------------------------------------------
    if not quick:
        mp = calibrate.load_mapping()
        ark = calibrate.load_darwins_ark_matrix(mp)
        c_items, ca, cb = irt.load_params(ROOT / "data" / "reference" / "params_calibrated.csv")
        norms = pd.read_csv(ROOT / "data" / "reference" / "population_norms_theta.csv").set_index("percentile")
        c75, c90 = float(norms.loc[75, "theta_cutpoint"]), float(norms.loc[90, "theta_cutpoint"])
        ours = irt.grm_eap(responses[c_items], c_items, ca, cb)
        bands = ours.theta.apply(lambda t: calibrate.assign_band(t, c75, c90))
        ark_est = irt.grm_eap(ark[c_items], c_items, ca, cb)
        table("Darwin's Ark calibration (reference population for severity cut-points)", [
            ("Darwin's Ark complete cases", str(len(ark))),
            ("Calibrated items", str(len(c_items))),
            ("Reference 75th / 90th percentile theta cut-points", f"{c75:+.4f} / {c90:+.4f}"),
            ("Reference population theta mean / SD", f"{ark_est.theta.mean():+.3f} / {ark_est.theta.std():.3f}"),
            ("Our cohort banded with those cut-points", dist(bands)),
        ])

    # ---- C-BARQ corroboration --------------------------------------------------------
    cb = pd.read_csv(corroborate_cbarq.DATA_PATH, sep="\t")
    rows = []
    for pa, pb in corroborate_cbarq.PAIRS:
        sub = cb[[pa, pb]].dropna()
        tag = "  (primary)" if (pa, pb) == corroborate_cbarq.PRIMARY_PAIR else ""
        rows.append((f"{pa} vs {pb}{tag}", f"r = {sub[pa].corr(sub[pb]):.4f}, n = {len(sub)}"))
    table("C-BARQ corroboration (independent subscale correlations)", rows)

    # ---- German DOGS representativeness benchmark ------------------------------------
    if not quick:
        Xg, yg = benchmark_german_dogs.load_complete_cases()
        reg = RandomForestRegressor(n_estimators=200, random_state=42)
        scores = cross_val_score(reg, Xg, yg, cv=KFold(n_splits=5, shuffle=True, random_state=42), scoring="r2")
        reg.fit(Xg, yg)
        gi = pd.Series(reg.feature_importances_, index=Xg.columns).sort_values(ascending=False)
        table("German DOGS benchmark (demographics vs anxiety proxy, RF regressor, 5-fold CV)", [
            ("Complete cases", str(len(Xg))),
            ("Predictors (after one-hot encoding)", str(Xg.shape[1])),
            ("CV R-squared (mean)", f"{scores.mean():.4f}"),
            ("CV R-squared per fold", ", ".join(f"{s:.3f}" for s in scores)),
            ("Top 5 feature importances", ", ".join(f"{k} {v:.3f}" for k, v in gi.head(5).items())),
        ])

    print(f"\n{B}Done. Every value above was computed just now from the code and data.{N}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
