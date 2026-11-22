"""Deny-by-default route policy and academic-scope checks."""
import re
from sqlalchemy import select
from campusflow.product import database as db
from campusflow.product.catalog import ProductError


def require_scope(user, scope):
    if user["role"] not in ("administrator", "teacher", "student") and scope not in user["scopes"]:
        raise ProductError("You do not have access to this academic scope.", 403)


def authorize(user, path, method):
    role = user["role"]
    read = method in ("GET", "HEAD")
    if path == "/api/onboarding/workspace" and method == "POST":
        return  # Endpoint atomically rejects any existing membership.
    if role == "unassigned":
        if path in ("/api/auth/session","/api/auth/logout","/api/auth/password"):
            return
        raise ProductError("Create a workspace or accept an institution invitation first.",403)
    if role == "platform_super_admin":
        if path in ("/api/auth/session", "/api/auth/logout", "/api/auth/password") or path.startswith("/api/platform/"):
            return
        raise ProductError("Platform operators cannot access institution academic data.",403)
    if role == "administrator":
        return
    if path.startswith("/api/auth/"):
        if path not in ("/api/auth/session", "/api/auth/logout", "/api/auth/password"):
            raise ProductError("Administrator access required.", 403)
        return
    if path == "/api/solvers" or path.startswith("/api/timetables/"):
        if role == "planner":
            return
    root = "/api/product"
    if role == "planner":
        if read and path in (root + "/catalog", root + "/settings"):
            return
        if re.fullmatch(root + r"/records/(faculty|subjects|rooms|batches|requirements|departments|academic_years)(/[^/]+)?", path):
            if read or "/records/requirements" in path:
                return
        if path == root + "/jobs":
            return
    if read and path == root + "/versions":
        return  # list endpoint filters by scope and publication state
    match = re.fullmatch(root + r"/(versions|jobs)/([^/]+)(?:/(.*))?", path)
    if match:
        kind, identifier, operation = match.groups()
        if role in ("viewer", "teacher", "student") and (kind != "versions" or not read or operation not in (None, "reports", "export/pdf", "export/csv")):
            raise ProductError("Viewers can only read authorized published timetables.", 403)
        table = db.versions if kind == "versions" else db.jobs
        with db.connection() as conn:
            row = conn.execute(select(table).where(table.c.id == identifier)).mappings().first()
        if not row:
            raise ProductError("Resource not found", 404)
        require_scope(user, row["scope"])
        if role in ("viewer", "teacher", "student") and row["state"] != "published":
            raise ProductError("Only published timetables are available to viewers.", 403)
        if role == "planner" and kind == "versions" and (operation in ("publish", "archive") or
                (method in ("PUT", "DELETE") and row["state"] not in ("draft", "generated"))):
            raise ProductError("Only administrators can publish or modify protected versions.", 403)
        return
    raise ProductError("You do not have permission to perform this action.", 403)
