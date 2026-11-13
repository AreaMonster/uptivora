"""index check_rollups.bucket_start

The rollup job reads max(bucket_start) every 10 minutes, the retention job deletes by
bucket_start and the admin overview sums the last 24 hours. Without this index each of them
scans the whole table (up to ~100 million rows with 10,000 monitors and 400 days of history).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-13 15:00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_check_rollups_bucket_start", "check_rollups", ["bucket_start"])


def downgrade() -> None:
    op.drop_index("ix_check_rollups_bucket_start", table_name="check_rollups")
