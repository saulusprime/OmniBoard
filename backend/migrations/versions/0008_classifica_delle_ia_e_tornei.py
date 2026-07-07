"""classifica delle IA e tornei

Revisione: 0008
Precedente: 0007
Creata il: 2026-07-07 19:52:46.734650
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_ratings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("identity", sa.String(), nullable=False),
        sa.Column("elo", sa.Float(), nullable=False),
        sa.Column("wins", sa.Integer(), nullable=False),
        sa.Column("draws", sa.Integer(), nullable=False),
        sa.Column("losses", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "identity", name="uq_game_identity"),
    )
    op.create_table(
        "tournaments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("double_round", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "tournament_games",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tournament_id", sa.Integer(), nullable=False),
        sa.Column("x_identity", sa.String(), nullable=False),
        sa.Column("o_identity", sa.String(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("result", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["game_sessions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tournament_id"],
            ["tournaments.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("tournament_games")
    op.drop_table("tournaments")
    op.drop_table("ai_ratings")
