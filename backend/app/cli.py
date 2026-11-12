"""Operator command line.

  python -m app.cli migrate
  python -m app.cli create-user --email a@b.ch --password '...' [--admin] [--plan pro]

``--plan`` creates a TEST-MODE subscription (no payment) and is refused in production.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.auth.service import create_user, get_user_by_email
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.core.security import PasswordPolicyError, check_password_policy
from app.models import Plan, Subscription, SubscriptionStatus, UserRole


def cmd_migrate(_: argparse.Namespace) -> None:
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "head")


async def _create_user(args: argparse.Namespace) -> None:
    settings = get_settings()
    password = args.password or getpass.getpass("Password: ")
    try:
        check_password_policy(password, email=args.email)
    except PasswordPolicyError as exc:
        raise SystemExit(str(exc)) from exc
    if args.plan and settings.is_production:
        raise SystemExit("--plan creates a test subscription and is not allowed in production")
    async with get_sessionmaker()() as db:
        if await get_user_by_email(db, args.email):
            raise SystemExit(f"User {args.email} already exists")
        user = await create_user(
            db,
            email=args.email,
            password=password,
            full_name=args.name or "",
            role=UserRole.ADMIN if args.admin else UserRole.USER,
        )
        user.email_verified_at = datetime.now(UTC)
        if args.plan:
            plan = await db.scalar(select(Plan).where(Plan.code == args.plan))
            if plan is None:
                raise SystemExit(f"Unknown plan {args.plan}")
            now = datetime.now(UTC)
            db.add(
                Subscription(
                    user_id=user.id,
                    plan_id=plan.id,
                    status=SubscriptionStatus.ACTIVE,
                    current_period_start=now,
                    current_period_end=now + timedelta(days=30),
                    provider="test",
                    is_test=True,
                )
            )
        await db.commit()
        print(
            f"Created {'admin' if args.admin else 'user'} {user.email}"
            + (f" with TEST subscription '{args.plan}'" if args.plan else "")
        )
    await get_engine().dispose()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="uptivora")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="apply database migrations").set_defaults(func=cmd_migrate)
    p = sub.add_parser("create-user", help="create a user account")
    p.add_argument("--email", required=True)
    p.add_argument("--password")
    p.add_argument("--name")
    p.add_argument("--admin", action="store_true")
    p.add_argument("--plan", help="attach a TEST subscription (non-production only)")
    p.set_defaults(func=lambda a: asyncio.run(_create_user(a)))
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
