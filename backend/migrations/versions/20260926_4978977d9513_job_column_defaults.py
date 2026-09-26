"""job column defaults

Revision ID: 4978977d9513
Revises: 5510e6e5838b
Create Date: 2026-09-26 19:02:02.051626
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '4978977d9513'
down_revision: str | None = '5510e6e5838b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("jobs", "status", server_default="queued")
    op.alter_column("jobs", "attempts", server_default="0")
    op.alter_column("jobs", "payload", server_default="{}")


def downgrade() -> None:
    for column in ("status", "attempts", "payload"):
        op.alter_column("jobs", column, server_default=None)
