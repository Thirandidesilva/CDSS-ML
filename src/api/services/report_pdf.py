"""Orchestrates template render + Playwright PDF export. The only file in this project
that imports playwright.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

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
        self._executor.submit(self._start).result()

    def _start(self) -> None:
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch()

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
