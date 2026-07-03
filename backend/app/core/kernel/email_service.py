"""
app/core/kernel/email_service.py
Password reset email via SendGrid (optional — no-ops gracefully if
SENDGRID_API_KEY isn't configured).
"""

import os
from loguru import logger


async def send_email(to_email: str, subject: str, html_content: str) -> bool:
    api_key = os.getenv("SENDGRID_API_KEY", "")
    from_addr = os.getenv("SENDGRID_FROM_EMAIL", "noreply@resortos.local")
    if not api_key:
        logger.warning(f"[Email] SendGrid not configured — skipped: {subject} → {to_email}")
        return False
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail, Email, To, Content
        message = Mail(
            from_email=Email(from_addr),
            to_emails=To(to_email),
            subject=subject,
            html_content=Content("text/html", html_content),
        )
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        return response.status_code == 202
    except Exception as e:
        logger.error(f"[Email] SendGrid error: {e}")
        return False


async def send_password_reset_email(to_email: str, token: str, app_name: str = None) -> bool:
    name = app_name or os.getenv("APP_NAME", "Resort OS")
    app_url = os.getenv("APP_URL", "").rstrip("/")
    reset_url = f"{app_url}/reset-password?token={token}" if app_url else token
    html = f"""
    <html><body style="font-family:sans-serif;padding:32px">
    <h2>{name} — Password Reset</h2>
    <p>Click the link below to reset your password. Valid for 2 hours.</p>
    <a href="{reset_url}" style="background:#0ea5e9;color:#fff;padding:12px 24px;
       border-radius:6px;text-decoration:none;display:inline-block">Reset Password</a>
    <p style="margin-top:24px;color:#666;font-size:12px">
      If you didn't request this, ignore this email.
    </p>
    </body></html>
    """
    return await send_email(to_email, f"{name} — Password Reset", html)
