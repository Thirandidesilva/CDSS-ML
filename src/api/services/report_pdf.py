"""Orchestrates template render + Playwright PDF export. The only file in this project
that imports playwright.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..codes import BusinessCode
from ..errors import ApiError

log = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def _render_html(context: dict) -> str:
    return _env.get_template("report.html").render(**context)


class PdfRenderer:
    """Owns one headless-Chromium instance on one dedicated worker thread.

    Playwright's sync API is pinned to whichever thread calls sync_playwright().start()
    and cannot be used from any other thread. FastAPI runs sync `def` route handlers in
    a threadpool, so a request handler calling straight into a browser launched at app
    startup could easily land on a *different* thread than the one that launched it —
    this raised `greenlet.error: Cannot switch to a different thread` in testing.
    Routing every Playwright call through this single-worker executor guarantees they
    always run on the one thread that owns them, and serializes access to the shared
    Browser as a side effect (no separate lock needed).
    """

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1)
        try:
            self._executor.submit(self._start).result()
        except Exception:
            # Don't leave an idle worker thread behind for every failed attempt.
            self._executor.shutdown(wait=False)
            raise

    def _start(self) -> None:
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch()
        except Exception:
            # Chromium missing/unlaunchable: also stop the Playwright driver process
            # that start() just spawned, or it lingers.
            self._playwright.stop()
            raise

    def render_pdf(self, context: dict) -> bytes:
        html = _render_html(context)
        return self._executor.submit(self._render, html).result()

    def _render(self, html: str) -> bytes:
        page = self._browser.new_page()
        try:
            page.set_content(html)
            return page.pdf(format="A4", print_background=True, margin={
                "top": "0", "bottom": "0", "left": "0", "right": "0",
            })
        finally:
            page.close()

    def close(self) -> None:
        self._executor.submit(self._stop).result()
        self._executor.shutdown(wait=True)

    def _stop(self) -> None:
        self._browser.close()
        self._playwright.stop()


class LazyPdfRenderer:
    """Starts Chromium on the first report request instead of at app startup.

    Launching it eagerly meant a server without Chromium (or too little memory for it)
    refused to boot at all, taking login, dogs and assessments down over an optional
    feature. Lazily, only POST /report/generate is affected: if Chromium can't start,
    that request answers 503 with business code 4004 and everything else keeps working.
    A failed start is not cached, so installing Chromium fixes it without a restart.
    """

    def __init__(self, factory: Callable[[], PdfRenderer] = PdfRenderer) -> None:
        self._factory = factory
        self._renderer: Optional[PdfRenderer] = None
        self._lock = threading.Lock()

    def render_pdf(self, context: dict) -> bytes:
        return self._get().render_pdf(context)

    def _get(self) -> PdfRenderer:
        # The lock also stops two simultaneous first requests from launching two browsers.
        with self._lock:
            if self._renderer is None:
                try:
                    self._renderer = self._factory()
                except Exception:
                    log.exception("could not start Chromium for PDF reports")
                    raise ApiError(
                        BusinessCode.REPORT_UNAVAILABLE, "pdf reports are not available on this server"
                    )
            return self._renderer

    def close(self) -> None:
        with self._lock:
            if self._renderer is not None:
                self._renderer.close()
                self._renderer = None
