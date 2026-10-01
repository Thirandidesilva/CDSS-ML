# Pawsitivity — Canine Anxiety Clinical Decision Support System

A final-year BSc research project (Coventry University with NIBM) that screens dogs for
anxiety from a twelve-item owner questionnaire, and a REST API + PDF report generator
built on top of it so the screening result can actually reach an owner or a vet.

The deliverable is a defensible research artefact, not a product demo: every number the
system produces has a script behind it that can be re-run and re-derived, not a figure
copied into a document by hand.

## What it does

1. **Measures severity** with a graded response model (item response theory) fit on the
   twelve items, not a summed score — the original design summed the items into an
   "Anxiety Index" and then trained a classifier on that same index, which is circular
   (the classifier was learning arithmetic, not anxiety). Every design choice below
   follows from fixing that. See `.claude/docs/CLAUDE.md` for the full account.
2. **Identifies a behavioural phenotype** (Mild / Noise-specific / Generalised) via
   k-means clustering, with a Random Forest supplying a calibrated confidence score
   (not the label itself).
3. **Produces a recommendation** from a deterministic, nine-cell rule matrix
   (severity × phenotype), each cell cited to MSD Veterinary Manual or AAHA guidelines,
   with no default branch — an uncovered case routes to "see a vet" rather than a guess.
   Two uncertainty flags (imprecise severity, uncertain phenotype) gate the
   recommendation independently and are never combined into one score.
4. **Tracks change over time** against a minimum-detectable-change threshold, so a
   single-band shift is correctly reported as "not distinguishable from noise" rather
   than as improvement or deterioration.
5. **Serves all of the above through a REST API** — accounts, dog profiles, assessment
   history, OTP-verified account recovery, and a generated clinical PDF report — backed
   by Postgres (Supabase) and documented at `/docs`.

## Repository layout

```
src/
  irt.py, fit_params.py        GRM item-response scoring and estimation
  cluster.py, train_rf.py      phenotype clustering + confidence model
  calibrate.py                 calibration against Darwin's Ark
  rules.py                     the 9-cell recommendation matrix
  longitudinal.py               minimum-detectable-change tracking
  run_pipeline.py              orchestrates every stage; the CLI entry point
  score_cohort.py, load_data.py, corroborate_cbarq.py, benchmark_german_dogs.py
  api/                         the FastAPI service (see below)
    models.py                  SQLAlchemy schema (users, dogs, assessments, reports, OTP codes, ...)
    routers/                   auth, users, dogs, assessment, report
    services/                  scoring bridge, OTP, email (Resend), PDF report rendering
    templates/report.html      the vet-facing PDF template (Jinja2 + inline SVG chart)
alembic/                       hand-written DB migrations (no live DB to autogenerate against)
tests/                         pytest suite — pipeline tests + full API test suite
data/, results/, models/       cohort data, regenerable pipeline outputs, the fitted RF model
docs/                          source PDFs (MSD, AAHA), openapi.json, THESIS_GUIDE.md
.claude/docs/                  the project's own working conventions (CLAUDE.md, ARCHITECTURE.md,
                                PHASES.md, CODE_GUIDE.md, FACTS.md) — read these before changing src/
```

## Setup

Requires Python 3.9 (the venv here is pinned to it — code uses `typing.Optional` rather
than `X | None` syntax throughout for that reason).

```bash
git clone <this repo> && cd CDSS-ML
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium   # one-time; not pip-installable — needed for PDF reports
```

## Running the ML pipeline

No configuration needed — reads straight from `data/reference/` and `results/`.

```bash
python -m pytest tests/ -v                # full suite (82 tests as of this writing)
python src/run_pipeline.py                # scores 3 demo dogs, prints every stage
python src/run_pipeline.py --all          # scores the full 163-dog cohort
python src/run_pipeline.py --interactive  # enter one dog's answers by hand
```

## Running the backend API

### 1. Configure `.env`

```bash
cp .env.example .env
```

Fill in:

| Group | Variables | Notes |
|---|---|---|
| Database | `DATABASE_URL` | Postgres. This project uses Supabase — use the **Session pooler** connection string (`aws-0-<region>.pooler.supabase.com:5432`), not the direct `db.<ref>.supabase.co` host, which is IPv6-only and may not resolve on your network. Needs the `+psycopg` driver prefix (`postgresql+psycopg://...`) — the bare `postgresql://` scheme defaults to `psycopg2`, which isn't installed. For quick local testing without Supabase, `DATABASE_URL=sqlite:///./dev.db` also works. |
| Auth | `JWT_SECRET`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `RESET_TOKEN_EXPIRE_MINUTES` | `JWT_SECRET` must be a real random value before running for real. |
| Email (OTP) | `RESEND_API_KEY`, `EMAIL_FROM_ADDRESS` | Sent via Resend's HTTP API. `EMAIL_FROM_ADDRESS` must be either Resend's sandbox sender on `resend.dev` (only deliverable to the email the Resend account itself was signed up with) or an address on a domain verified in that Resend account (Dashboard → Domains → add the SPF/DKIM records). |
| OTP | `OTP_EXPIRE_MINUTES`, `OTP_MAX_ATTEMPTS` | Defaults: 10 minutes, 5 attempts. |

### 2. Apply migrations

```bash
alembic upgrade head
```

Creates all tables (`users`, `dogs`, `assessment`, `irt_response`, `recommendation`,
`report`, `otp_codes`) and seeds the 9 static recommendation rows straight from
`rules.py`. Safe to re-run.

### 3. Start the server

```bash
uvicorn api:create_app --factory --app-dir src --reload
```

`--factory` matters: `create_app()` is a factory function (it also launches a headless
Chromium instance for PDF rendering), not a bare `app` object.

Open **http://127.0.0.1:8000/docs** for the interactive Swagger UI (or read
`docs/openapi.json` directly — regenerate it with the same `app.openapi()` call the
existing routers use if the API surface changes).

## What the API does

All endpoints are under `/api/v1/{auth,users,dogs,assessment,report}`, respond with a
`{"code": "XXXX", "response": [...]}` envelope (business codes documented per-endpoint
in `/docs`), and return real HTTP status codes for genuine transport-layer failures
(401/403/404/422/500) while using `code` for business outcomes (wrong password,
duplicate email, etc.) that are still a well-formed 200.

- **Auth** — register, login (JWT bearer tokens), and an OTP-gated account-recovery
  flow: `forget-username`/`forget-password` email a 6-digit code (DB-backed with
  capped verification attempts, not a stateless token — a code needs real brute-force
  protection), and only `verify-otp` succeeding reveals the username (by email) or
  issues the token that unlocks `reset-password`.
- **Users / Dogs** — profile and dog-profile CRUD, owner-scoped, with admin-only
  "list everyone" routes.
- **Assessment** — `GET questions` (the 12 items), `POST submit` (runs the scoring
  pipeline via `score_case()` and persists the full audit trail), history listing.
- **Report** — `POST generate` builds both a JSON audit snapshot and a rendered
  two-page clinical PDF (Playwright + Jinja2 + an inline-SVG severity trend chart);
  `GET download/{id}` streams the actual PDF.

## Testing

```bash
python -m pytest tests/ -v
```

No live database or real email/PDF delivery is required — the suite uses an in-memory
SQLite database per test, monkeypatches the email sender to capture outgoing messages
instead of calling Resend, and launches one headless-Chromium instance for the whole
test session (not per test) for the PDF-rendering tests.

## Conventions worth knowing before changing `src/`

Full detail lives in `.claude/docs/CLAUDE.md` / `CODE_GUIDE.md` / `ARCHITECTURE.md` —
the short version:

- Never let an aggregate score (`anxiety_index`, any `theta`, a subscale mean) reach a
  classifier's feature matrix — `FORBIDDEN_FEATURES` in `tests/test_pipeline.py` is the
  enforced guard.
- `flag_irt` and `flag_rf` are never combined into a single score.
- A one-band severity move is not, by itself, evidence of change — see
  `rules.detectable_change()` / `longitudinal.py` (MDC95 = 1.508).
- No default branch in the recommendation matrix; an uncovered cell routes to
  veterinary review rather than inventing advice.
- `results/vet_sheet_key_DO_NOT_SHARE.csv` (the blinded-case unblinding key) must never
  be displayed, logged, or committed.
- Nothing in `handoff/verified_facts.json` is a result until this repository
  regenerates it — those are acceptance targets, not source-of-truth numbers.

## Project status

`docs/THESIS_GUIDE.md` has the full phase-by-phase build log, a thesis chapter map, and
which numbers are currently safe to quote. `.claude/docs/PHASES.md` is the original
build plan. In short: the research pipeline (measurement, phenotyping, rules,
longitudinal tracking) and the full REST API (auth, OTP, dogs, assessments, PDF
reports) are built and tested; Phase 14 (external evaluation against blinded
veterinary labels) is blocked on those labels existing.
