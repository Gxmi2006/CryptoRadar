from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any


class EmailNotifier:
    def __init__(self, config: dict[str, Any]):
        email_cfg = config.get("email", {})
        self.user = os.getenv(email_cfg.get("user_env", "EMAIL_USER"), "")
        self.password = os.getenv(email_cfg.get("password_env", "EMAIL_PASSWORD"), "")
        self.to = email_cfg.get("to", "")
        self.host = email_cfg.get("smtp_host", "smtp.gmail.com")
        self.port = int(email_cfg.get("smtp_port", 587))

    def send(self, subject: str, message: str) -> bool:
        if not (self.user and self.password and self.to):
            return False
        email = EmailMessage()
        email["From"] = self.user
        email["To"] = self.to
        email["Subject"] = subject
        email.set_content(message)
        with smtplib.SMTP(self.host, self.port, timeout=12) as smtp:
            smtp.starttls()
            smtp.login(self.user, self.password)
            smtp.send_message(email)
        return True
