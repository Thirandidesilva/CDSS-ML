"""create_app() factory: mounts routers, loads the scoring model once, wires the DB engine."""
from __future__ import annotations

from typing import Optional

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import run_pipeline  # noqa: E402

from . import db  # noqa: E402
from .config import get_settings  # noqa: E402
from .errors import register_exception_handlers  # noqa: E402
from .routers import assessment, auth, dogs, report, users  # noqa: E402
from .services.report_pdf import LazyPdfRenderer, PdfRenderer  # noqa: E402


def create_app(*, pdf_renderer: Optional[PdfRenderer] = None) -> FastAPI:
    # Called exactly once per process (uvicorn on startup, or once per test via the
    # api_client fixture) — everything below runs a single time, not per request.
    owns_renderer = pdf_renderer is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # LazyPdfRenderer launches Chromium on the first report request, not here, so a
        # server without Chromium still boots (see services/report_pdf.py). Tests inject
        # a ready PdfRenderer instead.
        app.state.pdf_renderer = pdf_renderer if pdf_renderer is not None else LazyPdfRenderer()
        yield
        if owns_renderer:
            app.state.pdf_renderer.close()

    app = FastAPI(title="Canine Anxiety CDSS", description=__doc__, lifespan=lifespan)

    db.init_engine(get_settings().database_url)
    # Loaded once and reused for every request via app.state — see routers/assessment.py.
    # Never re-fit or re-loaded per request; that would be slow and pointless since the
    # underlying model files don't change while the server is running.
    app.state.scoring_model = run_pipeline.load_scoring_model()

    register_exception_handlers(app)

    # Order doesn't matter for routing (each router has its own url prefix), but this
    # is the one place that shows every resource this API exposes.
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(dogs.router)
    app.include_router(assessment.router)
    app.include_router(report.router)

    return app
