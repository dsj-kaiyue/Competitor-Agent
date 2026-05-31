"""add dynamic dimension fields to claim

Revision ID: 0003_dimension_claims
Revises: 0002_dynamic_profile_matrix
Create Date: 2026-05-31
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003_dimension_claims"
down_revision: str | None = "0002_dynamic_profile_matrix"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("claim", sa.Column("dimension_key", sa.String(100), nullable=True))
    op.add_column("claim", sa.Column("dimension_label", sa.String(255), nullable=True))
    op.add_column("claim", sa.Column("dimension_prompt_json", sa.JSON(), nullable=True))
    op.create_index("ix_claim_dimension_key", "claim", ["dimension_key"])


def downgrade() -> None:
    op.drop_index("ix_claim_dimension_key", table_name="claim")
    op.drop_column("claim", "dimension_prompt_json")
    op.drop_column("claim", "dimension_label")
    op.drop_column("claim", "dimension_key")
