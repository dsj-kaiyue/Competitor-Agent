from pathlib import Path
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.graph.workflow import (
    _apply_dimension_qa_scores_to_nodes,
    _failed_dimension_nodes_from_qa_state,
    _failed_dimension_nodes_from_scores,
    _build_finalizer_revision_context,
    _revision_action_for_failed_dimensions,
    _revision_plan_for_failed_dimensions,
    _sync_dimension_qa_state_and_get_failed_nodes,
)
from app.models.agent_node import AgentNode
from app.models.analysis_task import AnalysisTask  # noqa: F401


def test_revision_targets_include_all_failed_dimensions_even_with_partial_issues():
    failed_nodes = [
        "dimension_analysis_agent_capability",
        "dimension_analysis_pricing",
        "dimension_analysis_enterprise",
        "dimension_analysis_security",
        "dimension_analysis_users",
    ]
    issues = [
        {"suggested_action": "reanalyze", "target_node": failed_nodes[0]},
        {"suggested_action": "reanalyze", "target_node": failed_nodes[1]},
        {"suggested_action": "reanalyze", "target_node": failed_nodes[2]},
        {"suggested_action": "reanalyze", "target_node": failed_nodes[3]},
    ]

    action, targets = _revision_action_for_failed_dimensions(issues, failed_nodes)

    assert action == "reanalyze"
    assert targets == failed_nodes


def test_revision_targets_keep_failed_subset_after_partial_qa():
    previous_failed_nodes = {
        "dimension_analysis_agent_capability",
        "dimension_analysis_pricing",
        "dimension_analysis_enterprise",
        "dimension_analysis_security",
        "dimension_analysis_users",
    }
    current_failed_nodes = [
        "dimension_analysis_enterprise",
        "dimension_analysis_security",
        "dimension_analysis_users",
    ]

    action, targets = _revision_action_for_failed_dimensions([], current_failed_nodes)

    assert action == "reanalyze"
    assert set(targets).issubset(previous_failed_nodes)
    assert targets == current_failed_nodes


def test_recollect_action_still_targets_every_failed_dimension():
    failed_nodes = [
        "dimension_analysis_enterprise",
        "dimension_analysis_security",
    ]
    issues = [
        {"suggested_action": "recollect", "target_node": failed_nodes[0], "search_query": "example query"},
    ]

    action, targets = _revision_action_for_failed_dimensions(issues, failed_nodes)

    assert action == "recollect"
    assert targets == failed_nodes


def test_rewrite_action_still_carries_every_failed_dimension_target():
    failed_nodes = [
        "dimension_analysis_ide",
        "dimension_analysis_pricing",
        "dimension_analysis_enterprise",
        "dimension_analysis_security",
        "dimension_analysis_users",
    ]
    issues = [
        {"suggested_action": "rewrite", "target_node": failed_nodes[2]},
    ]

    action, targets = _revision_action_for_failed_dimensions(issues, failed_nodes)

    assert action == "rewrite"
    assert targets == failed_nodes


def test_mixed_revision_plan_groups_actions_but_targets_all_failed_dimensions():
    failed_nodes = [
        "dimension_analysis_ide",
        "dimension_analysis_pricing",
        "dimension_analysis_enterprise",
        "dimension_analysis_security",
        "dimension_analysis_users",
    ]
    issues = [
        {"suggested_action": "reanalyze", "target_node": "dimension_analysis_ide"},
        {"suggested_action": "reanalyze", "target_node": "dimension_analysis_pricing"},
        {"suggested_action": "rewrite", "target_node": "dimension_analysis_enterprise"},
        {"suggested_action": "recollect", "target_node": "dimension_analysis_security", "search_query": "Security official docs"},
        {"suggested_action": "recollect", "target_node": "dimension_analysis_users", "search_query": "Users official docs"},
    ]

    plan = _revision_plan_for_failed_dimensions(issues, failed_nodes)

    assert plan["next_action"] == "recollect"
    assert plan["target_nodes"] == failed_nodes
    assert plan["recollect_nodes"] == ["dimension_analysis_security", "dimension_analysis_users"]
    assert plan["reanalyze_nodes"] == ["dimension_analysis_ide", "dimension_analysis_pricing"]
    assert plan["rewrite_nodes"] == ["dimension_analysis_enterprise"]
    assert plan["analysis_nodes"] == [
        "dimension_analysis_security",
        "dimension_analysis_users",
        "dimension_analysis_ide",
        "dimension_analysis_pricing",
    ]


def test_finalizer_revision_context_carries_qa_issues_into_targeted_rewrite():
    context = _build_finalizer_revision_context(
        {
            "score": 0.62,
            "issues": [
                {
                    "severity": "high",
                    "message": "执行摘要引入了 Claim 中没有的新事实",
                    "paragraph_id": "executive_summary_p1",
                    "claim_ids": [1, 2],
                }
            ],
        },
        [
            {
                "severity": "medium",
                "message": "安全合规维度证据不足",
                "related_dimension": "安全合规",
                "target_node": "dimension_analysis_security",
                "suggested_action": "reanalyze",
            }
        ],
    )

    assert context["revision_required"] is True
    assert context["finalizer_score"] == 0.62
    assert context["grounding_issues"] == [
        {
            "severity": "high",
            "message": "执行摘要引入了 Claim 中没有的新事实",
            "paragraph_id": "executive_summary_p1",
            "claim_ids": [1, 2],
        }
    ]
    assert context["residual_body_qa_issues"][0]["target_node"] == "dimension_analysis_security"
    assert any("逐条修复" in rule or "paragraph_id" in rule for rule in context["rewrite_rules"])


def test_dimension_node_qa_state_is_authoritative_for_failed_targets():
    engine = create_engine("sqlite:///:memory:")
    AnalysisTask.__table__.create(engine)
    AgentNode.__table__.create(engine)
    first = "dimension_analysis_enterprise"
    second = "dimension_analysis_security"
    third = "dimension_analysis_users"

    with Session(engine) as session:
        session.add_all(
            [
                AgentNode(task_id=1, node_key=first, node_name="企业能力分析 Agent", node_type="dimension_analyst", status="success"),
                AgentNode(task_id=1, node_key=second, node_name="安全合规分析 Agent", node_type="dimension_analyst", status="success"),
                AgentNode(task_id=1, node_key=third, node_name="适用用户分析 Agent", node_type="dimension_analyst", status="success"),
            ]
        )
        session.flush()

        _apply_dimension_qa_scores_to_nodes(
            session,
            1,
            [
                {"target_node": first, "score": 0.85, "passed": True, "issues": []},
                {"target_node": second, "score": 0.7, "passed": False, "issues": [{"message": "证据不足"}]},
                {"target_node": third, "score": 0.6, "passed": False, "issues": [{"message": "需要重写"}]},
            ],
            revision_round=1,
        )

        assert _failed_dimension_nodes_from_qa_state(session, 1) == [second, third]
        assert _failed_dimension_nodes_from_qa_state(session, 1, [first, second]) == [second]


def test_failed_dimension_nodes_from_scores_treat_string_false_as_failed():
    scores = [
        {"target_node": "dimension_analysis_enterprise", "passed": "false"},
        {"target_node": "dimension_analysis_agent", "passed": "通过"},
        {"target_node": "dimension_analysis_security", "passed": False},
    ]

    assert _failed_dimension_nodes_from_scores(scores) == [
        "dimension_analysis_enterprise",
        "dimension_analysis_security",
    ]


def test_sync_dimension_qa_state_returns_database_failed_nodes_after_consistency_check():
    engine = create_engine("sqlite:///:memory:")
    AnalysisTask.__table__.create(engine)
    AgentNode.__table__.create(engine)
    first = "dimension_analysis_ide"
    second = "dimension_analysis_enterprise"

    with Session(engine) as session:
        session.add_all(
            [
                AgentNode(task_id=1, node_key=first, node_name="IDE 集成分析 Agent", node_type="dimension_analyst", status="success"),
                AgentNode(task_id=1, node_key=second, node_name="企业能力分析 Agent", node_type="dimension_analyst", status="success"),
            ]
        )
        session.flush()

        failed_nodes = _sync_dimension_qa_state_and_get_failed_nodes(
            session,
            1,
            [
                {"target_node": first, "score": 0.5, "passed": False, "issues": [{"message": "需要重分析"}]},
                {"target_node": second, "score": 0.5, "passed": "false", "issues": [{"message": "需要重写"}]},
            ],
            revision_round=0,
        )

        assert failed_nodes == [first, second]
        assert _failed_dimension_nodes_from_qa_state(session, 1) == [first, second]


def test_sync_dimension_qa_state_uses_current_scores_when_a_node_is_missing():
    engine = create_engine("sqlite:///:memory:")
    AnalysisTask.__table__.create(engine)
    AgentNode.__table__.create(engine)

    with Session(engine) as session:
        session.add(
            AgentNode(
                task_id=1,
                node_key="dimension_analysis_ide",
                node_name="IDE 集成分析 Agent",
                node_type="dimension_analyst",
                status="success",
            )
        )
        session.flush()

        failed_nodes = _sync_dimension_qa_state_and_get_failed_nodes(
            session,
            1,
            [
                {"target_node": "dimension_analysis_ide", "score": 0.5, "passed": False, "issues": []},
                {"target_node": "dimension_analysis_enterprise", "score": 0.5, "passed": False, "issues": []},
            ],
            revision_round=0,
        )

        assert failed_nodes == ["dimension_analysis_ide", "dimension_analysis_enterprise"]
