"""HTML email bodies. Table layout + inline CSS only: email clients ignore <style>/flex/grid,
and many drop CSS gradients, so every gradient has a solid `bgcolor` fallback. Designed from
the Figma "Pawsitivity · Username recovery email" frame (600px wide).
"""
from __future__ import annotations

from html import escape

from ..config import get_settings

_FONT = "Inter,-apple-system,'Segoe UI',Helvetica,Arial,sans-serif"
_INK = "#172033"
_MUTED = "#65738a"
_BLUE = "#2368d8"
SUPPORT_EMAIL = "support@pawsitivity.app"


def _logo_img() -> str:
    logo_url = get_settings().email_logo_url
    return (
        f'<img src="{escape(logo_url, quote=True)}" width="56" height="54" alt="" '
        'style="display:block;border:0;border-radius:13px;">'
        if logo_url else ""
    )


def _brand_header(logo: str) -> str:
    return f"""  <!-- Brand header -->
  <tr><td bgcolor="#e8f2ff" style="background-color:#e8f2ff;background-image:linear-gradient(90deg,#f5f9ff 0%,#e8f2ff 55%,#d8e9ff 100%);padding:32px 40px;">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
      <td style="padding-right:12px;" valign="middle">{logo}</td>
      <td valign="middle" style="font-family:{_FONT};font-size:22px;font-weight:600;color:{_INK};">Pawsitivity</td>
    </tr></table>
  </td></tr>"""

def username_recovery_email(username: str, email: str) -> str:
    logo = _logo_img()
    username = escape(username)
    email = escape(email)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<title>Your Pawsitivity username</title>
</head>
<body style="margin:0;padding:0;background:#ffffff;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff;">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;font-family:{_FONT};">

{_brand_header(logo)}
  <!-- Recovery message -->
  <tr><td style="padding:40px 40px 0 40px;">
    <h1 style="margin:0 0 12px 0;font-family:{_FONT};font-size:30px;line-height:1.2;font-weight:700;color:{_INK};">Your username, recovered.</h1>
    <p style="margin:0;font-family:{_FONT};font-size:16px;line-height:1.55;color:{_MUTED};">As requested, here&rsquo;s the Pawsitivity username associated with your email address.</p>
  </td></tr>

  <!-- Account details card -->
  <tr><td style="padding:32px 40px 0 40px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr><td bgcolor="#eef5ff" style="background-color:#eef5ff;background-image:linear-gradient(90deg,#f5f9ff,#e8f2ff);border:1px solid #d8e7fc;border-radius:20px;padding:24px;">
        <div style="font-family:{_FONT};font-size:14px;font-weight:500;line-height:1.3;color:{_MUTED};margin:0 0 8px 0;">Your username</div>
        <div style="font-family:{_FONT};font-size:28px;line-height:1.2;color:{_BLUE};margin:0 0 16px 0;word-break:break-word;">{username}</div>
        <div style="font-family:{_FONT};font-size:12px;line-height:1.3;color:{_MUTED};margin:0 0 4px 0;">Email address</div>
        <div style="font-family:{_FONT};font-size:14px;line-height:1.4;color:{_INK};word-break:break-word;">{email}</div>
      </td></tr>
    </table>
  </td></tr>

  <!-- Assistance -->
  <tr><td style="padding:32px 40px 32px 40px;">
    <p style="margin:0 0 16px 0;font-family:{_FONT};font-size:14px;line-height:1.55;color:{_MUTED};">If you didn&rsquo;t request this, you can safely ignore this email.</p>
    <p style="margin:0 0 4px 0;font-family:{_FONT};font-size:14px;line-height:1.5;color:{_MUTED};">Need a hand? We&rsquo;re here to help.</p>
    <a href="mailto:{SUPPORT_EMAIL}" style="font-family:{_FONT};font-size:14px;line-height:1.5;font-weight:500;color:{_BLUE};text-decoration:none;">{SUPPORT_EMAIL}</a>
  </td></tr>

  <!-- Transactional footer -->
  <tr><td style="padding:0 40px 32px 40px;">
    <div style="border-top:1px solid #d8e7fc;font-size:0;line-height:0;height:1px;margin:0 0 24px 0;">&nbsp;</div>
    <p style="margin:0 0 12px 0;font-family:{_FONT};font-size:12px;line-height:1.5;color:{_MUTED};">You&rsquo;re receiving this email because a username reminder was requested for your Pawsitivity account.</p>
    <p style="margin:0 0 12px 0;font-family:{_FONT};font-size:12px;line-height:1.3;color:{_MUTED};">Privacy Policy &nbsp;&nbsp; Terms of Service</p>
    <p style="margin:0;font-family:{_FONT};font-size:12px;line-height:1.5;color:{_MUTED};">&copy; Pawsitivity</p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>
"""


def password_reset_otp_email(code: str) -> str:
    code = escape(code)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<title>Your Pawsitivity verification code</title>
</head>
<body style="margin:0;padding:0;background:#ffffff;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff;">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;font-family:{_FONT};">

{_brand_header(_logo_img())}
  <!-- Title -->
  <tr><td align="center" style="padding:64px 40px 40px 40px;">
    <h1 style="margin:0;font-family:{_FONT};font-size:40px;line-height:1.2;font-weight:700;color:#000000;text-align:center;">OTP</h1>
  </td></tr>

  <!-- Code card -->
  <tr><td style="padding:0 40px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr><td align="center" bgcolor="#d8e7fc" style="background-color:#d8e7fc;border-radius:20px;padding:40px 24px;">
        <div style="font-family:{_FONT};font-size:16px;font-weight:500;line-height:1.5;color:#2b3039;margin:0 0 32px 0;">Here is your Password Reset Code</div>
        <div style="font-family:{_FONT};font-size:32px;font-weight:500;line-height:1.5;letter-spacing:10px;color:#2b3039;margin:0 0 24px 0;padding-left:10px;">{code}</div>
        <div style="font-family:{_FONT};font-size:11px;font-weight:500;line-height:1.5;color:#7a7f87;margin:0;">This code will expire soon</div>
      </td></tr>
    </table>
  </td></tr>

  <!-- Assistance -->
  <tr><td align="center" style="padding:40px 40px 64px 40px;">
    <p style="margin:0 0 16px 0;font-family:{_FONT};font-size:14px;line-height:1.55;color:{_MUTED};text-align:center;">If you didn&rsquo;t request this, you can safely ignore this email.</p>
    <p style="margin:0 0 16px 0;font-family:{_FONT};font-size:14px;line-height:1.5;color:{_MUTED};text-align:center;">Need a hand? We&rsquo;re here to help.</p>
    <a href="mailto:{SUPPORT_EMAIL}" style="font-family:{_FONT};font-size:14px;line-height:1.5;font-weight:500;color:{_BLUE};text-decoration:underline;">{SUPPORT_EMAIL}</a>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>
"""
