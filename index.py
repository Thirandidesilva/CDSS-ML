"""Vercel entrypoint: Vercel's Python runtime looks for a module-level `app` here.

The API itself lives in src/api; this file only puts src/ on the import path and builds
the app once per instance (which also loads the scoring model).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from api.app import create_app  # noqa: E402

app = create_app()
