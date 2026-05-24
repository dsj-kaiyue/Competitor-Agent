"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_task",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_input", sa.Text(), nullable=False),
        sa.Column("topic", sa.String(255), nullable=False),
        sa.Column("industry", sa.String(255)),
        sa.Column("target_product", sa.String(255)),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("report_depth", sa.String(50), server_default="standard"),
        sa.Column("output_language", sa.String(50), server_default="zh-CN"),
        sa.Column("task_plan_json", sa.JSON()),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "agent_node",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("node_key", sa.String(100), nullable=False),
        sa.Column("node_name", sa.String(255), nullable=False),
        sa.Column("node_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("input_summary", sa.Text()),
        sa.Column("output_summary", sa.Text()),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("ended_at", sa.DateTime()),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("retry_count", sa.Integer(), server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["analysis_task.id"]),
    )
    op.create_index("ix_agent_node_task_id", "agent_node", ["task_id"])
    op.create_table(
        "agent_run_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("node_id", sa.BigInteger()),
        sa.Column("log_type", sa.String(50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["analysis_task.id"]),
        sa.ForeignKeyConstraint(["node_id"], ["agent_node.id"]),
    )
    op.create_index("ix_agent_run_log_task_id", "agent_run_log", ["task_id"])
    op.create_table(
        "source_document",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("competitor_name", sa.String(255)),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_title", sa.String(500)),
        sa.Column("source_type", sa.String(100)),
        sa.Column("content_markdown", mysql.MEDIUMTEXT()),
        sa.Column("content_text", mysql.MEDIUMTEXT()),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["analysis_task.id"]),
    )
    op.create_index("ix_source_document_task_id", "source_document", ["task_id"])
    op.create_table(
        "evidence_chunk",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("source_document_id", sa.BigInteger(), nullable=False),
        sa.Column("competitor_name", sa.String(255)),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_title", sa.String(500)),
        sa.Column("source_type", sa.String(100)),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("reliability_score", sa.Numeric(4, 2)),
        sa.Column("milvus_vector_id", sa.String(128)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["analysis_task.id"]),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_document.id"]),
    )
    op.create_index("ix_evidence_chunk_task_id", "evidence_chunk", ["task_id"])
    op.create_table(
        "claim",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("agent_node_id", sa.BigInteger()),
        sa.Column("competitor_name", sa.String(255)),
        sa.Column("claim_type", sa.String(100)),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 2)),
        sa.Column("risk_level", sa.String(50)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["analysis_task.id"]),
        sa.ForeignKeyConstraint(["agent_node_id"], ["agent_node.id"]),
    )
    op.create_index("ix_claim_task_id", "claim", ["task_id"])
    op.create_table(
        "claim_evidence",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("claim_id", sa.BigInteger(), nullable=False),
        sa.Column("evidence_chunk_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claim.id"]),
        sa.ForeignKeyConstraint(["evidence_chunk_id"], ["evidence_chunk.id"]),
    )
    op.create_index("ix_claim_evidence_claim_id", "claim_evidence", ["claim_id"])
    op.create_index("ix_claim_evidence_evidence_chunk_id", "claim_evidence", ["evidence_chunk_id"])
    op.create_table(
        "report",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content_markdown", mysql.MEDIUMTEXT(), nullable=False),
        sa.Column("content_html", mysql.MEDIUMTEXT()),
        sa.Column("report_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["analysis_task.id"]),
    )
    op.create_index("ix_report_task_id", "report", ["task_id"])
    op.create_table(
        "qa_result",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("report_id", sa.BigInteger()),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Numeric(4, 2)),
        sa.Column("issues_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["analysis_task.id"]),
        sa.ForeignKeyConstraint(["report_id"], ["report.id"]),
    )
    op.create_index("ix_qa_result_task_id", "qa_result", ["task_id"])


def downgrade() -> None:
    for table in ["qa_result", "report", "claim_evidence", "claim", "evidence_chunk", "source_document", "agent_run_log", "agent_node", "analysis_task"]:
        op.drop_table(table)
