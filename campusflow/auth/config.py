import os
import secrets
from dataclasses import dataclass
from urllib.parse import urlsplit

_development_secret = secrets.token_hex(32)


@dataclass(frozen=True)
class SecuritySettings:
    secret: str
    production: bool
    origins: tuple[str, ...]
    session_seconds: int = 8 * 3600
    idle_seconds: int = 30 * 60

    @property
    def cookie(self):
        return "__Host-campusflow" if self.production else "campusflow_session"


def settings():
    mode = os.getenv("CAMPUSFLOW_ENV", "development")
    if mode not in ("development", "production"):
        raise RuntimeError("CAMPUSFLOW_ENV must be development or production")
    production = mode == "production"
    secret = os.getenv("CAMPUSFLOW_SESSION_SECRET", "")
    if production and len(secret) < 32:
        raise RuntimeError("Production requires CAMPUSFLOW_SESSION_SECRET with at least 32 characters")
    origins = tuple(x.strip().rstrip("/") for x in os.getenv("CAMPUSFLOW_ALLOWED_ORIGINS", "").split(",") if x.strip())
    if not origins and not production:
        origins = tuple(f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (3000, 5173, 5174, 8000))
    if not origins:
        raise RuntimeError("Production requires explicit CAMPUSFLOW_ALLOWED_ORIGINS")
    for origin in origins:
        url = urlsplit(origin)
        if url.scheme not in ("http", "https") or not url.hostname or url.path or url.query or url.fragment or url.username:
            raise RuntimeError("Origins must be explicit HTTP(S) origins without paths or credentials")
        if production and url.scheme != "https":
            raise RuntimeError("Production origins must use HTTPS")
        if not production and url.hostname not in ("localhost", "127.0.0.1", "[::1]", "::1"):
            raise RuntimeError("Development origins must be loopback only")
    return SecuritySettings(secret or _development_secret, production, origins)
