"""add followup columns to chats

Revision ID: 9f0a585859d4
Revises: b4d99314cd34
Create Date: 2026-04-07 01:26:02.039178
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9f0a585859d4"
down_revision: Union[str, None] = "b4d99314cd34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _chats_column_names() -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return {c["name"] for c in insp.get_columns("chats")}


def upgrade() -> None:
    cols = _chats_column_names()

    if "last_activity_at" not in cols:
        op.add_column(
            "chats",
            sa.Column(
                "last_activity_at",
                sa.DateTime(),
                nullable=True,
            ),
        )
    if "reminder_count" not in cols:
        op.add_column(
            "chats",
            sa.Column(
                "reminder_count",
                sa.Integer(),
                server_default="0",
                nullable=False,
            ),
        )
    if "last_reminder_at" not in cols:
        op.add_column(
            "chats",
            sa.Column(
                "last_reminder_at",
                sa.DateTime(),
                nullable=True,
            ),
        )
    if "current_step" not in cols:
        op.add_column(
            "chats",
            sa.Column(
                "current_step",
                sa.String(length=100),
                nullable=True,
            ),
        )

    op.execute(
        "UPDATE chats "
        "SET last_activity_at = started_at "
        "WHERE last_activity_at IS NULL"
    )


def downgrade() -> None:
    cols = _chats_column_names()
    if "current_step" in cols:
        op.drop_column("chats", "current_step")
    if "last_reminder_at" in cols:
        op.drop_column("chats", "last_reminder_at")
    if "reminder_count" in cols:
        op.drop_column("chats", "reminder_count")
    if "last_activity_at" in cols:
        op.drop_column("chats", "last_activity_at")
