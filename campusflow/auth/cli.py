"""Secure local provisioning/recovery; passwords are never command arguments."""
import argparse
from getpass import getpass
from sqlalchemy import select, update

from campusflow.product.database import migrate
from campusflow.product.catalog import transaction, ProductError
from .tables import users
from .service import create_user, hasher, valid_password, revoke_user


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create-admin", "create-platform-admin", "reset-password"])
    parser.add_argument("username")
    args = parser.parse_args()
    password = getpass("Password (12–128 characters): ")
    if password != getpass("Confirm password: "):
        parser.error("Passwords do not match")
    try:
        valid_password(password)
        migrate()
        with transaction() as conn:
            if args.action == "create-platform-admin":
                create_user(conn, args.username, password, "platform_super_admin", [], must_change=False)
            elif args.action == "create-admin":
                if conn.execute(select(users.c.id).where(users.c.role == "administrator")).first():
                    raise ProductError("An administrator already exists. Use the authenticated user-management page.")
                create_user(conn, args.username, password, "administrator", must_change=False)
            else:
                user = conn.execute(select(users).where(users.c.username == args.username.strip().lower())).mappings().first()
                if not user:
                    raise ProductError("User not found")
                conn.execute(update(users).where(users.c.id == user["id"]).values(password_hash=hasher.hash(password), must_change_password=1))
                revoke_user(conn, user["id"])
        print("Administrator created." if args.action.startswith("create-") else "Password reset; all sessions revoked. User must change this temporary password at login.")
    except ProductError as exc:
        parser.error(exc.message)


if __name__ == "__main__":
    main()
