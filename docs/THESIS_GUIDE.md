# Thesis writing guide

A map from this repository to a thesis document: what each chapter should say, which file
proves it, and which numbers are safe to quote. Built by reading `.claude/docs/` (the
project's own working documents — `CLAUDE.md`, `ARCHITECTURE.md`, `PHASES.md`,
`CODE_GUIDE.md`, `FACTS.md`, `PIPELINE.md`), the source tree, and the test suite
(82 passed at time of writing: `python -m pytest tests/ -v`).

This file does not replace those five documents — it re-indexes them for thesis writing.
Where this guide and one of them disagree, the original in `.claude/docs/` wins; update
this file, not the other way round.

---

## 1. What this project is, in one paragraph

A clinical decision support system (CDSS) for canine anxiety screening, built on a
twelve-item owner-report questionnaire (163 dogs, Coventry University with NIBM, final-year
BSc project). The system estimates *how anxious* a dog is with a graded response model
(item response theory), estimates *what kind* of anxiety pattern it shows with k-means
clustering corroborated by a calibrated Random Forest, and combines the two at a
deterministic, evidence-cited rule engine that can withhold a recommendation rather than
guess. The central research finding — and the reason the system is shaped the way it is —
is that the original design was circular: it derived a severity label from the same twelve
items it then tried to predict from those items, so any classifier trained on it was
learning arithmetic, not anxiety. Section 4 below is that finding written out fully; it is
the strongest single narrative thread available for an introduction or motivation chapter.

---

## 2. Suggested chapter map

| Thesis chapter | What it should say | Primary source(s) |
|---|---|---|
| Introduction / motivation | The leakage finding (§4 below); why a CDSS needs to be able to say "I don't know" | `.claude/docs/CLAUDE.md` §"The finding the whole design rests on" |
| Literature / instrument provenance | C-BARQ lineage, MSD/AAHA as the evidence base for recommendations, Darwin's Ark and German DOGS as external datasets | `docs/*.pdf`, §6 below |
| Methodology — measurement model | GRM/IRT design and why not a sum score | `.claude/docs/ARCHITECTURE.md` Stage 2; `src/irt.py`, `src/fit_params.py` |
| Methodology — thresholds | Population-referenced bands vs cohort tertiles | `ARCHITECTURE.md` Stage 3; `src/calibrate.py` |
| Methodology — phenotyping | k-means + nearest centroid + RF confidence | `ARCHITECTURE.md` Stage 4-5; `src/cluster.py`, `src/train_rf.py` |
| Methodology — rule engine | 9-cell deterministic matrix, no default branch, evidence citations | `ARCHITECTURE.md` Stage 6; `src/rules.py` |
| Methodology — longitudinal tracking | MDC95 guard against over-reading noise | `ARCHITECTURE.md` Stage 7; `src/longitudinal.py` |
| System implementation | FastAPI service, DB schema, auth/OTP, PDF report generation | §7 below; `src/api/` |
| Testing / validation strategy | Leakage guard + positive control, reproduction of archived figures | §8 below; `tests/` |
| Results | Every number in `.claude/docs/FACTS.md`, each with its status | §9 below (do not hand-copy without checking status) |
| Discussion / limitations | What cannot yet be claimed and why | §10 below |
| Future work | Phase 14 (evaluation), open questions, blockers | §11 below |

---

## 3. Phase-by-phase build log (what was actually done, in order)

This is the project's real build sequence — `.claude/docs/PHASES.md` is the plan, this
table is what happened, cross-checked against `git log` and the current source tree.
Good raw material for a "development process" or "implementation" chapter, since a viva
examiner may ask what order things were built in and why.

| # | Phase | Deliverable | File(s) | Status |
|---|---|---|---|---|
| 0 | Repository skeleton | git repo, `.gitignore` covering the unblinding key and raw data | — | done |
| 1 | Item mapping & raw data | `item_mapping.csv`, `responses.csv`, 163×13, zero nulls | `src/load_data.py` | done |
| 2 | Item parameter estimation | GRM parameters via EM | `src/fit_params.py` | done |
| 3 | Cohort scoring | `theta_irt`, `theta_se` per dog | `src/score_cohort.py` | done |
| 4 | Phenotype clustering | k-means, k=3 by silhouette, labelled by profile shape not index | `src/cluster.py` | done |
| 5 | Rule engine | 9-cell matrix, MSD/AAHA evidence per cell | `src/rules.py` | done |
| 6 | Leakage guard | `FORBIDDEN_FEATURES` + positive control | `tests/test_pipeline.py` | done |
| 7 | Full cohort run & flag reconciliation | `pipeline_output_cohort.csv` | `src/run_pipeline.py --all` | done |
| 8 | Serialise Random Forest | real `predict_proba().max()` confidence, not the softmax stand-in | `src/train_rf.py`, `models/phenotype_rf.joblib` | done |
| 9 | Calibration against Darwin's Ark | `params_calibrated.csv`, `population_norms_theta.csv` | `src/calibrate.py` | done, reconciliation gap noted (§9) |
| 10 | Longitudinal tracking | 3-tier change detection, MDC95 guard | `src/longitudinal.py` | done |
| 11 | API layer | FastAPI wrapping `score_case()` | `src/api/` | done, and substantially extended (§7) |
| 12 | Owner-facing output | plain-language recommendation text | `src/api/services/report.py`, `report_pdf_data.py` | done, as a generated PDF report rather than only plain text |
| 13 | Reproducibility record | a `REPRODUCIBILITY.md` regenerating every `FACTS.md` row | — | **not yet written** — see §12 |
| 14 | Evaluation, external and gated | quadratic weighted kappa against blinded vet labels | — | **blocked**: no veterinary labels exist yet |

### Beyond the original phase plan

`PHASES.md` stops at a research-artefact API (one scoring endpoint). What actually exists
now is a small production-shaped backend, built across the git history visible in
`git log --oneline`:

```
ea17641 feature(migrations): created the alembic migrations for the schema
ded7eb2 feature(api): created the database models and auth layer
25b5433 feature(fastapi): created the api layer
c653a15 feature(longitudinal): created the longitudinal tracking
b438dcb feature(cbarq): verification of the thresholds
da3e3e4 feature(calibaration): calibarate with Dawins Ark
5a14b9c feature(rf): Random forest classification
5690065 test(Guard): created a guard to the random forest
6b6587f feature(rulebaseengine): created the rule base engine
d212bc2 feature(kmeans): unsupervised learning
dc85045 feature(assessment): validation chohort
b79491c feature(assessment): enhance the stability of the e/m algorithm
e87f8d3 feature(assessment): based on the e/m algorithm created the grm
aedd9c5 feature(assessment): preprocessing of the collected 163 survey data
ea85980 chore: basic file structure scaffolding
b9ac2f  feature(api): created rest endpoints for users, dogs, and assessments
4273317 feature(migrations): created the otp codes table
b5866aa feature(api): created otp generation and verification
acbc943 feature(api): created otp gated forget username and password flows
```

This is genuine additional implementation work — users, dogs, assessments, auth (JWT +
bcrypt), OTP-gated account recovery, a seven-table Postgres schema via Alembic, and a
PDF report generation subsystem — and belongs in the thesis as its own implementation
section (§7), distinct from the ML pipeline that `PHASES.md` was written for.

---

## 4. The finding the whole design rests on (motivation chapter material)

Write this near the front. It is the strongest justification for every subsequent design
choice, and it is a real methodological finding, not a framing device.

**The circularity.** The original design summed the twelve items into an Anxiety Index,
cut that index into three severity bands, and trained a Random Forest to predict those
bands *from the same twelve items*. The label was a deterministic function of the
features, so the classifier was learning arithmetic, not anxiety.

**The proof, not just the argument.** A single-feature decision tree trained on the index
alone recovers the label at accuracy **1.000** — not a coincidence, the mathematical
consequence of the label being computable from the feature. Across a seven-model
benchmark, ordinal logistic regression topped out at **0.951** precisely because it best
approximates a linear scoring rule; the Random Forest came **last of seven at 0.721**.
`0.951 belongs to ordinal logistic, not to the system`, and measures recovery of the
scoring formula, not clinical correctness — repeat this attribution every time the number
is used, or a reader will take it as the system's headline accuracy.

**What follows from fixing it, structurally:**
- Severity is produced by a *measurement model* (GRM/IRT), not a predictor.
- The Random Forest is reassigned: it no longer predicts severity, it supplies calibrated
  *confidence* on the phenotype label only.
- Recommendations come from a deterministic, evidence-cited rule engine, never a learned
  model — because a learned recommender has no provenance to show, and provenance is the
  only defensible claim available before veterinary labels exist.
- A test suite encodes the finding permanently: `tests/test_pipeline.py::test_no_leakage_features`
  asserts no classifier's feature list contains an aggregate (`anxiety_index`, `raw_score`,
  any subscale mean, any theta), and `test_leakage_is_demonstrable` is a **positive
  control** — it deliberately trains on the forbidden feature and asserts accuracy above
  0.95, so the guard cannot pass vacuously by, say, a typo'd feature name. Being able to
  explain *why the positive control exists* unprompted is the project's own bar for
  understanding this finding (`CODE_GUIDE.md`).

---

## 5. System architecture (methodology chapter backbone)

```
responses (12 items, 0-4)
   |
   +-- encode                subscale means retained for phenotype and rules only
   |
   +-- SEVERITY track                    +-- PHENOTYPE track
   |     GRM theta + per-dog SE          |     nearest centroid -> label
   |     population-referenced band      |     random forest -> confidence
   |     flag_irt if SE > 0.50           |     flag_rf if confidence < 0.70
   |     (withholds entirely)            |     (downgrades only)
   |                                     |
   +------------------+------------------+
                      |
                 rule engine (9 cells, MSD / AAHA)
                      |
             recommendation, or withheld
```

Two tracks, estimated independently, meeting only at the rule engine — this is what makes
a *disagreement* between "how anxious" and "what kind" visible instead of silently
averaged away. Full per-stage justification (why GRM and not sum score, why population
percentile and not cohort tertile, why nearest-centroid and not the forest for the label,
why two separate uncertainty flags and not one combined score, why no default branch in
the rule matrix) is written out in `.claude/docs/ARCHITECTURE.md` — it is already in
viva-answer prose and can largely be adapted directly into a methodology chapter, with
citations added.

Key numbers to anchor each stage (status-checked against `FACTS.md`, see §9 for the full
table with reproducibility status):

- GRM discrimination ranges **0.317 (Q11) to 3.736 (Q8)** — a ~12× spread, which is the
  quantitative case against equal-weighted sum scoring.
- Own-cohort parameters correlate **r = 0.938** with the two-item noise subscale but only
  **r = 0.519** with the seven-item generalised subscale — "a noise-sensitivity measure
  wearing an anxiety label." Darwin's-Ark-calibrated parameters reverse this (0.605 /
  0.852). This trade-off — lower reliability on the intended construct beats higher
  reliability on the wrong one — is, per `ARCHITECTURE.md`, "the single most important
  trade-off in the design" and should be stated in exactly those terms in the thesis.
- Nearest-centroid phenotype assignment beats the Random Forest at every missingness
  level tested (**0.957 vs 0.865** complete data, **0.819 vs 0.782** at three items
  blank), which is the evidentiary basis for keeping the forest out of labelling.
- Band width in theta is **0.769**; the 95% minimum detectable change for a single theta
  is **1.508**. A one-band move is therefore below the noise floor — `rules.detectable_change()`
  and `longitudinal.track_theta_change()` enforce that a single-band move is reported as
  "not distinguishable from measurement noise," never as deterioration.

---

## 6. Data and external corroboration (literature / data chapter material)

| Source | Role | File | n |
|---|---|---|---|
| Study survey | Primary instrument under development | `data/raw/responses.csv` | 163 |
| Darwin's Ark | Fixed item parameters + reference distribution for population-referenced bands | `src/calibrate.py` | **disputed: 18,385 or ~8,000 — must be resolved from the dataset itself before either figure is used** |
| C-BARQ | Item provenance and external corroboration that separation and noise/fear are separable constructs | `src/corroborate_cbarq.py`, `data/raw/CBARQ.dat` | 12,059 |
| German DOGS | Representativeness benchmark (demographic predictors of an anxiety proxy) — a **null result**, worth reporting as one | `src/benchmark_german_dogs.py` | 3,178 complete |
| DogMove IMU / Dog Aging Project | Evaluated as a possible sensor channel, **not used** | — | 45 / 47,444 |

Clinical evidence base for the rule engine's recommendation text: MSD Veterinary Manual,
"Behavior Problems of Dogs" (Borns-Weil), and the 2015 AAHA Canine and Feline Behavior
Management Guidelines (`docs/*.pdf`). `rules.py` cites section headers from these
documents verbatim in its `evidence` field per cell — this is what makes the
recommendation defensible as *provenance*, which is the only kind of defensibility
available pre-evaluation (§10).

---

## 7. System implementation (this is new material beyond the ML pipeline chapter)

The API layer (`src/api/`) is a substantially built-out FastAPI backend, not just the
single scoring endpoint `PHASES.md` phase 11 describes. Worth its own implementation
section.

**Stack:** FastAPI 0.128 + SQLAlchemy 2.0 (Postgres in production, SQLite in tests) +
Alembic migrations + Pydantic 2 validation + JWT (`pyjwt`) + bcrypt password hashing +
Playwright (headless Chromium) for PDF rendering + Resend for transactional email.
Full list in `requirements.txt`.

**Database schema** (`src/api/models.py`, seven tables, Alembic migrations in
`alembic/versions/`):
`users`, `dogs`, `assessment` (one row per `score_case()` call — persists `theta_irt`
*or* `theta_calibrated`, never a bare `theta`, matching the naming discipline in
`CODE_GUIDE.md`), `irt_response` (one row per item, not one wide row), `recommendation`
(a static mirror of `rules.py`'s nine cells, seeded once by a data migration, never read
back into scoring logic), `report`, `otp_codes`. The ORM layer is deliberately one-way:
the DB calls into the ML core (`run_pipeline.score_case()`), never the reverse.

**Auth & account recovery:** JWT-based auth (`src/api/auth.py`), role-gated endpoints
(`owner` vs `admin` via `require_role`), and an OTP-gated forget-username/forget-password
flow backed by a DB table rather than a stateless token specifically so verification
attempts can be capped against brute force (`src/api/services/otp.py`,
`src/api/routers/auth.py`).

**Report generation:** `POST /api/v1/report/generate` builds a JSON audit snapshot
(`services/report.py`) *and* renders a vet-facing PDF via Playwright
(`services/report_pdf.py`, `report_pdf_data.py`, `report_chart.py`, a Jinja2 template at
`src/api/templates/report.html`). The PDF context assembly
(`build_pdf_context` in `report_pdf_data.py`) is worth describing in detail in an
implementation chapter: it pulls prior assessments for the same dog to compute a
longitudinal trend banner via `longitudinal.track_theta_change()`, renders an inline SVG
severity chart, and formats the rule engine's recommendation text into bulleted,
sourced, owner-appropriate language — this is effectively where Phase 12
("owner-facing output") actually landed, as a generated document rather than a plain-text
function. **This PDF subsystem is currently uncommitted work** (`git status` shows
`report_chart.py`, `report_pdf.py`, `report_pdf_data.py`, `report_sources.py`,
`report_storage.py`, and `src/api/templates/` as untracked) — flag this to your
supervisor/examiner as in-progress if the thesis draft describes it as finished.

**API design conventions worth naming in a thesis:** every endpoint response is wrapped
in a `{"code", "response"}` envelope (`src/api/errors.py`) except the PDF download route,
which streams a raw file body with a `Content-Disposition` header — the router comment at
`src/api/routers/report.py` explains why that one route is the exception. A withheld
recommendation returns HTTP 200 with the withheld payload, not an error, matching
`PHASES.md` phase 11's explicit requirement that withholding is a valid result.

---

## 8. Testing and validation strategy (methodology chapter, or its own section)

82 tests across 15 files (`tests/`), run with `python -m pytest tests/ -v`. All passing at
time of writing. The project's own testing philosophy, worth quoting or paraphrasing:
*"Each test encodes a defect that was actually found in this project's outputs. Name them
after the defect, not after the function."* (`CODE_GUIDE.md`)

Tests that map directly to claims worth making in a thesis:

| Test | What it proves |
|---|---|
| `test_no_leakage_features` + `test_leakage_is_demonstrable` | The leakage guard, with a positive control so it cannot pass vacuously (§4) |
| `test_grm_reproduces_archive` | The GRM implementation reproduces archived theta at r = 1.0000, max diff < 0.001 |
| `test_calibrated_item_count` | The calibrated model scores exactly eleven items (Q11 excluded), and fails loudly if the item mapping ever silently changes |
| `test_phenotype_labels_follow_profile_not_index` | Cluster-to-label mapping is by profile shape, not k-means' arbitrary initialisation order — re-running with a different seed cannot silently relabel the cohort |
| `test_single_band_change_is_not_detectable` | The system refuses to call a one-band move "deterioration" when it is below the MDC95 noise floor |
| `test_flag_irt_withholds_and_flag_rf_downgrades` | The two uncertainty flags behave asymmetrically as designed, never merged |
| `test_all_nine_cells_have_evidence` | No rule-matrix cell is silently uncited |
| `test_to_dict_is_json_serialisable` | The audit trail contains no numpy scalars / objects / file paths before it reaches the API boundary |

Note for a "results reproduce the analysis" section: `tests/test_irt.py`'s
archive-reproduction test is the direct evidence for the GRM implementation's fidelity to
the prior analysis; the leakage tests are the direct evidence for §4's finding; the
longitudinal tests are the direct evidence for the MDC95 claim in §5.

---

## 9. Numbers — what is safe to write into the thesis right now

**Do not copy a number out of this table without also copying its status.**
`FACTS.md` is the canonical source; this is a condensed pointer to it, not a replacement.
Three statuses only: **target** (from the prior analysis, an acceptance target for this
rebuild — not yet this repository's own result), **regenerated** (produced by a script
here, with the command recorded), **not reproducible** (do not quote).

| Quantity | Value | Status |
|---|---|---|
| Cohort size / items / missing | 163 / 12 (Q4–Q15) / 0 | target |
| GRM reproduces archived theta | r = 1.0000, max diff 0.0009 | target (guarded by `test_irt.py`) |
| Marginal reliability (name the denominator, always) | 0.761 observed-variance / 0.809 prior-variance | target — **the thesis currently also contains an orphan 0.763 with no source; remove it** |
| Discrimination range | 0.317 (Q11) to 3.736 (Q8) | target |
| Cut-points (75th / 90th percentile) | 0.537 / 1.013 | target |
| **Band counts, chapter's stated 98 / 24 / 41** | — | **not reproducible** — rests on a calibrated theta that was never persisted; this is called out in `FACTS.md` as "the single largest liability in the thesis" |
| Band counts on own-cohort theta at the chapter's cut-points | 112 / 30 / 21 | target (what the saved artefacts actually give) |
| Band counts, stale `severity_popnorm` column | 16 / 29 / 118 | **do not use** — computed on the superseded anxiety-index scale |
| `flag_irt` / `flag_rf` counts | 64 / 64 | target |
| Both flags | 26 | target |
| **Either flag ("routed for review")** | **102 (62.6%)** | target — **"64 dogs routed for review" is a documented error; 64 is each flag separately** |
| Recommendation withheld | 37 of 163 (22.7%) | target, computed with the pre-Phase-8 confidence stand-in — expected to move now the forest is serialised |
| Phenotype k / counts | 3 by silhouette; Mild 61, Noise-specific 57, Generalised 45 (analysis) vs 62/57/44 (centroid rule) | target — the two count sets differ by one dog **by design**, state which procedure a figure comes from |
| Cluster stability (ARI) | 0.982 | target — supersedes an earlier 0.889 figure; confirm any citation uses the current one |
| Nearest centroid vs forest (complete / 3 blank) | 0.957 vs 0.865 / 0.819 vs 0.782 | target |
| Macro-F1, rule vs forest | 0.954 vs 0.887 | target |
| **Best benchmark accuracy** | **0.951 — belongs to ordinal logistic, not the system** | target — always attribute |
| Random Forest benchmark accuracy | 0.721, last of 7 | target |
| Single-feature tree on the index | 1.000 | target — the leakage proof, not a performance figure |
| Band width (theta) / MDC95 single theta | 0.769 / 1.508 | target |
| MDC tier 1 / 2 / 3 | 0.68 / 1.00 / 0.18 | target |
| Darwin's Ark n | **disputed: 18,385 or ~8,000** | unresolved — resolve from the dataset before writing either number anywhere |

Figures carried forward from earlier revisions that need their comparison re-checked
before reuse (`FACTS.md` "Figures carried forward" table): cohort median enrichment
(63.6th percentile, not 95th — the 95th compared different instruments), reference
subscale correlation (r = 0.303, not 0.291), reclassification under calibration (~43%)
vs reclassification theta-vs-sum-tertiles (~41%) — **these are two different comparisons,
do not conflate them.**

---

## 10. What cannot be claimed yet — write these as explicit limitations

Five claims the project's own documentation flags as currently indefensible
(`FACTS.md`, `PIPELINE.md`). Each needs to be softened or attributed everywhere it
appears in the draft:

1. **Any accuracy, correctness, or clinical-validity claim about the system as a whole.**
   There is no external criterion until veterinary labels exist (Phase 14, blocked).
2. **The rule engine's recommendations as validated output.** They are defensible as
   *provenance* — traceable to MSD/AAHA — not as agreement with what a vet would actually
   recommend for this instrument. Nobody has checked that.
3. **The phenotype labels as clinical entities.** "Noise-specific" is a robust,
   externally-corroborated statistical cluster; whether it corresponds to a category a
   vet would recognise is untested.
4. **"Confidence above 0.7 is never wrong."** True only about agreement with the cluster
   label, which is derived from the same items the confidence is computed on. It says
   nothing about clinical correctness — phrase it as agreement with the clustering.
5. **Any severity threshold as a clinical action point.** The 90th percentile is a
   distributional choice, not a validated referral trigger, until someone with clinical
   standing says otherwise.

Also avoid, project-wide, in any output-describing sentence: *"validated," "accurate,"
"clinically [X]," "diagnosis/diagnosed"* — these words are explicitly banned from code,
docstrings, and UI copy (`CODE_GUIDE.md`) for the same reason; the thesis prose should
hold itself to the same standard for consistency.

---

## 11. Open questions and blockers (for a "limitations and future work" chapter)

Unresolved questions the project's own `CLAUDE.md` says only the author can settle —
useful to name explicitly in a future-work section rather than silently pick one:

| Question | Conflicting sources |
|---|---|
| How many cases get blinded vet labels? | Earlier design: 40 held out (D124–D163). Validation snapshot: 67 stratified. |
| Is there still a train/holdout split? | Thresholds became population-referenced, so the original 123/40 rationale may no longer apply as stated. |
| Darwin's Ark n | 18,385 vs ~8,000 (`irt.py` docstring) |
| Which reliability figure is *the* reported one | Chapter contains both 0.761 and 0.763; 0.763 has no traceable source |

**Phase 14 (evaluation)** is explicitly blocked until veterinary labels exist, and the
design decision to freeze thresholds before any label is seen must be stated as a design
decision in the methodology, not discovered as a limitation later: tuning thresholds
against labelled cases and then evaluating on the same cases would be circular.

**Phase 13 (reproducibility record)** — a `REPRODUCIBILITY.md` listing every `FACTS.md`
claim, the exact command that regenerates it, and the value obtained — has not been
written yet. This is described in the project's own docs as "the artefact that answers
'can you prove this' under examination," i.e. close to load-bearing for a viva. Worth
prioritising before submission regardless of whether it goes in the thesis body or an
appendix.

**The Phase 9 reconciliation gap** (§9, the 98/24/41 vs 112/30/21 discrepancy) is the
single item flagged as "the largest liability in the thesis" — resolve or explicitly
narrate it; do not silently prefer one number.

---

## 12. Practical checklist before submission

- [ ] Every number quoted in the thesis has a row in `FACTS.md` (or this guide) with a
      status other than "not reproducible."
- [ ] The orphan reliability figure 0.763 is removed or sourced.
- [ ] "64 dogs routed for review" is replaced with the either-flag figure (102, 62.6%) or
      explicitly scoped to one named flag.
- [ ] 0.951 is never written without naming ordinal logistic as the model it belongs to.
- [ ] The 98/24/41 vs 112/30/21 band-count discrepancy is addressed, not silently picked.
- [ ] `docs/instrument/` item wording is confirmed to match `run_pipeline.py`'s `ITEM_TEXT`
      for Q7/Q8 (documented as transposed at one point) and Q14/Q15 (documented as
      describing different behaviours across sources).
- [ ] Section 5 vocabulary guardrails (§10 above) hold across the whole document, not just
      the results chapter.
- [ ] `REPRODUCIBILITY.md` (Phase 13) exists, or its absence is acknowledged as
      in-progress work.
- [ ] The uncommitted PDF-report files (§7) are either committed or described as
      work-in-progress, not as a finished, tested subsystem.
