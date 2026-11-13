"""worker_heartbeats.network_held

Set by a worker while it holds back outage alerts because its own network is down
(see app.engine.netwatch); shown in the admin health view and the service health endpoint.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-13 21:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "worker_heartbeats",
        sa.Column("network_held", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("worker_heartbeats", "network_held")
