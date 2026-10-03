"""Reusable OpenAPI 'responses' blocks for router route decorators.

FastAPI only auto-documents two things for these routes: 200 (with an EMPTY schema,
since every route returns a plain envelope dict rather than a typed response_model)
and 422 (from Pydantic body/path validation, via HTTPValidationError). Every other
status code a route can actually return — 401, 403, 404, 500, and the business-code
outcomes that still come back as HTTP 200 (wrong password, duplicate email, etc.) —
has to be declared here explicitly, or it never appears in /docs or openapi.json.

There is no 3xx response anywhere in this API: nothing here issues a redirect, so
none is documented — inventing one would misdescribe what the API actually does.

Usage in a router:
    @router.get("/{dog_id}", responses={**success(DOG_EXAMPLE), **UNAUTHORIZED,
                                         **FORBIDDEN, **DOG_NOT_FOUND, **SERVER_ERROR})
"""
from __future__ import annotations


def _body(code: str, message: str) -> dict:
    return {"code": code, "response": [{"message": message}]}


def success(body, description: str = "Success") -> dict:
    """One concrete 200 example — for routes with exactly one successful shape."""
    return {200: {"description": description, "content": {"application/json": {"example": body}}}}


def success_variants(*named_examples: tuple) -> dict:
    """A 200 entry with several NAMED examples — for routes where "success" (HTTP 200)
    covers more than one business-code outcome. named_examples is a list of
    (name, summary, body) tuples.
    """
    examples = {name: {"summary": summary, "value": body} for name, summary, body in named_examples}
    return {200: {
        "description": "200 covers both success and expected business-code outcomes — see examples",
        "content": {"application/json": {"examples": examples}},
    }}


UNAUTHORIZED = {401: {
    "description": "Missing, invalid, or expired bearer token",
    "content": {"application/json": {"example": _body("1000", "invalid or expired token")}},
}}

FORBIDDEN = {403: {
    "description": "Authenticated, but this resource belongs to someone else",
    "content": {"application/json": {"example": _body("2002", "not your dog")}},
}}

ADMIN_ONLY = {403: {
    "description": "Requires the admin role",
    "content": {"application/json": {"example": _body("2002", "requires admin role")}},
}}

DOG_NOT_FOUND = {404: {
    "description": "Dog does not exist (or was deleted)",
    "content": {"application/json": {"example": _body("2001", "dog not found")}},
}}

ASSESSMENT_NOT_FOUND = {404: {
    "description": "Assessment does not exist (or was deleted)",
    "content": {"application/json": {"example": _body("3001", "assessment not found")}},
}}

REPORT_NOT_FOUND = {404: {
    "description": "Report does not exist",
    "content": {"application/json": {"example": _body("4002", "report not found")}},
}}

REPORT_FILE_MISSING = {404: {
    "description": "Report exists but its PDF file is unset or missing on disk",
    "content": {"application/json": {"example": _body("4003", "report file missing on disk")}},
}}

REPORT_UNAVAILABLE = {503: {
    "description": "The PDF could not be rendered",
    "content": {"application/json": {"example": _body("4004", "the report could not be rendered")}},
}}

# Only relevant to routes that accept a profile_picture: when it is a base64 image data
# URI, the API uploads it to Cloudinary, which can fail in these three ways.
UPLOAD_ERRORS = {
    400: {
        "description": "profile_picture is not a valid base64 image data URI (jpeg/png/webp/heic, max 5 MB)",
        "content": {"application/json": {"example": _body("5003", "image must be a base64 jpeg/png/webp/heic data URI")}},
    },
    502: {
        "description": "Cloudinary was unreachable or rejected the image",
        "content": {"application/json": {"example": _body("5002", "image upload failed")}},
    },
    503: {
        "description": "Cloudinary credentials are not configured on this deployment",
        "content": {"application/json": {"example": _body("5001", "image uploads are not configured")}},
    },
}

EMAIL_SEND_FAILED = {502: {
    "description": "The email provider refused or couldn't deliver the message",
    "content": {"application/json": {"example": _body("1007", "we couldn't send the email right now")}},
}}

SERVER_ERROR = {500: {
    "description": "Unhandled server error",
    "content": {"application/json": {"example": _body("9000", "internal server error")}},
}}
