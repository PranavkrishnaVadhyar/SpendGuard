"""Explicit SMTP delivery of the durable notification outbox."""

from dataclasses import dataclass, field
from email.message import EmailMessage
import os
import smtplib
import ssl

from spendguard import db


@dataclass
class EmailSettings:
    host: str
    port: int
    sender: str
    recipient: str
    username: str = ""
    password: str = field(default="", repr=False)
    security: str = "starttls"

    def __post_init__(self):
        for value in (self.host, self.sender, self.recipient):
            if not isinstance(value, str) or not value.strip() or '\n' in value or '\r' in value:
                raise ValueError("invalid SMTP host or address")
        if isinstance(self.port, bool) or not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise ValueError("invalid SMTP port")
        if self.security not in {"starttls", "ssl"}:
            raise ValueError("SMTP security must be starttls or ssl")
        if bool(self.username) != bool(self.password):
            raise ValueError("SMTP username and password must both be set or both empty")

    @classmethod
    def from_env(cls):
        return cls(os.getenv('SPENDGUARD_SMTP_HOST', ''), int(os.getenv('SPENDGUARD_SMTP_PORT', '587')),
                   os.getenv('SPENDGUARD_SMTP_FROM', ''), os.getenv('SPENDGUARD_SMTP_TO', ''),
                   os.getenv('SPENDGUARD_SMTP_USERNAME', ''), os.getenv('SPENDGUARD_SMTP_PASSWORD', ''),
                   os.getenv('SPENDGUARD_SMTP_SECURITY', 'starttls'))


def send_pending(db_path, settings, limit=20):
    if not isinstance(settings, EmailSettings):
        raise ValueError("settings must be EmailSettings")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("email batch limit must be between 1 and 100")
    with db.connection(db_path) as conn:
        ids = [row[0] for row in conn.execute("""SELECT id FROM notifications
            WHERE status IN ('queued','failed') ORDER BY id LIMIT ?""", (limit,))]
    sent = failed = 0
    for notification_id in ids:
        with db.transaction(db_path) as conn:
            cursor = conn.execute("""UPDATE notifications SET status='sending',attempts=attempts+1,error_type=NULL
                WHERE id=? AND status IN ('queued','failed')""", (notification_id,))
            if not cursor.rowcount:
                continue
            row = conn.execute("SELECT * FROM notifications WHERE id=?", (notification_id,)).fetchone()
        error_type = None
        try:
            message = EmailMessage()
            message['From'], message['To'] = settings.sender, settings.recipient
            message['Subject'] = 'SpendGuard notification'
            message.set_content(row['message'])
            factory = smtplib.SMTP_SSL if settings.security == 'ssl' else smtplib.SMTP
            options = {"context": ssl.create_default_context()} if settings.security == 'ssl' else {}
            with factory(settings.host, settings.port, timeout=10, **options) as client:
                if settings.security == 'starttls':
                    client.starttls(context=ssl.create_default_context())
                if settings.username:
                    client.login(settings.username, settings.password)
                if client.send_message(message):
                    raise smtplib.SMTPRecipientsRefused("recipient refused")
        except Exception as exc:
            error_type = type(exc).__name__
        with db.transaction(db_path) as conn:
            conn.execute("UPDATE notifications SET status=?,error_type=?,sent_at=? WHERE id=?",
                         ('failed' if error_type else 'sent', error_type, None if error_type else db.now(), notification_id))
        failed += error_type is not None
        sent += error_type is None
    return {"sent": sent, "failed": failed}
