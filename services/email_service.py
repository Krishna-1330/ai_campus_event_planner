"""Optional SMTP delivery for approved CampusFlow event assignments."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage


logger = logging.getLogger(__name__)


def send_email(config, recipient: str, subject: str, body: str) -> str:
    """Deliver one email without allowing SMTP errors to undo an approval."""
    recipient = str(recipient or "").strip()
    host = str(config.get("SMTP_HOST", "")).strip()
    sender = str(config.get("SMTP_FROM", "")).strip()
    if not recipient:
        return "skipped_missing_recipient"
    if not host or not sender:
        return "skipped_not_configured"

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(host, int(config.get("SMTP_PORT", 587)), timeout=10) as client:
            if config.get("SMTP_USE_TLS", True):
                client.starttls()
            username = str(config.get("SMTP_USERNAME", "")).strip()
            if username:
                client.login(username, str(config.get("SMTP_PASSWORD", "")))
            client.send_message(message)
    except (OSError, ValueError, smtplib.SMTPException):
        logger.exception("CampusFlow could not deliver an assignment email")
        return "failed"
    return "sent"
