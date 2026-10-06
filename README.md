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
    services/                  scoring bridge, OTP, email (Resend), PDF report rendering (ReportLab)
    templates/report.html      the vet-facing PDF template (Jinja2 + inline SVG chart)
alembic/                       hand-written DB migrations (no live DB to autogenerate against)
tests/                         pytest suite — pipeline tests + full API test suite
data/, results/, models/       cohort data, regenerable pipeline outputs, the fitted RF model
docs/                          source PDFs (MSD, AAHA), openapi.json, THESIS_GUIDE.md
.claude/docs/                  the project's own working conventions (CLAUDE.md, ARCHITECTURE.md,
                                PHASES.md, CODE_GUIDE.md, FACTS.md) — read these before changing src/
```

## Setup

Runs on Python 3.9 to 3.12 (code uses `typing.Optional` rather than `X | None` syntax
throughout so 3.9 keeps working). The Vercel deployment uses 3.12 (`.python-version`); the
full test suite passes on both 3.9 and 3.12.

```bash
git clone <this repo> && cd CDSS-ML
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # requirements.txt is the runtime-only subset (what gets deployed)
```

## Running the ML pipeline

No configuration needed — reads straight from `data/reference/` and `results/`.

```bash
python -m pytest tests/ -v                # full suite (154 tests as of this writing)
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
| Auth | `JWT_SECRET`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `RESET_TOKEN_EXPIRE_MINUTES` | `JWT_SECRET` must be a real random value before running for real. Defaults: access token 30 minutes, refresh token 30 days. An `ACCESS_TOKEN_EXPIRE_MINUTES` left over in a host's settings overrides the default. |
| Email (OTP) | `RESEND_API_KEY`, `EMAIL_FROM_ADDRESS` | Sent via Resend's HTTP API. `EMAIL_FROM_ADDRESS` must be either Resend's sandbox sender on `resend.dev` (only deliverable to the email the Resend account itself was signed up with) or an address on a domain verified in that Resend account (Dashboard → Domains → add the SPF/DKIM records). |
| OTP | `OTP_EXPIRE_MINUTES`, `OTP_MAX_ATTEMPTS` | Defaults: 10 minutes, 5 attempts. |

### 2. Apply migrations

```bash
alembic upgrade head
```

Creates all tables (`users`, `dogs`, `assessment`, `irt_response`, `recommendation`,
`report`, `otp_codes`, `refresh_tokens`) and seeds the 9 static recommendation rows straight from
`rules.py`. Safe to re-run.

### 3. Start the server

```bash
uvicorn api:create_app --factory --app-dir src --reload
```

`--factory` matters: `create_app()` is a factory function, not a bare `app` object.
(`index.py` at the repo root builds it once and exposes `app`, which is what Vercel looks for.)

Open **http://127.0.0.1:8000/docs** for the interactive Swagger UI (or read
`docs/openapi.json` directly; it is generated from `create_app().openapi()` and must be
regenerated whenever the API surface changes).

## What the API does

All endpoints are under `/api/v1/{auth,users,dogs,assessment,report}`, respond with a
`{"code": "XXXX", "response": [...]}` envelope (business codes documented per-endpoint
in `/docs`), and return real HTTP status codes for genuine transport-layer failures
(401/403/404/422/500) while using `code` for business outcomes (wrong password,
duplicate email, etc.) that are still a well-formed 200.

- **Auth** — register, login, and renewal: login returns a short-lived access token (JWT,
  30 minutes) and a refresh token (opaque, 30 days, stored only as a hash). `POST /auth/refresh`
  trades a refresh token for a new pair, and works after the access token has expired; every
  use retires the token it was given. A token that was used long ago and shows up again is a
  copy, so its whole sign-in is revoked (a repeat within 30 seconds is forgiven, for a lost
  reply). `POST /auth/logout` revokes the session; deleting the account revokes them all.
  Clients should renew shortly before `expires_in` runs out. Account recovery is OTP-gated:
  flow: `forget-username`/`forget-password` email a 6-digit code (DB-backed with
  capped verification attempts, not a stateless token — a code needs real brute-force
  protection), and only `verify-otp` succeeding reveals the username (by email) or
  issues the token that unlocks `reset-password`.
- **Users / Dogs** — profile and dog-profile CRUD, owner-scoped, with admin-only
  "list everyone" routes. A base64 `profile_picture` on users/update and dogs/create|update is
  uploaded to Cloudinary by the server (code `5001` when the host has no Cloudinary settings).
- **Assessment** — `GET questions` (the 12 items), `POST submit` (runs the scoring
  pipeline via `score_case()` and persists the full audit trail), `list-by-dog`, `get`,
  `delete` (soft), `stats`, and `weekly-summary`. Each assessment carries `created_at` (UTC) and
  `anxiety_index`, a 0 to 1 display value built from theta so that it always agrees with the
  severity band. `weekly-summary` accepts `utc_offset_minutes` (-840 to 840, default 0) so the
  week and each assessment's day follow the caller's clock.
- **Health** — `GET /health` answers `{"status": "ok"}` with no login or database, so a client
  can wake a sleeping host.
- **Report** — `POST generate` stores a JSON audit snapshot; `GET download/{id}` draws the
  two-page clinical PDF on demand with ReportLab (pure Python, severity trend chart
  included) from the stored rows. Nothing is written to disk, so it works on a serverless
  host.

## Testing

```bash
python -m pytest tests/ -v
```

No live database or real email/PDF delivery is required — the suite uses an in-memory
SQLite database per test, monkeypatches the email sender to capture outgoing messages
instead of calling Resend. PDF tests render real PDFs in memory with ReportLab.

## Deploying to Vercel

`index.py`, `vercel.json`, `.vercelignore` and `.python-version` are the whole setup; Vercel
installs `requirements.txt`. Set the same variables as `.env.example` in the Vercel project,
with `DATABASE_URL` pointing at Supabase's transaction pooler (port 6543) and
`DB_POOL_MODE=null`. Run Alembic migrations from your own machine against the direct
(port 5432) URL — they are not part of the deployed bundle.

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
