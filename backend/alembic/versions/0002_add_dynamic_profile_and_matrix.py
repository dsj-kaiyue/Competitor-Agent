"""add dynamic profile and matrix

Revision ID: 0002_dynamic_profile_matrix
Revises: 0001_initial_schema
Create Date: 2026-05-31
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002_dynamic_profile_matrix"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "competitor_profile",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("competitor_name", sa.String(255), nullable=False),
        sa.Column("template_key", sa.String(100)),
        sa.Column("profile_schema_json", sa.JSON(), nullable=False),
        sa.Column("profile_data_json", sa.JSON(), nullable=False),
        sa.Column("claim_ids_json", sa.JSON()),
        sa.Column("evidence_ids_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("task_id", "competitor_name", name="uq_profile_task_competitor"),
    )
    op.create_index("ix_competitor_profile_task_id", "competitor_profile", ["task_id"])
    op.create_index("ix_competitor_profile_competitor_name", "competitor_profile", ["competitor_name"])
    op.create_index("ix_competitor_profile_template_key", "competitor_profile", ["template_key"])
    op.create_index("ix_profile_task_template", "competitor_profile", ["task_id", "template_key"])

    op.create_table(
        "comparison_matrix",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("template_key", sa.String(100)),
        sa.Column("matrix_type", sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("matrix_schema_json", sa.JSON(), nullable=False),
        sa.Column("matrix_data_json", sa.JSON(), nullable=False),
        sa.Column("claim_ids_json", sa.JSON()),
        sa.Column("evidence_ids_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_comparison_matrix_task_id", "comparison_matrix", ["task_id"])
    op.create_index("ix_comparison_matrix_template_key", "comparison_matrix", ["template_key"])
    op.create_index("ix_comparison_matrix_matrix_type", "comparison_matrix", ["matrix_type"])
    op.create_index("ix_matrix_task_type", "comparison_matrix", ["task_id", "matrix_type"])


def downgrade() -> None:
    op.drop_table("comparison_matrix")
    op.drop_table("competitor_profile")
