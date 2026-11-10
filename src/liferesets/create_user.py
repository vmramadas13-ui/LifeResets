"""Create a local account from an interactive terminal prompt."""

from __future__ import annotations

import getpass
import sys

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select

from liferesets.database import SessionFactory
from liferesets.models import Profile, User
from liferesets.security import hash_password

MIN_PASSWORD_LENGTH = 15


def main() -> int:
    """Create a user without accepting passwords in command-line arguments."""
    try:
        email = str(
            TypeAdapter(EmailStr).validate_python(input("Email: ").strip())
        ).casefold()
    except ValidationError:
        print("Enter a valid email address.", file=sys.stderr)
        return 1

    password = getpass.getpass("Password (15 characters minimum): ")
    confirmation = getpass.getpass("Confirm password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print("Password must be at least 15 characters.", file=sys.stderr)
        return 1
    if len(password) > 1024:
        print("Password must be at most 1024 characters.", file=sys.stderr)
        return 1
    if password != confirmation:
        print("Passwords do not match.", file=sys.stderr)
        return 1

    with SessionFactory() as db:
        if db.scalar(select(User.id).where(User.email == email)) is not None:
            print("An account with that email already exists.", file=sys.stderr)
            return 1

        user = User(email=email, password_hash=hash_password(password))
        user.profile = Profile(timezone="UTC")
        db.add(user)
        db.commit()

    print("Local account created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
