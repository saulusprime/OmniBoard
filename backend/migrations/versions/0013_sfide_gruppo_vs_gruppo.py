"""sfide gruppo-vs-gruppo (squadre a tavoliere multiplo)

Revisione: 0013
Precedente: 0012
Creata il: 2026-07-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "group_matches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("challenger_group_id", sa.Integer(), nullable=False),
        sa.Column("opponent_group_id", sa.Integer(), nullable=False),
        sa.Column("boards", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("winner_group_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
        ),
        sa.ForeignKeyConstraint(
            ["challenger_group_id"],
            ["groups.id"],
        ),
        sa.ForeignKeyConstraint(
            ["opponent_group_id"],
            ["groups.id"],
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["winner_group_id"],
            ["groups.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "group_match_boards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("board", sa.Integer(), nullable=False),
        sa.Column("x_user_id", sa.Integer(), nullable=False),
        sa.Column("o_user_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("result", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["group_matches.id"],
        ),
        sa.ForeignKeyConstraint(
            ["x_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["o_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["game_sessions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("group_match_boards")
    op.drop_table("group_matches")
