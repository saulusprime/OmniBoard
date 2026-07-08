"""sistema puzzle

Revisione: 0010
Precedente: 0009
Creata il: 2026-07-08 20:59:21.426047
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "puzzles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("fen", sa.String(), nullable=False),
        sa.Column("solution_json", sa.String(), nullable=False),
        sa.Column("theme", sa.String(), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_session_id", sa.Integer(), nullable=True),
        sa.Column("source_ply", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_session_id"],
            ["game_sessions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_session_id", "source_ply", name="uq_puzzle_origin"),
    )
    op.create_table(
        "puzzle_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("puzzle_id", sa.Integer(), nullable=False),
        sa.Column("solved", sa.Boolean(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["puzzle_id"],
            ["puzzles.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "puzzle_id", name="uq_user_puzzle"),
    )


def downgrade() -> None:
    op.drop_table("puzzle_attempts")
    op.drop_table("puzzles")
