"""Email service for sending transactional emails.

In development mode (SMTP_HOST=localhost, SMTP_PORT=1025), emails are logged
to console. For production, configure SMTP_HOST/SMTP_PORT with real credentials.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    @staticmethod
    def _is_dev_mode() -> bool:
        return settings.SMTP_HOST in ("localhost", "127.0.0.1")

    @staticmethod
    async def send_password_reset(email_to: str, token: str, full_name: str | None = None) -> None:
        reset_link = f"http://localhost:5173/reset-password/{token}"
        name = full_name or email_to

        subject = "Reset your Learning Hub password"
        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: 'Inter', system-ui, sans-serif; max-width: 480px; margin: 0 auto; padding: 24px;">
  <div style="text-align: center; margin-bottom: 24px;">
    <div style="display: inline-block; width: 40px; height: 40px; background: linear-gradient(135deg, #6C5CE7, #A855F7); border-radius: 12px;"></div>
    <h2 style="margin: 8px 0 0; font-size: 18px; color: #1a1a2e;">Learning Hub</h2>
  </div>
  <h1 style="font-size: 22px; color: #1a1a2e;">Hi {name},</h1>
  <p style="color: #64748b; line-height: 1.6;">We received a request to reset your password. Click the button below to create a new one. This link expires in 30 minutes.</p>
  <div style="text-align: center; margin: 32px 0;">
    <a href="{reset_link}" style="display: inline-block; padding: 12px 32px; background: linear-gradient(135deg, #6C5CE7, #A855F7); color: white; text-decoration: none; border-radius: 12px; font-weight: 600; font-size: 15px;">Reset Password</a>
  </div>
  <p style="color: #64748b; font-size: 13px;">If you didn't request this, you can safely ignore this email.</p>
  <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;">
  <p style="color: #94a3b8; font-size: 12px; text-align: center;">Learning Hub AI Study Workspace</p>
</body>
</html>"""
        text = f"Reset your Learning Hub password\n\nHi {name},\n\nWe received a request to reset your password. Open the link below to create a new one. This link expires in 30 minutes.\n\n{reset_link}\n\nIf you didn't request this, you can safely ignore this email."

        await EmailService._send(email_to, subject, html, text)

    @staticmethod
    async def _send(to: str, subject: str, html: str, text: str) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.MAIL_FROM_NAME} <{settings.MAIL_FROM}>"
        msg["To"] = to
        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        if EmailService._is_dev_mode():
            logger.info("=== EMAIL (dev mode) ===")
            logger.info("To: %s", to)
            logger.info("Subject: %s", subject)
            logger.info("Text: %s", text)
            logger.info("========================")
            return

        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                if settings.SMTP_USE_TLS:
                    server.starttls()
                if settings.SMTP_USER:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.MAIL_FROM, to, msg.as_string())
            logger.info("Email sent to %s", to)
        except Exception as e:
            logger.error("Failed to send email to %s: %s", to, e)
            # In production, you might want to queue failed emails
