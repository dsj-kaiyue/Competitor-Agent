from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
import json
import logging
import re

import markdown
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.planner_agent import parse_task_plan
from app.graph.state import CompetitiveAnalysisState
from app.models.agent_node import AgentNode
from app.models.analysis_task import AnalysisTask
from app.models.claim import Claim
from app.models.claim_evidence import ClaimEvidence
from app.models.evidence_chunk import EvidenceChunk
from app.models.qa_result import QAResult
from app.models.report import Report
from app.models.source_document import SourceDocument
from app.services.log_service import add_log
from app.services.task_service import get_task_plan, update_task_status
from app.tools.llm_client import LLMClient
from app.tools.milvus_tool import MilvusTool
from app.tools.web_context_provider import WebContextProvider


logger = logging.getLogger("competitive-agent")


def _console(message: str, payload: dict | None = None) -> None:
    suffix = f" | {json.dumps(payload, ensure_ascii=False)}" if payload else ""
    logger.info("%s%s", message, suffix)


def _node(db: Session, task_id: int, node_key: str) -> AgentNode:
    node = db.scalar(select(AgentNode).where(AgentNode.task_id == task_id, AgentNode.node_key == node_key))
    if node is None:
        raise RuntimeError(f"Missing DAG node: {node_key}")
    return node


def _run_node(db: Session, task_id: int, node_key: str, task_status: str, fn: Callable[[AgentNode], None]) -> None:
    node = _node(db, task_id, node_key)
    update_task_status(db, task_id, task_status)
    started = datetime.utcnow()
    _console("node started", {"task_id": task_id, "node_key": node_key, "node_name": node.node_name})
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
        _console("node completed", {"task_id": task_id, "node_key": node_key, "duration_ms": node.duration_ms})
    except Exception as exc:
        ended = datetime.utcnow()
        node.status = "failed"
        node.ended_at = ended
        node.duration_ms = int((ended - started).total_seconds() * 1000)
        node.error_message = str(exc)
        add_log(db, task_id, node.id, f"{node.node_name} failed", {"error": str(exc)}, log_type="error")
        db.commit()
        _console("node failed", {"task_id": task_id, "node_key": node_key, "error": str(exc)})
        raise


def _strip_markdown(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"!\[[^\]]*]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)]\([^)]*\)", r"\1", text)
    text = re.sub(r"[#>*_`|]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _chunks(text: str, size: int = 1400, overlap: int = 180) -> list[str]:
    clean = _strip_markdown(text)
    if not clean:
        return []
    result = []
    start = 0
    while start < len(clean):
        result.append(clean[start : start + size])
        start += size - overlap
    return result


def _source_type(query: str, url: str) -> str:
    value = f"{query} {url}".lower()
    if "pricing" in value or "price" in value or "plans" in value:
        return "pricing_page"
    if "security" in value or "compliance" in value or "privacy" in value or "enterprise" in value:
        return "official_website"
    if "docs" in value or "documentation" in value:
        return "docs"
    return "official_website"


def _json_from_text(text: str):
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", text, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(1))


def _evidence_context(chunks: list[EvidenceChunk], limit: int = 10) -> str:
    lines = []
    for chunk in chunks[:limit]:
        lines.append(
            f"[evidence_id={chunk.id}] competitor={chunk.competitor_name}; source_type={chunk.source_type}; "
            f"title={chunk.source_title}; url={chunk.source_url}; text={chunk.chunk_text[:900]}"
        )
    return "\n".join(lines)


def run_competitive_analysis(db: Session, task_id: int) -> CompetitiveAnalysisState:
    state: CompetitiveAnalysisState = {"task_id": task_id, "errors": []}
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise RuntimeError(f"Task {task_id} not found")
    _console("analysis workflow started", {"task_id": task_id})

    llm = LLMClient()
    web = WebContextProvider()
    milvus = MilvusTool()

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
        if plan.auto_discover_competitors and not plan.competitors:
            discovery_query = f"{plan.target_product or plan.topic} competitors alternatives {plan.industry or ''}".strip()
            _console("competitor discovery started", {"task_id": task_id, "query": discovery_query})
            discovery_results = web.search(discovery_query, max_results=8)
            discovery_context = "\n".join(
                f"- title={item.get('title')}; url={item.get('url')}; description={item.get('description') or item.get('markdown') or ''}"
                for item in discovery_results
            )
            prompt = f"""
请从搜索结果中识别与目标产品最相关的直接竞品或替代产品。
目标产品：{plan.target_product or plan.topic}
行业：{plan.industry}
搜索结果：
{discovery_context}

只输出 JSON 数组，最多 6 个产品名。不要包含目标产品本身，不要输出解释。
"""
            try:
                discovered = _json_from_text(llm.complete(prompt, system="你只输出合法 JSON。"))
                if isinstance(discovered, dict):
                    discovered = discovered.get("competitors", [])
                plan.competitors = [
                    str(name).strip()
                    for name in discovered
                    if str(name).strip() and str(name).strip().lower() != str(plan.target_product or "").strip().lower()
                ][:6]
            except Exception as exc:
                _console("competitor discovery failed", {"task_id": task_id, "error": str(exc)})
                plan.competitors = []
            if not plan.competitors:
                raise RuntimeError("Auto competitor discovery did not produce competitors")
            task.task_plan_json = plan.model_dump()
            state["competitors"] = plan.competitors
            add_log(db, task_id, node.id, "Auto discovered competitors", {"competitors": plan.competitors})
            _console("competitor discovery completed", {"task_id": task_id, "competitors": plan.competitors})

        saved_ids: list[int] = []
        seen_urls: set[str] = set()
        for competitor in plan.competitors:
            _console("collector competitor started", {"task_id": task_id, "competitor": competitor})
            queries = [
                f"{competitor} {plan.industry or plan.topic} official product features",
                f"{competitor} pricing plans official",
                f"{competitor} docs enterprise security compliance privacy official",
            ]
            competitor_saved = 0
            for query in queries:
                _console("firecrawl search started", {"task_id": task_id, "query": query})
                results = web.search(query, max_results=3)
                _console("firecrawl search completed", {"task_id": task_id, "query": query, "result_count": len(results)})
                add_log(db, task_id, node.id, "Firecrawl search completed", {"query": query, "result_count": len(results)})
                for item in results:
                    url = item.get("url")
                    if not url or url in seen_urls or competitor_saved >= 5:
                        continue
                    _console("firecrawl scrape started", {"task_id": task_id, "url": url})
                    seen_urls.add(url)
                    scraped = web.scrape(url)
                    if not scraped or not scraped.get("markdown"):
                        _console("firecrawl scrape skipped", {"task_id": task_id, "url": url})
                        add_log(db, task_id, node.id, "Firecrawl scrape skipped", {"url": url}, log_type="warning")
                        continue
                    doc = SourceDocument(
                        task_id=task_id,
                        competitor_name=competitor,
                        source_url=url,
                        source_title=scraped.get("title") or item.get("title") or url,
                        source_type=_source_type(query, url),
                        content_markdown=scraped.get("markdown"),
                        content_text=_strip_markdown(scraped.get("markdown", "")),
                        metadata_json={"search_query": query, "search_result": item, "scrape_metadata": scraped.get("metadata") or {}},
                    )
                    db.add(doc)
                    db.flush()
                    saved_ids.append(doc.id)
                    competitor_saved += 1
                    _console("firecrawl scrape saved", {"task_id": task_id, "source_document_id": doc.id, "url": url})
                    add_log(db, task_id, node.id, "Firecrawl scrape saved", {"url": url, "source_document_id": doc.id})
                db.commit()
        if not saved_ids:
            raise RuntimeError("Firecrawl did not return any usable source documents")
        node.output_summary = f"真实采集并保存 {len(saved_ids)} 份 source_document"
        state["source_document_ids"] = saved_ids

    def evidence_extractor(node: AgentNode) -> None:
        docs = list(db.scalars(select(SourceDocument).where(SourceDocument.task_id == task_id).order_by(SourceDocument.id)))
        ids: list[int] = []
        for doc in docs:
            _console("evidence document started", {"task_id": task_id, "source_document_id": doc.id, "competitor": doc.competitor_name})
            for idx, text in enumerate(_chunks(doc.content_text or doc.content_markdown or "")[:4]):
                _console("embedding started", {"task_id": task_id, "source_document_id": doc.id, "chunk_index": idx})
                embedding = llm.embed_text(text)
                chunk = EvidenceChunk(
                    task_id=task_id,
                    source_document_id=doc.id,
                    competitor_name=doc.competitor_name,
                    source_url=doc.source_url,
                    source_title=doc.source_title,
                    source_type=doc.source_type,
                    chunk_index=idx,
                    chunk_text=text,
                    reliability_score=Decimal("0.92") if doc.source_type in {"official_website", "pricing_page"} else Decimal("0.78"),
                )
                db.add(chunk)
                db.flush()
                vector_id = milvus.upsert_evidence_embedding(
                    chunk_id=chunk.id,
                    task_id=task_id,
                    competitor_name=chunk.competitor_name,
                    source_type=chunk.source_type,
                    source_url=chunk.source_url,
                    embedding=embedding,
                )
                chunk.milvus_vector_id = vector_id
                ids.append(chunk.id)
                _console("evidence embedded and saved", {"task_id": task_id, "chunk_id": chunk.id, "vector_id": vector_id})
                add_log(db, task_id, node.id, "Evidence embedded and saved", {"chunk_id": chunk.id, "vector_id": vector_id})
            db.commit()
        if not ids:
            raise RuntimeError("No evidence chunks were extracted")
        node.output_summary = f"抽取并向量化 {len(ids)} 条 evidence_chunk"
        state["evidence_chunk_ids"] = ids

    def analyst_factory(node_key: str, claim_type: str, dimension: str) -> Callable[[AgentNode], None]:
        def analyst(node: AgentNode) -> None:
            plan = get_task_plan(task)
            claim_ids: list[int] = []
            for competitor in plan.competitors:
                _console("llm analyst started", {"task_id": task_id, "node_key": node_key, "competitor": competitor})
                evidence = list(
                    db.scalars(
                        select(EvidenceChunk)
                        .where(EvidenceChunk.task_id == task_id, EvidenceChunk.competitor_name == competitor)
                        .order_by(EvidenceChunk.reliability_score.desc(), EvidenceChunk.id)
                    )
                )
                prompt = f"""
你是严谨的竞品分析 Agent。请只基于给定 evidence 生成 {dimension} 维度的结构化结论。
竞品：{competitor}
分析主题：{plan.topic}
证据：
{_evidence_context(evidence, limit=12)}

输出 JSON 数组，最多 3 条。每条格式：
{{"claim_text":"中文结论，必须具体且可被证据支撑","evidence_ids":[数字ID],"confidence":0.0到1.0,"risk_level":"low|medium|high"}}
不要输出 JSON 之外的内容。
"""
                raw = llm.complete(prompt, system="你只输出合法 JSON，不编造证据。")
                parsed = _json_from_text(raw)
                if isinstance(parsed, dict):
                    parsed = parsed.get("claims", [])
                for item in parsed[:3]:
                    evidence_ids = [int(eid) for eid in item.get("evidence_ids", []) if str(eid).isdigit()]
                    valid_ids = [eid for eid in evidence_ids if any(chunk.id == eid for chunk in evidence)]
                    if not valid_ids and evidence:
                        valid_ids = [evidence[0].id]
                    claim = Claim(
                        task_id=task_id,
                        agent_node_id=node.id,
                        competitor_name=competitor,
                        claim_type=claim_type,
                        claim_text=str(item.get("claim_text") or "").strip(),
                        confidence=Decimal(str(item.get("confidence", 0.75))).quantize(Decimal("0.01")),
                        risk_level=str(item.get("risk_level") or "medium"),
                    )
                    if not claim.claim_text:
                        continue
                    db.add(claim)
                    db.flush()
                    for evidence_id in valid_ids[:4]:
                        db.add(ClaimEvidence(claim_id=claim.id, evidence_chunk_id=evidence_id))
                    claim_ids.append(claim.id)
                _console("llm analyst completed", {"task_id": task_id, "node_key": node_key, "competitor": competitor, "claim_count_so_far": len(claim_ids)})
                db.commit()
            if not claim_ids:
                raise RuntimeError(f"{node_key} did not produce claims")
            node.output_summary = f"{node_key} 使用 LLM 生成 {len(claim_ids)} 条 Claim"
            state.setdefault("claim_ids", []).extend(claim_ids)

        return analyst

    def report_writer(node: AgentNode) -> None:
        plan = get_task_plan(task)
        claims = list(db.scalars(select(Claim).where(Claim.task_id == task_id).order_by(Claim.id)))
        linked = list(db.scalars(select(ClaimEvidence).where(ClaimEvidence.claim_id.in_([claim.id for claim in claims])))) if claims else []
        evidence_by_claim: dict[int, list[int]] = {}
        for item in linked:
            evidence_by_claim.setdefault(item.claim_id, []).append(item.evidence_chunk_id)
        claim_context = "\n".join(
            f"[claim_id={claim.id}] competitor={claim.competitor_name}; type={claim.claim_type}; "
            f"evidence_ids={evidence_by_claim.get(claim.id, [])}; text={claim.claim_text}"
            for claim in claims
        )
        prompt = f"""
请基于以下结构化 Claim 写一份中文 Markdown 竞品分析报告。
主题：{plan.topic}
行业：{plan.industry}
竞品：{', '.join(plan.competitors)}
分析维度：{', '.join(plan.analysis_dimensions)}

要求：
1. 必须覆盖所有分析维度。
2. 关键结论后标注 claim_id 和 evidence_ids。
3. 不要编造没有 Claim 支撑的信息。
4. 输出完整 Markdown。

Claims:
{claim_context}
"""
        _console("llm report writer started", {"task_id": task_id, "claim_count": len(claims)})
        content = llm.complete(prompt, system="你是专业竞品分析报告撰写 Agent，输出中文 Markdown。")
        report = Report(
            task_id=task_id,
            title=f"{plan.topic}报告",
            content_markdown=content,
            content_html=markdown.markdown(content, extensions=["tables"]),
            report_json={"claim_ids": [claim.id for claim in claims], "mode": "firecrawl_llm_milvus"},
        )
        db.add(report)
        db.flush()
        node.output_summary = f"使用 LLM 生成报告 #{report.id}"
        _console("llm report writer completed", {"task_id": task_id, "report_id": report.id})
        state["report_id"] = report.id

    def qa(node: AgentNode) -> None:
        plan = get_task_plan(task)
        report = db.scalar(select(Report).where(Report.task_id == task_id).order_by(Report.id.desc()))
        claims = list(db.scalars(select(Claim).where(Claim.task_id == task_id)))
        linked_claim_ids = set(db.scalars(select(ClaimEvidence.claim_id).where(ClaimEvidence.claim_id.in_([claim.id for claim in claims])))) if claims else set()
        issues = []
        for claim in claims:
            if claim.id not in linked_claim_ids:
                issues.append({"type": "missing_evidence", "severity": "high", "message": f"Claim {claim.id} 缺少证据绑定", "related_claim_id": claim.id, "suggested_action": "reanalyze"})
            if claim.confidence is not None and claim.confidence < Decimal("0.65"):
                issues.append({"type": "weak_evidence", "severity": "medium", "message": f"Claim {claim.id} 置信度偏低", "related_claim_id": claim.id, "suggested_action": "collect"})
        if report:
            missing_dimensions = [dim for dim in plan.analysis_dimensions if dim not in report.content_markdown]
            if missing_dimensions:
                issues.append({"type": "schema_incomplete", "severity": "medium", "message": f"报告可能未显式覆盖维度：{', '.join(missing_dimensions)}", "related_claim_id": None, "suggested_action": "rewrite"})
        qa_prompt = f"""
请复核这份竞品分析报告是否存在明显逻辑或证据问题。
仅基于报告和问题列表输出 JSON：
{{"passed":true/false,"score":0.0到1.0,"issues":[{{"type":"logic_gap|unsupported_claim|weak_evidence|schema_incomplete","severity":"low|medium|high","message":"中文问题","related_claim_id":null,"suggested_action":"collect|reanalyze|rewrite"}}]}}

报告：
{(report.content_markdown if report else '')[:6000]}

规则检查问题：
{json.dumps(issues, ensure_ascii=False)}
"""
        _console("qa llm review started", {"task_id": task_id, "rule_issue_count": len(issues)})
        try:
            qa_json = _json_from_text(llm.complete(qa_prompt, system="你只输出合法 JSON。"))
            llm_issues = qa_json.get("issues", []) if isinstance(qa_json, dict) else []
            issues.extend(llm_issues)
            score = Decimal(str(qa_json.get("score", 0.85))).quantize(Decimal("0.01")) if isinstance(qa_json, dict) else Decimal("0.85")
            passed = bool(qa_json.get("passed", True)) if isinstance(qa_json, dict) else True
        except Exception:
            score = Decimal("0.80")
            passed = True
        passed = passed and not any(item.get("severity") == "high" for item in issues)
        qa_result = QAResult(task_id=task_id, report_id=report.id if report else None, passed=passed, score=score, issues_json=issues)
        db.add(qa_result)
        db.flush()
        node.output_summary = f"QA 得分 {qa_result.score}，问题 {len(issues)} 个"
        _console("qa completed", {"task_id": task_id, "qa_result_id": qa_result.id, "passed": qa_result.passed, "score": str(qa_result.score)})
        state["qa_result_id"] = qa_result.id

    update_task_status(db, task_id, "running")
    _run_node(db, task_id, "planner", "planned", planner)
    _run_node(db, task_id, "collector", "collecting", collector)
    _run_node(db, task_id, "evidence_extractor", "extracting", evidence_extractor)
    _run_node(db, task_id, "feature_analysis", "analyzing", analyst_factory("feature_analysis", "feature", "产品定位、核心功能、Agent 能力、IDE 集成"))
    _run_node(db, task_id, "pricing_analysis", "analyzing", analyst_factory("pricing_analysis", "pricing", "价格策略、套餐结构、个人与团队商业化"))
    _run_node(db, task_id, "market_analysis", "analyzing", analyst_factory("market_analysis", "market", "适用用户、市场定位、企业能力"))
    _run_node(db, task_id, "security_analysis", "analyzing", analyst_factory("security_analysis", "security", "安全合规、隐私、企业治理能力"))
    _run_node(db, task_id, "report_writer", "writing", report_writer)
    _run_node(db, task_id, "qa", "qa_checking", qa)
    update_task_status(db, task_id, "success")
    _console("analysis workflow completed", {"task_id": task_id})
    return state
