"""Configurable SMTP delivery; no credentials or verification links are logged."""
import os
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from urllib.parse import urlsplit

from campusflow.product.catalog import ProductError


def normalize_email(value: str) -> str:
    value = value.strip().lower()
    # Deliberately support ordinary ASCII mailboxes, not display names or SMTPUTF8.
    if len(value) > 254 or not re.fullmatch(r"[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+", value):
        raise ValueError("Enter a valid email address")
    local, domain = value.rsplit("@", 1)
    if len(local) > 64 or any(len(label) > 63 for label in domain.split(".")):
        raise ValueError("Enter a valid email address")
    return value


@dataclass(frozen=True)
class MailConfig:
    host: str
    port: int
    sender: str
    username: str
    password: str
    tls: str
    public_url: str


def configuration(production: bool) -> MailConfig:
    try:
        if os.getenv("CAMPUSFLOW_EMAIL_PROVIDER") != "smtp":
            raise ValueError("SMTP provider required")
        host = os.environ["CAMPUSFLOW_SMTP_HOST"]
        port = int(os.getenv("CAMPUSFLOW_SMTP_PORT", "587"))
        sender = normalize_email(os.environ["CAMPUSFLOW_EMAIL_FROM"])
        username = os.getenv("CAMPUSFLOW_SMTP_USERNAME", "")
        password = os.getenv("CAMPUSFLOW_SMTP_PASSWORD", "")
        tls = os.getenv("CAMPUSFLOW_SMTP_TLS", "starttls")
        public_url = os.environ["CAMPUSFLOW_PUBLIC_URL"].rstrip("/")
        url = urlsplit(public_url)
        if not host or not 1 <= port <= 65535 or tls not in ("starttls", "ssl", "none"):
            raise ValueError("Invalid transport")
        if bool(username) != bool(password):
            raise ValueError("Incomplete SMTP credentials")
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.path or url.query or url.fragment:
            raise ValueError("Invalid public origin")
        if not public_url.isascii() or len(public_url) > 900:
            raise ValueError("Public origin must be ASCII (use punycode) and fit one SMTP line")
        if url.scheme != "https" and (production or url.hostname not in ("localhost", "127.0.0.1", "::1")):
            raise ValueError("HTTPS required")
        if tls == "none" and (production or host not in ("localhost", "127.0.0.1", "::1") or username):
            raise ValueError("Plain SMTP is only allowed for a local test receiver without credentials")
        return MailConfig(host, port, sender, username, password, tls, public_url)
    except (KeyError, ValueError):
        raise ProductError("Email delivery is not configured. Contact the operator.", 503) from None


def send_verification(config: MailConfig, recipient: str, token: str, *, invitation=False) -> None:
    message = EmailMessage()
    message["From"], message["To"] = config.sender, recipient
    message["Subject"] = "Your CampusFlow institution invitation" if invitation else "Verify your CampusFlow registration"
    # A fragment avoids sending the token in HTTP request URLs and access logs.
    link = f"{config.public_url}/{'accept-invitation' if invitation else 'verify-email'}#token={token}"
    message.set_content(
    "Accept your CampusFlow invitation within 72 hours and set your own password:\n\n"
    + link + "\nIf unexpected, ignore this message." if invitation else
    "Verify your CampusFlow registration within 30 minutes:\n\n" + link +
    "\n\nEnter the password you chose when registering. This link is single-use. "
    "Verification creates your new institution workspace. "
    "If you did not register, ignore this message. No existing institution access is granted.\n",
    cte="7bit")
    try:
        context = ssl.create_default_context()
        transport = smtplib.SMTP_SSL if config.tls == "ssl" else smtplib.SMTP
        kwargs = {"context": context} if config.tls == "ssl" else {}
        with transport(config.host, config.port, timeout=10, **kwargs) as smtp:
            if config.tls == "starttls":
                smtp.starttls(context=context)
            if config.username:
                smtp.login(config.username, config.password)
            refused = smtp.send_message(message)
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
    except (OSError, smtplib.SMTPException):
        raise ProductError("Email could not be submitted. Try again later using resend verification.", 503) from None
