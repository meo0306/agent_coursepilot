"""initial CoursePilot base

Revision ID: 0001_initial_coursepilot_base
Revises:
Create Date: 2026-06-20 00:01:00
"""

from collections.abc import Sequence

revision: str = "0001_initial_coursepilot_base"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

