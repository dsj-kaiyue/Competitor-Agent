"""add user management

Revision ID: 0005_user_management
Revises: 0004_agent_node_qa_state
Create Date: 2026-06-05
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0005_user_management"
down_revision: str | None = "0004_agent_node_qa_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(80), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_app_user_username", "app_user", ["username"], unique=True)
    op.add_column("analysis_task", sa.Column("user_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_analysis_task_user_id", "analysis_task", ["user_id"])
    op.create_foreign_key("fk_analysis_task_user_id", "analysis_task", "app_user", ["user_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_analysis_task_user_id", "analysis_task", type_="foreignkey")
    op.drop_index("ix_analysis_task_user_id", table_name="analysis_task")
    op.drop_column("analysis_task", "user_id")
    op.drop_index("ix_app_user_username", table_name="app_user")
    op.drop_table("app_user")
