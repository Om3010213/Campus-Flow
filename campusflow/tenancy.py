"""Trusted institution context and fail-closed academic SQL boundary.

HTTP middleware supplies this context from the authenticated membership. It is
never populated from request headers, URL parameters or JSON.
"""
from contextvars import ContextVar
from contextlib import contextmanager
from sqlalchemy.sql import Select, Insert, Update, Delete

LEGACY = "00000000-0000-0000-0000-000000000001"
# Direct library/maintenance callers retain the legacy workspace. HTTP resets it.
institution_context = ContextVar("institution_context", default=LEGACY)


def institution_id():
    value = institution_context.get()
    if not value:
        raise PermissionError("Institution context is required")
    return value


@contextmanager
def institution(value):
    token = institution_context.set(value)
    try:
        yield
    finally:
        institution_context.reset(token)


class AcademicConnection:
    """Scopes every academic statement at execution, including aggregates.

    Global authentication/registration tables are deliberately not tenant tables.
    Raw SQL belongs only in explicit migration/maintenance code, not this boundary.
    """
    def __init__(self, connection):
        self.connection = connection

    def execute(self, statement, parameters=None):
        from campusflow.product.database import TENANT_TABLES
        if isinstance(statement, Select):
            tables = []
            def collect(source):
                if hasattr(source, "left") and hasattr(source, "right"):
                    collect(source.left); collect(source.right)
                elif getattr(source, "name", None) in TENANT_TABLES:
                    tables.append(source)
                elif getattr(getattr(source, "original", None), "name", None) in TENANT_TABLES:
                    tables.append(source)
            for source in statement.get_final_froms():
                collect(source)
            # Reject nested academic subqueries until they can be scoped recursively.
            # This prevents a future aggregate/EXISTS query silently bypassing tenancy.
            from sqlalchemy.sql import visitors
            for nested in visitors.iterate(statement):
                if isinstance(nested, Select) and nested is not statement:
                    if any(getattr(node, "name", None) in TENANT_TABLES for node in visitors.iterate(nested)):
                        raise TypeError("Nested academic queries require an explicit scoped query")
            for table in tables:
                statement = statement.where(table.c.institution_id == institution_id())
        elif isinstance(statement, (Update, Delete, Insert)):
            table = statement.table
            if table.name in TENANT_TABLES:
                tenant = institution_id()
                if isinstance(statement, Insert):
                    if parameters is not None:
                        raise ValueError("Parameterized academic inserts must use explicit values")
                    statement = statement.values(institution_id=tenant)
                else:
                    statement = statement.where(table.c.institution_id == tenant)
                    if isinstance(statement, Update) and any(getattr(k, "name", k) == "institution_id" for k in statement._values or {}):
                        raise ValueError("An academic record cannot change institution")
        else:
            raise TypeError("Academic connections accept structured SQL only")
        return self.connection.execute(statement, parameters or {})

    def exec_driver_sql(self, statement):
        if statement != "BEGIN IMMEDIATE":
            raise TypeError("Raw academic SQL is not permitted")
        return self.connection.exec_driver_sql(statement)
