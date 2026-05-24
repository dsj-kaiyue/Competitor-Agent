from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

import markdown
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.planner_agent import parse_task_plan
from app.graph.state import CompetitiveAnalysisState
from app.models.agent_node import AgentNode
from app.models.claim import Claim
from app.models.claim_evidence import ClaimEvidence
from app.models.evidence_chunk import EvidenceChunk
from app.models.qa_result import QAResult
from app.models.report import Report
from app.models.source_document import SourceDocument
from app.services.log_service import add_log
from app.services.task_service import get_task_plan, update_task_status


def _node(db: Session, task_id: int, node_key: str) -> AgentNode:
    node = db.scalar(select(AgentNode).where(AgentNode.task_id == task_id, AgentNode.node_key == node_key))
    if node is None:
        raise RuntimeError(f"Missing DAG node: {node_key}")
    return node


def _run_node(db: Session, task_id: int, node_key: str, task_status: str, fn: Callable[[AgentNode], None]) -> None:
    node = _node(db, task_id, node_key)
    update_task_status(db, task_id, task_status)
    started = datetime.utcnow()
    node.status = "running"
    node.started_at = started
    node.error_message = None
    add_log(db, task_id, node.id, f"{node.node_name} started", {"node_key": node_key})
    db.commit()
    try:
        fn(node)
        ended = datetime.utcnow()
        node.status = "success"
        node.ended_at = ended
        node.duration_ms = int((ended - started).total_seconds() * 1000)
        add_log(db, task_id, node.id, f"{node.node_name} completed")
        db.commit()
    except Exception as exc:
        ended = datetime.utcnow()
        node.status = "failed"
        node.ended_at = ended
        node.duration_ms = int((ended - started).total_seconds() * 1000)
        node.error_message = str(exc)
        add_log(db, task_id, node.id, f"{node.node_name} failed", {"error": str(exc)}, log_type="error")
        db.commit()
        raise


def run_competitive_analysis(db: Session, task_id: int) -> CompetitiveAnalysisState:
    state: CompetitiveAnalysisState = {"task_id": task_id, "errors": []}
    task = db.get(__import__("app.models.analysis_task", fromlist=["AnalysisTask"]).AnalysisTask, task_id)
    if task is None:
        raise RuntimeError(f"Task {task_id} not found")

    def planner(node: AgentNode) -> None:
        plan = parse_task_plan(task.user_input)
        task.task_plan_json = plan.model_dump()
        task.topic = plan.topic
        task.industry = plan.industry
        task.report_depth = plan.report_depth
        task.output_language = plan.output_language
        node.input_summary = task.user_input[:300]
        node.output_summary = f"识别 {len(plan.competitors)} 个竞品、{len(plan.analysis_dimensions)} 个分析维度"
        state["task_plan"] = plan.model_dump()
        state["competitors"] = plan.competitors
        state["analysis_dimensions"] = plan.analysis_dimensions

    def collector(node: AgentNode) -> None:
        plan = get_task_plan(task)
        ids: list[int] = []
        official_urls = {
            "Cursor": "https://cursor.com",
            "GitHub Copilot": "https://github.com/features/copilot",
            "Windsurf": "https://windsurf.com",
            "Tabnine": "https://www.tabnine.com",
        }
        for competitor in plan.competitors:
            url = official_urls.get(competitor, f"https://www.google.com/search?q={competitor}")
            doc = SourceDocument(
                task_id=task_id,
                competitor_name=competitor,
                source_url=url,
                source_title=f"{competitor} official overview",
                source_type="official_website",
                content_markdown=f"# {competitor}\n\n{competitor} 是 AI 编程助手竞品分析中的公开资料来源占位。MVP mock 采集层会在接入 Firecrawl 后替换为真实网页正文。",
                content_text=f"{competitor} 提供 AI 编程辅助、代码补全、聊天或 Agent 工作流等能力，面向个人开发者和团队。",
                metadata_json={"mode": "mock", "replace_with": "Firecrawl Search + Scrape"},
            )
            db.add(doc)
            db.flush()
            ids.append(doc.id)
        node.output_summary = f"保存 {len(ids)} 份 source_document"
        state["source_document_ids"] = ids

    def evidence_extractor(node: AgentNode) -> None:
        docs = list(db.scalars(select(SourceDocument).where(SourceDocument.task_id == task_id).order_by(SourceDocument.id)))
        ids: list[int] = []
        for doc in docs:
            chunks = [
                (0, f"{doc.competitor_name} 的公开产品资料显示，其核心价值围绕 AI 编码辅助、上下文理解和开发工作流效率提升。", "docs"),
                (1, f"{doc.competitor_name} 的商业化通常包含个人开发者与团队/企业使用场景，价格和企业能力需要以官方页面持续校验。", "pricing_page"),
                (2, f"{doc.competitor_name} 在企业采购中需要关注安全合规、代码隐私、权限控制和组织管理能力。", "official_website"),
            ]
            for idx, text, source_type in chunks:
                chunk = EvidenceChunk(
                    task_id=task_id,
                    source_document_id=doc.id,
                    competitor_name=doc.competitor_name,
                    source_url=doc.source_url,
                    source_title=doc.source_title,
                    source_type=source_type,
                    chunk_index=idx,
                    chunk_text=text,
                    reliability_score=Decimal("0.80"),
                    milvus_vector_id=f"mock-{task_id}-{doc.id}-{idx}",
                )
                db.add(chunk)
                db.flush()
                ids.append(chunk.id)
        node.output_summary = f"抽取 {len(ids)} 条 evidence_chunk"
        state["evidence_chunk_ids"] = ids

    def analyst_factory(node_key: str, claim_type: str, template: str) -> Callable[[AgentNode], None]:
        def analyst(node: AgentNode) -> None:
            chunks = list(db.scalars(select(EvidenceChunk).where(EvidenceChunk.task_id == task_id).order_by(EvidenceChunk.id)))
            by_competitor: dict[str, list[EvidenceChunk]] = {}
            for chunk in chunks:
                if chunk.competitor_name:
                    by_competitor.setdefault(chunk.competitor_name, []).append(chunk)
            claim_ids: list[int] = []
            for competitor, evidence in by_competitor.items():
                claim = Claim(
                    task_id=task_id,
                    agent_node_id=node.id,
                    competitor_name=competitor,
                    claim_type=claim_type,
                    claim_text=template.format(competitor=competitor),
                    confidence=Decimal("0.82"),
                    risk_level="low",
                )
                db.add(claim)
                db.flush()
                for chunk in evidence[:2]:
                    db.add(ClaimEvidence(claim_id=claim.id, evidence_chunk_id=chunk.id))
                claim_ids.append(claim.id)
            node.output_summary = f"{node_key} 生成 {len(claim_ids)} 条 Claim"
            state.setdefault("claim_ids", []).extend(claim_ids)
        return analyst

    def report_writer(node: AgentNode) -> None:
        plan = get_task_plan(task)
        claims = list(db.scalars(select(Claim).where(Claim.task_id == task_id).order_by(Claim.id)))
        lines = [
            f"# {plan.topic}报告",
            "",
            "## 执行摘要",
            "本报告基于 MVP 证据链路生成，当前采集层使用 mock 数据跑通 DAG、MySQL、Claim-Evidence 关联与 QA 展示。接入 Firecrawl 后可替换为真实公开资料。",
            "",
            "## 竞品结论",
        ]
        for competitor in plan.competitors:
            lines.append(f"### {competitor}")
            for claim in [item for item in claims if item.competitor_name == competitor]:
                lines.append(f"- [{claim.claim_type}] {claim.claim_text} (claim_id: {claim.id})")
            lines.append("")
        lines.extend(["## 覆盖维度", ", ".join(plan.analysis_dimensions)])
        content = "\n".join(lines)
        report = Report(
            task_id=task_id,
            title=f"{plan.topic}报告",
            content_markdown=content,
            content_html=markdown.markdown(content, extensions=["tables"]),
            report_json={"claim_ids": [claim.id for claim in claims], "mode": "mock_mvp"},
        )
        db.add(report)
        db.flush()
        node.output_summary = f"生成报告 #{report.id}"
        state["report_id"] = report.id

    def qa(node: AgentNode) -> None:
        report = db.scalar(select(Report).where(Report.task_id == task_id).order_by(Report.id.desc()))
        claims = list(db.scalars(select(Claim).where(Claim.task_id == task_id)))
        linked_claim_ids = set(db.scalars(select(ClaimEvidence.claim_id).where(ClaimEvidence.claim_id.in_([claim.id for claim in claims])))) if claims else set()
        issues = []
        for claim in claims:
            if claim.id not in linked_claim_ids:
                issues.append({"type": "missing_evidence", "severity": "high", "message": f"Claim {claim.id} 缺少证据绑定", "related_claim_id": claim.id, "suggested_action": "reanalyze"})
        if report and "mock 数据" in report.content_markdown:
            issues.append({"type": "weak_evidence", "severity": "medium", "message": "当前为 MVP mock 采集数据，演示真实分析前应接入 Firecrawl。", "related_claim_id": None, "suggested_action": "collect"})
        qa_result = QAResult(task_id=task_id, report_id=report.id if report else None, passed=not any(i["severity"] == "high" for i in issues), score=Decimal("0.88"), issues_json=issues)
        db.add(qa_result)
        db.flush()
        node.output_summary = f"QA 得分 {qa_result.score}，问题 {len(issues)} 个"
        state["qa_result_id"] = qa_result.id

    update_task_status(db, task_id, "running")
    _run_node(db, task_id, "planner", "planned", planner)
    _run_node(db, task_id, "collector", "collecting", collector)
    _run_node(db, task_id, "evidence_extractor", "extracting", evidence_extractor)
    _run_node(db, task_id, "feature_analysis", "analyzing", analyst_factory("feature_analysis", "feature", "{competitor} 的产品竞争力主要体现在 AI 编码辅助、上下文理解和开发流程提效。"))
    _run_node(db, task_id, "pricing_analysis", "analyzing", analyst_factory("pricing_analysis", "pricing", "{competitor} 需要从个人订阅、团队协作和企业采购三个层面评估价格策略。"))
    _run_node(db, task_id, "market_analysis", "analyzing", analyst_factory("market_analysis", "market", "{competitor} 面向开发者效率工具市场，适用用户覆盖个人开发者、工程团队和企业研发组织。"))
    _run_node(db, task_id, "security_analysis", "analyzing", analyst_factory("security_analysis", "security", "{competitor} 的企业落地重点包括代码隐私、安全合规、权限治理和组织级管理。"))
    _run_node(db, task_id, "report_writer", "writing", report_writer)
    _run_node(db, task_id, "qa", "qa_checking", qa)
    update_task_status(db, task_id, "success")
    return state
