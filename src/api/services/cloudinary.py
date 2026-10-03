"""Profile-photo storage on Cloudinary.

The app sends the photo inside the request it already makes (users/update, dogs/create,
dogs/update) as a base64 data URI in `profile_picture`. This module uploads it to
Cloudinary from the server — so the API secret never leaves it — and the caller stores
the returned https URL instead of the image. Any other value (an existing URL, None) is
passed through untouched.

Signing rule (Cloudinary docs, "Generating authentication signatures"): every parameter
sent EXCEPT file, cloud_name, resource_type and api_key, sorted by name, joined as
name=value with "&", API secret appended, SHA-1.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
import time
from typing import Optional

import requests

from ..codes import BusinessCode
from ..config import get_settings
from ..errors import ApiError

ALLOWED_MIME_TYPES = ("image/jpeg", "image/png", "image/webp", "image/heic")
ALLOWED_FORMATS = "jpg,jpeg,png,webp,heic"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
UPLOAD_TIMEOUT_SECONDS = 20

_DATA_URI = re.compile(r"^data:(?P<mime>[a-z0-9.+/-]+);base64,(?P<data>.+)$", re.DOTALL)


def is_data_uri(value: Optional[str]) -> bool:
    return bool(value) and value.startswith("data:")


def sign_params(params: dict, api_secret: str) -> str:
    to_sign = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return hashlib.sha1((to_sign + api_secret).encode("utf-8")).hexdigest()


def _decode_image(data_uri: str) -> tuple:
    """Returns (mime, raw_bytes), or raises INVALID_IMAGE. Checked before any network call."""
    invalid = ApiError(BusinessCode.INVALID_IMAGE, "image must be a base64 jpeg/png/webp/heic data URI")
    match = _DATA_URI.match(data_uri)
    if match is None or match.group("mime") not in ALLOWED_MIME_TYPES:
        raise invalid
    try:
        raw = base64.b64decode(match.group("data"), validate=True)
    except (binascii.Error, ValueError):
        raise invalid
    if not raw:
        raise invalid
    if len(raw) > MAX_IMAGE_BYTES:
        raise ApiError(BusinessCode.INVALID_IMAGE, "image is larger than 5 MB")
    return match.group("mime"), raw


def upload_image(data_uri: str, public_id: str) -> str:
    """Uploads the image and returns its https URL. A fixed public_id with overwrite means
    a new photo replaces the old one instead of leaving orphans, and invalidate clears the
    CDN's cached copy of the old one.
    """
    settings = get_settings()
    if not (settings.cloudinary_cloud_name and settings.cloudinary_api_key and settings.cloudinary_api_secret):
        raise ApiError(BusinessCode.UPLOAD_NOT_CONFIGURED, "image uploads are not configured")

    mime, raw = _decode_image(data_uri)

    signed = {
        "allowed_formats": ALLOWED_FORMATS,
        "invalidate": "true",
        "overwrite": "true",
        "public_id": public_id,
        "timestamp": str(int(time.time())),
    }
    fields = {
        **signed,
        "api_key": settings.cloudinary_api_key,
        "signature": sign_params(signed, settings.cloudinary_api_secret),
    }
    url = f"https://api.cloudinary.com/v1_1/{settings.cloudinary_cloud_name}/image/upload"
    try:
        resp = requests.post(
            url, data=fields, files={"file": ("photo", raw, mime)}, timeout=UPLOAD_TIMEOUT_SECONDS
        )
        secure_url = resp.json()["secure_url"] if resp.status_code == 200 else None
    except (requests.RequestException, ValueError, KeyError):
        secure_url = None
    # Deliberately generic: Cloudinary's own error text can name account details.
    if not secure_url:
        raise ApiError(BusinessCode.UPLOAD_FAILED, "image upload failed")
    return secure_url


def resolve_picture(value: Optional[str], public_id: str) -> Optional[str]:
    """What to store for a profile_picture the caller sent: the Cloudinary URL if it was a
    data URI, otherwise exactly what was sent (a URL, or None meaning "leave unchanged").
    """
    if is_data_uri(value):
        return upload_image(value, public_id)
    return value
