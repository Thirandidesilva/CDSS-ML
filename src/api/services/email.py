"""Email sender via Resend's HTTP API. The only file in this project that imports
`resend`. Same public signature as before (to, subject, body), so callers and the
sent_emails test fixture that monkeypatches this exact function don't need to change.
"""
from __future__ import annotations

import resend

from ..config import get_settings


def send_email(to: str, subject: str, body: str) -> None:
    # Called as `email_service.send_email(...)` from routers/auth.py (module reference,
    # not `from .email import send_email`) so tests can monkeypatch this exact attribute
    # and have every caller see the patched version.
    settings = get_settings()
    resend.api_key = settings.resend_api_key
    resend.Emails.send({
        "from": settings.email_from_address,
        "to": to,
        "subject": subject,
        "text": body,
    })
