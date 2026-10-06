"""Email sender via Resend's HTTP API. The only file in this project that imports
`resend`. Same public signature as before (to, subject, body), so callers and the
sent_emails test fixture that monkeypatches this exact function don't need to change.
"""
from __future__ import annotations

import logging

import resend

from ..codes import BusinessCode
from ..config import get_settings
from ..errors import ApiError

log = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str, html: str | None = None) -> None:
    # Called as `email_service.send_email(...)` from routers/auth.py (module reference,
    # not `from .email import send_email`) so tests can monkeypatch this exact attribute
    # and have every caller see the patched version.
    settings = get_settings()
    resend.api_key = settings.resend_api_key
    try:
        params = {
            "from": settings.email_from_address,
            "to": to,
            "subject": subject,
            "text": body,
        }
        if html:
            params["html"] = html  # `text` stays as the plain-text alternative
        resend.Emails.send(params)
    except Exception:
        # Resend refuses plenty of ordinary cases (sandbox accounts may only email their own
        # owner, unverified sender domain, bad key, rate limit, network). An unhandled one
        # used to surface as an opaque 500 / code 9000. The real reason goes to the server
        # log only; the caller gets a generic, safe message.
        log.exception("could not send email via Resend (to=%s, subject=%r)", to, subject)
        raise ApiError(BusinessCode.EMAIL_SEND_FAILED, "we couldn't send the email right now")
