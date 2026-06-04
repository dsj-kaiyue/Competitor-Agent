"""add qa state to agent node

Revision ID: 0004_agent_node_qa_state
Revises: 0003_dimension_claims
Create Date: 2026-06-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004_agent_node_qa_state"
down_revision: str | None = "0003_dimension_claims"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_node", sa.Column("qa_passed", sa.Boolean(), nullable=True))
    op.add_column("agent_node", sa.Column("qa_score", sa.Numeric(4, 2), nullable=True))
    op.add_column("agent_node", sa.Column("qa_revision_round", sa.Integer(), nullable=True))
    op.add_column("agent_node", sa.Column("qa_issue_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("agent_node", sa.Column("qa_updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_node", "qa_updated_at")
    op.drop_column("agent_node", "qa_issue_count")
    op.drop_column("agent_node", "qa_revision_round")
    op.drop_column("agent_node", "qa_score")
    op.drop_column("agent_node", "qa_passed")
