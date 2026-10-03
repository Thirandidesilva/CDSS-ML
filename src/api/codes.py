"""Business-code enum for the {"code","response"} envelope — routers reference these, never bare strings."""
from __future__ import annotations

from enum import Enum


class BusinessCode(str, Enum):
    SUCCESS = "0000"

    # 1xxx = auth/user domain
    MISSING_OR_INVALID_TOKEN = "1000"
    INVALID_CREDENTIALS = "1001"
    DUPLICATE_EMAIL = "1002"
    ACCOUNT_NOT_FOUND = "1003"
    INVALID_RESET_TOKEN = "1004"
    DUPLICATE_USERNAME = "1005"
    OTP_INVALID = "1006"  # wrong code, expired, or attempts exhausted — never distinguished
    EMAIL_SEND_FAILED = "1007"  # the email provider refused or couldn't deliver the message

    # 2xxx = dog domain
    DOG_NOT_FOUND = "2001"
    OWNERSHIP_VIOLATION = "2002"  # reused for assessment/report ownership too

    # 3xxx = assessment domain
    ASSESSMENT_NOT_FOUND = "3001"

    # 4xxx = report domain
    REPORT_NOT_READY = "4001"
    REPORT_NOT_FOUND = "4002"
    REPORT_FILE_MISSING = "4003"  # retired: PDFs are rendered on demand, so there is no file to go missing
    REPORT_UNAVAILABLE = "4004"   # the PDF could not be rendered

    # 5xxx = image upload domain
    UPLOAD_NOT_CONFIGURED = "5001"  # Cloudinary credentials are not set on this deployment
    UPLOAD_FAILED = "5002"          # Cloudinary was unreachable or rejected the image
    INVALID_IMAGE = "5003"          # not a base64 image data URI, wrong type, or too large

    # 9xxx = anything unhandled
    SERVER_ERROR = "9000"


# HTTP status paired with each code where the code implies a fixed transport-layer
# outcome. Codes not listed here are business outcomes returned with HTTP 200 — e.g.
# "wrong password" is a normal, well-formed request that just didn't succeed, so it
# stays 200 with code "1001" rather than a 401.
HTTP_STATUS = {
    BusinessCode.MISSING_OR_INVALID_TOKEN: 401,
    BusinessCode.DOG_NOT_FOUND: 404,
    BusinessCode.EMAIL_SEND_FAILED: 502,
    BusinessCode.OWNERSHIP_VIOLATION: 403,
    BusinessCode.ASSESSMENT_NOT_FOUND: 404,
    BusinessCode.REPORT_NOT_FOUND: 404,
    BusinessCode.REPORT_FILE_MISSING: 404,
    BusinessCode.REPORT_UNAVAILABLE: 503,
    BusinessCode.INVALID_IMAGE: 400,
    BusinessCode.UPLOAD_FAILED: 502,
    BusinessCode.UPLOAD_NOT_CONFIGURED: 503,
    BusinessCode.SERVER_ERROR: 500,
}
