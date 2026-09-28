"""Administer accounts on an install, from the host (ADR-101).

    docker compose exec api python -m pdm.platform.auth.cli list
    docker compose exec api python -m pdm.platform.auth.cli add <user> "<name>" <role>
    docker compose exec api python -m pdm.platform.auth.cli reset-password <user>
    docker compose exec api python -m pdm.platform.auth.cli set-role <user> <role>
    docker compose exec api python -m pdm.platform.auth.cli withdraw <user>

Roles: technician, supervisor, engineer, operator. A new or reset password is
generated and printed once; nothing here takes a password on the command line,
where it would stay in the shell history. Withdrawing keeps the person (closed
work orders and approvals name them) and ends their sessions at once.

A rehearsed demo leaves accounts whose passwords are in the repository
(`seed_demo.py --demo-passwords`). On any machine that will hold real work,
withdraw them: `withdraw tech-1 tech-2 tech-3 sup-1 eng-1 op-1`.
"""

from __future__ import annotations

import os
import secrets
import sys

from psycopg import connect

from pdm.contracts import Role, UserId
from pdm.platform.auth import repo
from pdm.platform.auth.domain import hash_password
from pdm.platform.clock import SystemClock


def _password() -> str:
    return secrets.token_urlsafe(12)


def main(argv: list[str]) -> int:
    url = os.environ.get("DATABASE_URL")
    if not url or not argv:
        print(__doc__)
        return 1
    command, *args = argv
    with connect(url) as conn:
        if command == "list":
            rows = conn.execute(
                "SELECT user_id, display_name, role, active FROM account ORDER BY user_id"
            ).fetchall()
            for user, name, role, active in rows:
                print(f"{user:12} {role:11} {'active' if active else 'withdrawn':9} {name}")
        elif command == "add" and len(args) == 3:
            user, name, role = args
            password = _password()
            repo.create_account(
                conn,
                user=UserId(user),
                display_name=name,
                role=Role(role),
                password=hash_password(password),
                now=SystemClock().now(),
            )
            print(f"{user} created; password (shown once): {password}")
        elif command == "reset-password" and len(args) == 1:
            password = _password()
            repo.set_password(conn, UserId(args[0]), hash_password(password))
            conn.execute("DELETE FROM session WHERE user_id = %s", (args[0],))
            print(f"{args[0]}: new password (shown once): {password}")
        elif command == "set-role" and len(args) == 2:
            repo.set_role(conn, UserId(args[0]), Role(args[1]))
            print(f"{args[0]} is now {args[1]}")
        elif command == "withdraw" and args:
            for user in args:
                repo.deactivate(conn, UserId(user))
                print(f"{user}: access withdrawn")
        else:
            print(__doc__)
            return 1
        conn.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
