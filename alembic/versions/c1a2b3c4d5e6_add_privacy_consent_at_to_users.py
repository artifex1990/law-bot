"""add privacy_consent_at to users

Revision ID: c1a2b3c4d5e6
Revises: 9f0a585859d4
Create Date: 2026-04-07

"""
# pylint: disable=no-member
# op.add_column / op.drop_column подставляются Alembic динамически

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1a2b3c4d5e6"
down_revision: Union[str, None] = "9f0a585859d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(  # type: ignore[attr-defined]
        "users",
        sa.Column("privacy_consent_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "privacy_consent_at")  # type: ignore[attr-defined]
