"""Opaque, revocable sessions. Only keyed digests of session tokens are stored."""
import hashlib
import hmac
import secrets
import time
from uuid import uuid4

from argon2 import PasswordHasher, Type
from argon2.exceptions import VerificationError, InvalidHashError
from sqlalchemy import select, update, delete

from campusflow.product.catalog import ProductError, transaction
from campusflow.product.database import database
from .tables import users, sessions, attempts, memberships, profiles
from .onboarding_tables import institutions
from campusflow.tenancy import institution_id

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1, type=Type.ID)
_dummy_hash = hasher.hash(secrets.token_urlsafe(32))


def digest(config, value):
    return hmac.new(config.secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def csrf(config, token):
    return digest(config, "csrf:" + token)


def public_user(user):
    return {key: user.get(key) for key in ("id", "name", "username", "role", "scopes", "active", "must_change_password", "institution_id", "institution_name", "institution_type", "faculty_id", "batch_ids")}


def valid_password(password):
    if not 12 <= len(password) <= 128:
        raise ProductError("Passwords must contain 12–128 characters.")


def verify(stored, password):
    try:
        return hasher.verify(stored, password)
    except (VerificationError, InvalidHashError):
        return False


def create_user(conn, username, password, role="viewer", scopes=None, must_change=True, *, tenant=None, faculty_id=None, batch_ids=None):
    valid_password(password)
    import re
    username = username.strip().lower()
    if "@" in username:
        from .mail import normalize_email
        username = normalize_email(username)
    elif not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,63}", username):
        raise ProductError("Username must be 3–64 letters, digits, dots, underscores or hyphens.")
    if role not in ("administrator", "planner", "viewer", "teacher", "student", "platform_super_admin"):
        raise ProductError("Invalid user role")
    identifier = uuid4().hex
    conn.execute(users.insert().values(id=identifier, username=username, password_hash=hasher.hash(password),
        role=role if role in ("administrator", "planner", "viewer") else "viewer", scopes=scopes or [], active=1, must_change_password=int(must_change)))
    conn.execute(memberships.insert().values(user_id=identifier, institution_id=tenant or institution_id(), role=role, scopes=scopes or [], active=1, faculty_id=faculty_id, batch_ids=batch_ids or []))
    return member_user(conn, dict(conn.execute(select(users).where(users.c.id == identifier)).mappings().one()))


def issue(conn, config, user_id=None):
    token = secrets.token_urlsafe(32)
    now = time.time()
    lifetime = config.session_seconds if user_id else 1800
    conn.execute(sessions.insert().values(digest=digest(config, token), user_id=user_id,
        created_at=now, last_seen=now, expires_at=now + lifetime))
    return token


def resolve(config, token):
    if not token or len(token) > 128:
        return None, None
    now = time.time()
    with database().begin() as conn:
        session = conn.execute(select(sessions).where(sessions.c.digest == digest(config, token))).mappings().first()
        if not session or session["expires_at"] <= now or session["last_seen"] + config.idle_seconds <= now:
            return None, None
        user = conn.execute(select(users).where(users.c.id == session["user_id"], users.c.active == 1)).mappings().first() if session["user_id"] else None
        user = member_user(conn, dict(user)) if user else None
        if session["user_id"] and not user:
            return None, None
        if now - session["last_seen"] >= 60:
            conn.execute(update(sessions).where(sessions.c.digest == session["digest"]).values(last_seen=now))
        return dict(session), dict(user) if user else None


def revoke_user(conn, user_id):
    conn.execute(delete(sessions).where(sessions.c.user_id == user_id))


def reserve_attempt(config, username, ip, action="login"):
    """Reserve before hashing so concurrent requests cannot evade throttling."""
    now = time.time()
    keys = [(digest(config, f"{action}:account:{username.lower()}"), 5),
            (digest(config, f"{action}:ip:{ip}"), 30)]
    with transaction() as conn:
        conn.execute(delete(attempts).where(attempts.c.until <= now))
        for key, maximum in keys:
            row = conn.execute(select(attempts).where(attempts.c.key == key)).mappings().first()
            if row and row["count"] >= maximum:
                raise ProductError("Too many attempts. Try again in 15 minutes.", 429)
        for key, _ in keys:
            row = conn.execute(select(attempts).where(attempts.c.key == key)).mappings().first()
            if row:
                conn.execute(update(attempts).where(attempts.c.key == key).values(count=row["count"] + 1))
            else:
                conn.execute(attempts.insert().values(key=key, count=1, until=now + 900))


def authenticate(config, username, password, ip):
    username = username.strip().lower()
    reserve_attempt(config, username, ip)
    with database().connect() as conn:
        user = conn.execute(select(users).where(users.c.username == username)).mappings().first()
        user = member_user(conn, dict(user)) if user else None
    if not verify(user["password_hash"] if user else _dummy_hash, password) or not user or not user["active"]:
        raise ProductError("Invalid username or password.", 401)
    return dict(user)


def member_user(conn, user):
    member = conn.execute(select(memberships).where(memberships.c.user_id == user["id"])).mappings().first()
    profile=conn.execute(select(profiles).where(profiles.c.user_id==user["id"])).mappings().first()
    if not member:
        if not profile:
            return None
        return {**user, "name":profile["name"], "role":"unassigned", "scopes":[],
                "institution_id":None, "institution_name":None, "institution_type":None, "faculty_id":None, "batch_ids":[]}
    if not member["active"]:
        return None
    user={**user,"name":profile["name"] if profile else user["username"]}
    tenant = conn.execute(select(institutions).where(institutions.c.institution_id == member["institution_id"], institutions.c.status == "ACTIVE")).mappings().first()
    if not tenant:
        return None
    return {**user, **{key:member[key] for key in ("institution_id","role","scopes","faculty_id","batch_ids")},
            "institution_name":tenant["institution_name"], "institution_type":tenant["institution_type"]}
