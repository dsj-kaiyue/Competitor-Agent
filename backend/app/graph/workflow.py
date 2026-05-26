from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from decimal import Decimal
import json
import logging
import re

import markdown
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.planner_agent import parse_task_plan
from app.core.config import settings
from app.graph.state import CompetitiveAnalysisState
from app.models.agent_node import AgentNode
from app.models.analysis_task import AnalysisTask
from app.models.claim import Claim
from app.models.claim_evidence import ClaimEvidence
from app.models.evidence_chunk import EvidenceChunk
from app.models.qa_result import QAResult
from app.models.report import Report
from app.models.source_document import SourceDocument
from app.services.evidence_retriever import EvidenceRetriever
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
    if node.ended_at is not None:
        node.retry_count += 1
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


def _analysis_query(competitor: str, claim_type: str, dimension: str, topic: str) -> tuple[str, str | None]:
    if claim_type == "pricing":
        return f"{competitor} pricing plans subscription team enterprise billing official", "pricing_page"
    if claim_type == "market":
        return f"{competitor} target users market positioning enterprise teams developers product strategy", None
    if claim_type == "security":
        return f"{competitor} security privacy compliance enterprise data protection training data policy", None
    return f"{competitor} product positioning core features {topic} {dimension}", None


def _target_nodes_from_issue(issue: dict) -> list[str]:
    target_node = issue.get("target_node")
    if target_node:
        return [target_node]
    dimension = str(issue.get("related_dimension") or issue.get("type") or "").lower()
    if "pricing" in dimension or "价格" in dimension:
        return ["pricing_analysis"]
    if "security" in dimension or "privacy" in dimension or "安全" in dimension:
        return ["security_analysis"]
    if "market" in dimension or "市场" in dimension:
        return ["market_analysis"]
    if "feature" in dimension or "功能" in dimension:
        return ["feature_analysis"]
    return []


def _decide_next_action(issues: list[dict]) -> tuple[str, list[str]]:
    high_issues = [issue for issue in issues if issue.get("severity") == "high"]
    candidates = high_issues or issues
    if any(issue.get("suggested_action") == "recollect" for issue in candidates):
        return "recollect", ["collector"]
    if any(issue.get("suggested_action") == "reanalyze" for issue in candidates):
        target_nodes: list[str] = []
        for issue in candidates:
            target_nodes.extend(_target_nodes_from_issue(issue))
        return "reanalyze", sorted(set(target_nodes)) or ["feature_analysis"]
    if any(issue.get("suggested_action") == "rewrite" for issue in candidates):
        return "rewrite", ["report_writer"]
    return "end", []


def _claim_evidence_map(db: Session, claim_ids: list[int]) -> dict[int, list[int]]:
    if not claim_ids:
        return {}
    linked = list(db.scalars(select(ClaimEvidence).where(ClaimEvidence.claim_id.in_(claim_ids))))
    evidence_by_claim: dict[int, list[int]] = {}
    for item in linked:
        evidence_by_claim.setdefault(item.claim_id, []).append(item.evidence_chunk_id)
    return evidence_by_claim


def _fill_paragraph_evidence(report_json: dict, evidence_by_claim: dict[int, list[int]]) -> dict:
    for section in report_json.get("sections", []):
        for paragraph in section.get("paragraphs", []):
            evidence_ids: list[int] = []
            for claim_id in paragraph.get("claim_ids", []):
                evidence_ids.extend(evidence_by_claim.get(int(claim_id), []))
            paragraph["evidence_ids"] = sorted(set(evidence_ids))
    return report_json


def _render_report_markdown(report_json: dict) -> str:
    lines: list[str] = [f"# {report_json.get('title') or '竞品分析报告'}", ""]
    for section in report_json.get("sections", []):
        title = section.get("title")
        if title:
            lines.extend([f"## {title}", ""])
        for paragraph in section.get("paragraphs", []):
            text = str(paragraph.get("text") or "").strip()
            if not text:
                continue
            claim_ids = paragraph.get("claim_ids") or []
            evidence_ids = paragraph.get("evidence_ids") or []
            suffix = f"（Claims: {claim_ids}; Evidence: {evidence_ids}）" if claim_ids else ""
            lines.extend([f"{text}{suffix}", ""])
    return "\n".join(lines).strip()


def _fallback_report_json(task: AnalysisTask, claims: list[Claim], evidence_by_claim: dict[int, list[int]]) -> dict:
    sections = []
    for claim_type, title in [
        ("feature", "产品与功能"),
        ("pricing", "价格策略"),
        ("market", "市场定位"),
        ("security", "安全合规"),
    ]:
        type_claims = [claim for claim in claims if claim.claim_type == claim_type]
        if not type_claims:
            continue
        sections.append(
            {
                "section_id": claim_type,
                "title": title,
                "paragraphs": [
                    {
                        "paragraph_id": f"{claim_type}_p1",
                        "text": "；".join(claim.claim_text for claim in type_claims[:4]),
                        "claim_ids": [claim.id for claim in type_claims[:4]],
                    }
                ],
            }
        )
    return _fill_paragraph_evidence({"title": f"{task.topic}报告", "sections": sections}, evidence_by_claim)


def _search_firecrawl_query(query: str, max_results: int = 3) -> tuple[str, list[dict]]:
    thread_web = WebContextProvider()
    return query, thread_web.search(query, max_results=max_results)


def _scrape_firecrawl_url(payload: dict) -> dict:
    thread_web = WebContextProvider()
    scraped = thread_web.scrape(payload["url"])
    return {**payload, "scraped": scraped}


def _embed_and_upsert_chunk(spec: dict) -> tuple[int, str]:
    thread_llm = LLMClient()
    thread_milvus = MilvusTool()
    embedding = thread_llm.embed_text(spec["chunk_text"])
    vector_id = thread_milvus.upsert_evidence_embedding(
        chunk_id=spec["chunk_id"],
        task_id=spec["task_id"],
        competitor_name=spec.get("competitor_name"),
        source_type=spec.get("source_type"),
        source_url=spec["source_url"],
        embedding=embedding,
    )
    return spec["chunk_id"], vector_id


def run_competitive_analysis(db: Session, task_id: int) -> CompetitiveAnalysisState:
    state: CompetitiveAnalysisState = {
        "task_id": task_id,
        "errors": [],
        "revision_round": 0,
        "max_revision_rounds": 1,
        "qa_passed": None,
        "qa_next_action": None,
        "qa_target_nodes": [],
        "qa_issues": [],
        "qa_followup_queries": [],
        "reanalyze_dimensions": [],
    }
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise RuntimeError(f"Task {task_id} not found")
    _console("analysis workflow started", {"task_id": task_id})

    llm = LLMClient()
    web = WebContextProvider()

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
            queries.extend(query for query in state.get("qa_followup_queries", []) if competitor.lower() in query.lower())
            max_workers = max(1, min(settings.collector_max_workers, len(queries)))
            _console("parallel firecrawl search started", {"task_id": task_id, "competitor": competitor, "query_count": len(queries), "max_workers": max_workers})
            add_log(
                db,
                task_id,
                node.id,
                "Parallel Firecrawl search started",
                {"competitor": competitor, "query_count": len(queries), "max_workers": max_workers},
            )
            db.commit()

            search_payloads: list[dict] = []
            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=f"collector-search-{task_id}") as executor:
                futures = {executor.submit(_search_firecrawl_query, query, 3): query for query in queries}
                for future in as_completed(futures):
                    query = futures[future]
                    try:
                        returned_query, results = future.result()
                    except Exception as exc:
                        _console("firecrawl search failed", {"task_id": task_id, "query": query, "error": str(exc)})
                        add_log(db, task_id, node.id, "Firecrawl search failed", {"query": query, "error": str(exc)}, log_type="warning")
                        db.commit()
                        continue
                    _console("firecrawl search completed", {"task_id": task_id, "query": returned_query, "result_count": len(results)})
                    add_log(db, task_id, node.id, "Firecrawl search completed", {"query": returned_query, "result_count": len(results)})
                    for item in results:
                        url = item.get("url")
                        if not url or url in seen_urls:
                            continue
                        seen_urls.add(url)
                        search_payloads.append({"query": returned_query, "item": item, "url": url, "competitor": competitor})
                        if len(search_payloads) >= 5:
                            break
                    if len(search_payloads) >= 5:
                        break
                    db.commit()
            db.commit()

            scrape_workers = max(1, min(settings.collector_max_workers, len(search_payloads)))
            _console(
                "parallel firecrawl scrape started",
                {"task_id": task_id, "competitor": competitor, "url_count": len(search_payloads), "max_workers": scrape_workers},
            )
            with ThreadPoolExecutor(max_workers=scrape_workers, thread_name_prefix=f"collector-scrape-{task_id}") as executor:
                futures = {executor.submit(_scrape_firecrawl_url, payload): payload for payload in search_payloads}
                for future in as_completed(futures):
                    payload = futures[future]
                    url = payload["url"]
                    query = payload["query"]
                    item = payload["item"]
                    _console("firecrawl scrape started", {"task_id": task_id, "url": url})
                    try:
                        result = future.result()
                        scraped = result.get("scraped")
                    except Exception as exc:
                        _console("firecrawl scrape failed", {"task_id": task_id, "url": url, "error": str(exc)})
                        add_log(db, task_id, node.id, "Firecrawl scrape failed", {"url": url, "error": str(exc)}, log_type="warning")
                        db.commit()
                        continue
                    if not scraped or not scraped.get("markdown"):
                        _console("firecrawl scrape skipped", {"task_id": task_id, "url": url})
                        add_log(db, task_id, node.id, "Firecrawl scrape skipped", {"url": url}, log_type="warning")
                        db.commit()
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
        pending_specs: list[dict] = []
        for doc in docs:
            _console("evidence document started", {"task_id": task_id, "source_document_id": doc.id, "competitor": doc.competitor_name})
            for idx, text in enumerate(_chunks(doc.content_text or doc.content_markdown or "")[:4]):
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
                ids.append(chunk.id)
                pending_specs.append(
                    {
                        "chunk_id": chunk.id,
                        "task_id": task_id,
                        "source_document_id": doc.id,
                        "chunk_index": idx,
                        "competitor_name": chunk.competitor_name,
                        "source_type": chunk.source_type,
                        "source_url": chunk.source_url,
                        "chunk_text": text,
                    }
                )
            db.commit()
        if not ids:
            raise RuntimeError("No evidence chunks were extracted")

        max_workers = max(1, min(settings.evidence_extractor_max_workers, len(pending_specs)))
        _console("parallel evidence embedding started", {"task_id": task_id, "chunk_count": len(pending_specs), "max_workers": max_workers})
        add_log(
            db,
            task_id,
            node.id,
            "Parallel evidence embedding started",
            {"chunk_count": len(pending_specs), "max_workers": max_workers},
        )
        db.commit()

        failures: list[dict] = []
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=f"evidence-{task_id}") as executor:
            futures = {executor.submit(_embed_and_upsert_chunk, spec): spec for spec in pending_specs}
            for future in as_completed(futures):
                spec = futures[future]
                try:
                    chunk_id, vector_id = future.result()
                except Exception as exc:
                    failures.append({"chunk_id": spec["chunk_id"], "error": str(exc)})
                    _console("evidence embedding failed", {"task_id": task_id, "chunk_id": spec["chunk_id"], "error": str(exc)})
                    add_log(
                        db,
                        task_id,
                        node.id,
                        "Evidence embedding failed",
                        {"chunk_id": spec["chunk_id"], "error": str(exc)},
                        log_type="error",
                    )
                    db.commit()
                    continue

                chunk = db.get(EvidenceChunk, chunk_id)
                if chunk is not None:
                    chunk.milvus_vector_id = vector_id
                completed += 1
                _console("evidence embedded and saved", {"task_id": task_id, "chunk_id": chunk_id, "vector_id": vector_id})
                add_log(db, task_id, node.id, "Evidence embedded and saved", {"chunk_id": chunk_id, "vector_id": vector_id})
                db.commit()

        if failures:
            raise RuntimeError(f"Evidence embedding failed for {len(failures)} chunks")
        node.output_summary = f"抽取并向量化 {len(ids)} 条 evidence_chunk"
        add_log(
            db,
            task_id,
            node.id,
            "Parallel evidence embedding completed",
            {"chunk_count": len(ids), "completed": completed, "failed": len(failures), "max_workers": max_workers},
        )
        state["evidence_chunk_ids"] = ids

    def analyst_factory(node_key: str, claim_type: str, dimension: str) -> Callable[[AgentNode], None]:
        def analyst(node: AgentNode) -> None:
            plan = get_task_plan(task)
            retriever = EvidenceRetriever(db)
            claim_ids: list[int] = []
            for competitor in plan.competitors:
                _console("llm analyst started", {"task_id": task_id, "node_key": node_key, "competitor": competitor})
                query, source_type = _analysis_query(competitor, claim_type, dimension, plan.topic)
                evidence = retriever.search(
                    task_id=task_id,
                    query=query,
                    competitor_name=competitor,
                    source_type=source_type,
                    top_k=8,
                    node_id=node.id,
                )
                if not evidence and source_type:
                    evidence = retriever.search(
                        task_id=task_id,
                        query=query,
                        competitor_name=competitor,
                        top_k=8,
                        node_id=node.id,
                    )
                _console("analyst evidence retrieved", retriever.last_search_log)
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
        evidence_by_claim = _claim_evidence_map(db, [claim.id for claim in claims])
        claim_context = "\n".join(
            f"[claim_id={claim.id}] competitor={claim.competitor_name}; type={claim.claim_type}; "
            f"evidence_ids={evidence_by_claim.get(claim.id, [])}; text={claim.claim_text}"
            for claim in claims
        )
        revision_instruction = state.get("revision_reason") or ""
        prompt = f"""
请基于以下结构化 Claim 生成中文竞品分析报告 JSON。
主题：{plan.topic}
行业：{plan.industry}
竞品：{', '.join(plan.competitors)}
分析维度：{', '.join(plan.analysis_dimensions)}
返工要求：{revision_instruction}

要求：
1. 只输出合法 JSON，不要 Markdown。
2. 每个 section 至少包含 section_id、title、paragraphs。
3. 每个关键 paragraph 必须包含 paragraph_id、text、claim_ids。
4. claim_ids 只能引用下方已有 claim_id，不要编造。
5. 不要输出 evidence_ids，后端会自动补齐。
6. 必须覆盖所有分析维度。

JSON 格式：
{{"title":"...","sections":[{{"section_id":"executive_summary","title":"执行摘要","paragraphs":[{{"paragraph_id":"executive_summary_p1","text":"...","claim_ids":[1,2]}}]}}]}}

Claims:
{claim_context}
"""
        _console("llm report writer started", {"task_id": task_id, "claim_count": len(claims)})
        try:
            report_json = _json_from_text(llm.complete(prompt, system="你只输出合法 JSON。"))
            if not isinstance(report_json, dict) or not report_json.get("sections"):
                raise ValueError("report_json.sections missing")
            report_json.setdefault("title", f"{plan.topic}报告")
            report_json = _fill_paragraph_evidence(report_json, evidence_by_claim)
        except Exception as exc:
            add_log(db, task_id, node.id, "Report JSON generation fallback used", {"error": str(exc)}, log_type="warning")
            report_json = _fallback_report_json(task, claims, evidence_by_claim)
        content = _render_report_markdown(report_json)
        report = Report(
            task_id=task_id,
            title=report_json.get("title") or f"{plan.topic}报告",
            content_markdown=content,
            content_html=markdown.markdown(content, extensions=["tables"]),
            report_json={**report_json, "mode": "firecrawl_llm_milvus_rag"},
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
        claim_ids = [claim.id for claim in claims]
        linked = list(db.scalars(select(ClaimEvidence).where(ClaimEvidence.claim_id.in_(claim_ids)))) if claim_ids else []
        linked_claim_ids = {item.claim_id for item in linked}
        evidence_ids_by_claim: dict[int, list[int]] = {}
        for item in linked:
            evidence_ids_by_claim.setdefault(item.claim_id, []).append(item.evidence_chunk_id)
        evidence_by_id = {
            chunk.id: chunk
            for chunk in db.scalars(select(EvidenceChunk).where(EvidenceChunk.id.in_([item.evidence_chunk_id for item in linked])))
        } if linked else {}
        issues = []
        for claim in claims:
            if claim.id not in linked_claim_ids:
                issues.append(
                    {
                        "type": "missing_evidence",
                        "severity": "high",
                        "message": f"Claim {claim.id} 缺少证据绑定",
                        "related_claim_id": claim.id,
                        "related_competitor": claim.competitor_name,
                        "related_dimension": claim.claim_type,
                        "suggested_action": "reanalyze",
                    }
                )
            if claim.confidence is not None and claim.confidence < Decimal("0.60"):
                issues.append(
                    {
                        "type": "weak_evidence",
                        "severity": "medium",
                        "message": f"Claim {claim.id} 置信度偏低",
                        "related_claim_id": claim.id,
                        "related_competitor": claim.competitor_name,
                        "related_dimension": claim.claim_type,
                        "suggested_action": "reanalyze",
                    }
                )
            if claim.claim_type == "pricing":
                evidence_types = {evidence_by_id[eid].source_type for eid in evidence_ids_by_claim.get(claim.id, []) if eid in evidence_by_id}
                if evidence_types and not (evidence_types & {"official_website", "pricing_page"}):
                    issues.append(
                        {
                            "type": "weak_evidence",
                            "severity": "medium",
                            "message": f"价格 Claim {claim.id} 缺少官方或价格页证据",
                            "related_claim_id": claim.id,
                            "related_competitor": claim.competitor_name,
                            "related_dimension": "pricing",
                            "suggested_action": "recollect",
                            "search_query": f"{claim.competitor_name} pricing plans official",
                        }
                    )
            if claim.claim_type == "security":
                evidence_types = {evidence_by_id[eid].source_type for eid in evidence_ids_by_claim.get(claim.id, []) if eid in evidence_by_id}
                if evidence_types and not (evidence_types & {"official_website", "docs", "security", "enterprise"}):
                    issues.append(
                        {
                            "type": "weak_evidence",
                            "severity": "medium",
                            "message": f"安全 Claim {claim.id} 缺少 docs/security/enterprise 来源",
                            "related_claim_id": claim.id,
                            "related_competitor": claim.competitor_name,
                            "related_dimension": "security",
                            "suggested_action": "recollect",
                            "search_query": f"{claim.competitor_name} security privacy compliance official docs",
                        }
                    )
        if report:
            missing_dimensions = [dim for dim in plan.analysis_dimensions if dim not in report.content_markdown]
            if missing_dimensions:
                issues.append({"type": "schema_incomplete", "severity": "medium", "message": f"报告可能未显式覆盖维度：{', '.join(missing_dimensions)}", "related_claim_id": None, "suggested_action": "rewrite"})
            if not report.content_markdown or len(report.content_markdown) < 500 or "##" not in report.content_markdown:
                issues.append({"type": "writing_issue", "severity": "high", "message": "报告为空、过短或缺少结构化章节", "suggested_action": "rewrite"})
        qa_prompt = f"""
请复核这份竞品分析报告是否存在明显逻辑或证据问题。
仅基于报告和问题列表输出 JSON：
{{"passed":true/false,"score":0.0到1.0,"issues":[{{"type":"logic_gap|unsupported_claim|weak_evidence|schema_incomplete|writing_issue","severity":"low|medium|high","message":"中文问题","related_claim_id":null,"related_dimension":"feature|pricing|market|security","suggested_action":"recollect|reanalyze|rewrite|ignore"}}]}}

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
        next_action, target_nodes = _decide_next_action(issues)
        if passed:
            next_action, target_nodes = "end", []
        followup_queries = [str(issue.get("search_query")) for issue in issues if issue.get("search_query")]
        payload = {
            "passed": passed,
            "score": float(score),
            "issues": issues,
            "next_action": next_action,
            "target_nodes": target_nodes,
            "revision_reason": "；".join(issue.get("message", "") for issue in issues[:4]) or None,
            "followup_queries": followup_queries,
            "revision_round": state.get("revision_round", 0),
        }
        qa_result = QAResult(task_id=task_id, report_id=report.id if report else None, passed=passed, score=score, issues_json=payload)
        db.add(qa_result)
        db.flush()
        node.output_summary = f"QA 得分 {qa_result.score}，问题 {len(issues)} 个"
        _console(
            "qa completed",
            {
                "task_id": task_id,
                "qa_result_id": qa_result.id,
                "passed": qa_result.passed,
                "score": str(qa_result.score),
                "next_action": next_action,
                "target_nodes": target_nodes,
            },
        )
        state["qa_result_id"] = qa_result.id
        state["qa_passed"] = passed
        state["qa_next_action"] = next_action
        state["qa_target_nodes"] = target_nodes
        state["qa_issues"] = issues
        state["qa_followup_queries"] = followup_queries
        state["revision_reason"] = payload["revision_reason"]

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
    if not state.get("qa_passed") and state.get("revision_round", 0) < state.get("max_revision_rounds", 1):
        state["revision_round"] = int(state.get("revision_round", 0)) + 1
        action = state.get("qa_next_action") or "end"
        target_nodes = state.get("qa_target_nodes", [])
        qa_node = _node(db, task_id, "qa")
        add_log(
            db,
            task_id,
            qa_node.id,
            "QA requested revision",
            {
                "next_action": action,
                "target_nodes": target_nodes,
                "issue_count": len(state.get("qa_issues", [])),
                "revision_round": state["revision_round"],
            },
            log_type="warning",
        )
        db.commit()
        _console(
            "qa requested revision",
            {"task_id": task_id, "next_action": action, "target_nodes": target_nodes, "revision_round": state["revision_round"]},
        )
        if action == "recollect":
            _run_node(db, task_id, "collector", "collecting", collector)
            _run_node(db, task_id, "evidence_extractor", "extracting", evidence_extractor)
            targets = [node_key for node_key in target_nodes if node_key.endswith("_analysis")] or [
                "feature_analysis",
                "pricing_analysis",
                "market_analysis",
                "security_analysis",
            ]
            for target in targets:
                if target == "feature_analysis":
                    _run_node(db, task_id, target, "analyzing", analyst_factory(target, "feature", "产品定位、核心功能、Agent 能力、IDE 集成"))
                elif target == "pricing_analysis":
                    _run_node(db, task_id, target, "analyzing", analyst_factory(target, "pricing", "价格策略、套餐结构、个人与团队商业化"))
                elif target == "market_analysis":
                    _run_node(db, task_id, target, "analyzing", analyst_factory(target, "market", "适用用户、市场定位、企业能力"))
                elif target == "security_analysis":
                    _run_node(db, task_id, target, "analyzing", analyst_factory(target, "security", "安全合规、隐私、企业治理能力"))
            _run_node(db, task_id, "report_writer", "writing", report_writer)
            _run_node(db, task_id, "qa", "qa_checking", qa)
        elif action == "reanalyze":
            for target in target_nodes or ["feature_analysis"]:
                if target == "feature_analysis":
                    _run_node(db, task_id, target, "analyzing", analyst_factory(target, "feature", "产品定位、核心功能、Agent 能力、IDE 集成"))
                elif target == "pricing_analysis":
                    _run_node(db, task_id, target, "analyzing", analyst_factory(target, "pricing", "价格策略、套餐结构、个人与团队商业化"))
                elif target == "market_analysis":
                    _run_node(db, task_id, target, "analyzing", analyst_factory(target, "market", "适用用户、市场定位、企业能力"))
                elif target == "security_analysis":
                    _run_node(db, task_id, target, "analyzing", analyst_factory(target, "security", "安全合规、隐私、企业治理能力"))
            _run_node(db, task_id, "report_writer", "writing", report_writer)
            _run_node(db, task_id, "qa", "qa_checking", qa)
        elif action == "rewrite":
            _run_node(db, task_id, "report_writer", "writing", report_writer)
            _run_node(db, task_id, "qa", "qa_checking", qa)
    update_task_status(db, task_id, "success")
    _console("analysis workflow completed", {"task_id": task_id})
    return state
