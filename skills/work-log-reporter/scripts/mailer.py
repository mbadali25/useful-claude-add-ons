"""SMTP delivery for work log reports.

Supports three transport shapes because they cover essentially every real
deployment: STARTTLS on 587 (most hosted providers), implicit SSL on 465, and
plain unauthenticated on 25 for an internal relay that authorises by IP.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

from wlconfig import WorkLogError, smtp_password


def build_message(cfg: dict, subject: str, html_body: str, text_body: str,
                  attachments: list[Path] | None = None) -> EmailMessage:
    email_cfg = cfg["email"]
    msg = EmailMessage()

    from_address = email_cfg.get("from_address")
    from_name = email_cfg.get("from_name") or ""
    msg["From"] = formataddr((from_name, from_address)) if from_name else from_address

    to = [a for a in (email_cfg.get("to") or []) if a]
    cc = [a for a in (email_cfg.get("cc") or []) if a]
    if not to:
        raise WorkLogError("email.to is empty — nowhere to send the report.")
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)

    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=from_address.split("@")[-1]
                                   if "@" in (from_address or "") else None)
    msg["X-Generated-By"] = "work-log-reporter"

    # Plain text first, HTML second: mail clients render the last part they
    # understand, so this order gives HTML clients the rich version and
    # text-only clients a readable fallback.
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    for path in attachments or []:
        path = Path(path)
        if not path.exists():
            continue
        subtype = "pdf" if path.suffix.lower() == ".pdf" else "octet-stream"
        msg.add_attachment(
            path.read_bytes(),
            maintype="application",
            subtype=subtype,
            filename=path.name,
        )
    return msg


def recipients(cfg: dict) -> list[str]:
    email_cfg = cfg["email"]
    return [a for a in (email_cfg.get("to") or []) + (email_cfg.get("cc") or []) if a]


def send(cfg: dict, msg: EmailMessage) -> str:
    smtp_cfg = cfg["smtp"]
    server = smtp_cfg["server"]
    port = int(smtp_cfg["port"])
    security = smtp_cfg.get("security", "starttls")
    timeout = int(smtp_cfg.get("timeout_seconds", 30))
    auth = smtp_cfg.get("auth", {})
    to_all = recipients(cfg)

    # Resolve the credential before dialing out. Otherwise a missing
    # environment variable surfaces as whatever the network happens to do
    # first, and the user chases a connection error that was never the problem.
    password = smtp_password(cfg) if auth.get("enabled", True) else None

    try:
        if security == "ssl":
            context = ssl.create_default_context()
            client = smtplib.SMTP_SSL(server, port, timeout=timeout, context=context)
        else:
            client = smtplib.SMTP(server, port, timeout=timeout)

        with client:
            client.ehlo()
            if security == "starttls":
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
            if auth.get("enabled", True):
                client.login(auth.get("username", ""), password or "")
            client.send_message(msg, to_addrs=to_all)

    except smtplib.SMTPAuthenticationError as exc:
        raise WorkLogError(
            f"SMTP rejected the login for {auth.get('username')}: {exc}\n"
            "Check the username and the value of "
            f"${auth.get('password_env', 'WORKLOG_SMTP_PASSWORD')}. "
            "Many providers require an app-specific password rather than the "
            "account password."
        ) from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise WorkLogError(
            f"Could not send via {server}:{port} ({security}): {exc}"
        ) from exc

    return ", ".join(to_all)
