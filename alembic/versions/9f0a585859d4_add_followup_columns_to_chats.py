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


def upgrade() -> None:
    op.add_column(
        "chats",
        sa.Column(
            "last_activity_at",
            sa.DateTime(),
            nullable=True,
        ),
    )
    op.add_column(
        "chats",
        sa.Column(
            "reminder_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "chats",
        sa.Column(
            "last_reminder_at",
            sa.DateTime(),
            nullable=True,
        ),
    )
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
    op.drop_column("chats", "current_step")
    op.drop_column("chats", "last_reminder_at")
    op.drop_column("chats", "reminder_count")
    op.drop_column("chats", "last_activity_at")
