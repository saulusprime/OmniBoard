"""posizione iniziale da FEN

Revisione: 0007
Precedente: 0006
Creata il: 2026-07-07 19:36:02.001846
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Posizione iniziale personalizzata (FEN, solo scacchi); None = standard.
    with op.batch_alter_table("game_sessions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("start_fen", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("game_sessions", schema=None) as batch_op:
        batch_op.drop_column("start_fen")
