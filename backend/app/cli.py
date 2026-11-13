"""Operator command line.

  python -m app.cli migrate
  python -m app.cli preflight [--smtp]
  python -m app.cli reissue-licences [--from-key-id OLD]
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


def cmd_preflight(args: argparse.Namespace) -> None:
    from app.preflight import render, run_checks

    async def run() -> list:
        try:
            return await run_checks(get_settings(), smtp=args.smtp)
        finally:
            await get_engine().dispose()

    results = asyncio.run(run())
    print(render(results))
    if any(r.level == "FAIL" for r in results):
        raise SystemExit(1)


def cmd_reissue(args: argparse.Namespace) -> None:
    from app.billing.licences import reissue_licences

    async def run() -> tuple[int, int]:
        try:
            return await reissue_licences(
                get_sessionmaker(), get_settings(), from_key_id=args.from_key_id
            )
        finally:
            await get_engine().dispose()

    done, failed = asyncio.run(run())
    print(f"Re-issued {done} licence(s); {failed} failed (see the log).")
    if failed:
        raise SystemExit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="uptivora")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="apply database migrations").set_defaults(func=cmd_migrate)
    pf = sub.add_parser("preflight", help="check that this installation is ready for production")
    pf.add_argument("--smtp", action="store_true", help="also log in to the SMTP server")
    pf.set_defaults(func=cmd_preflight)
    ri = sub.add_parser(
        "reissue-licences",
        help="after a signing-key rotation: re-sign and email every sold licence",
    )
    ri.add_argument("--from-key-id", help="only licences signed with this key id")
    ri.set_defaults(func=cmd_reissue)
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
