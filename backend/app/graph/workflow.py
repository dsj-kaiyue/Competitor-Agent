from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from decimal import Decimal
import json
import logging
import re
from time import perf_counter

import markdown
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.timezone import now_bj
from app.graph.state import CompetitiveAnalysisState
from app.models.agent_node import AgentNode
from app.models.analysis_task import AnalysisTask
from app.models.claim import Claim
from app.models.claim_evidence import ClaimEvidence
from app.models.comparison_matrix import ComparisonMatrix
from app.models.competitor_profile import CompetitorProfile
from app.models.evidence_chunk import EvidenceChunk
from app.models.qa_result import QAResult
from app.models.report import Report
from app.models.source_document import SourceDocument
from app.services.comparison_matrix_service import ComparisonMatrixService
from app.services.competitor_profile_service import CompetitorProfileService
from app.services.evidence_retriever import EvidenceRetriever
from app.services.log_service import add_log
from app.services.profile_schema_builder import ProfileSchemaBuilder
from app.services.task_service import build_dimension_node_specs, ensure_dimension_nodes, get_task_plan, update_task_status
from app.tools.llm_client import LLMClient
from app.tools.milvus_tool import MilvusTool
from app.tools.web_context_provider import WebContextProvider


logger = logging.getLogger("competitive-agent")

class TaskControlException(Exception):
    pass


class TaskPaused(TaskControlException):
    pass


class TaskCanceled(TaskControlException):
    pass


def _console(message: str, payload: dict | None = None) -> None:
    suffix = f" | {json.dumps(payload, ensure_ascii=False)}" if payload else ""
    logger.info("%s%s", message, suffix)


def _node(db: Session, task_id: int, node_key: str) -> AgentNode:
    node = db.scalar(select(AgentNode).where(AgentNode.task_id == task_id, AgentNode.node_key == node_key))
    if node is None:
        raise RuntimeError(f"Missing DAG node: {node_key}")
    return node


def _check_task_control(db: Session, task_id: int, node: AgentNode | None = None) -> None:
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise RuntimeError(f"Task {task_id} not found")
    db.refresh(task)
    if task.status in {"cancel_requested", "canceled"}:
        task.status = "canceled"
        task.error_message = "任务已取消"
        task.updated_at = now_bj()
        if node is not None:
            add_log(db, task_id, node.id, f"{node.node_name} canceled", log_type="warning")
        db.commit()
        _console("analysis workflow canceled", {"task_id": task_id, "node_key": node.node_key if node else None})
        raise TaskCanceled("任务已取消")
    if task.status in {"pause_requested", "paused"}:
        task.status = "paused"
        task.error_message = "任务已暂停"
        task.updated_at = now_bj()
        if node is not None:
            add_log(db, task_id, node.id, f"{node.node_name} paused", log_type="warning")
        db.commit()
        _console("analysis workflow paused", {"task_id": task_id, "node_key": node.node_key if node else None})
        raise TaskPaused("任务已暂停")


def _run_node(
    db: Session,
    task_id: int,
    node_key: str,
    task_status: str,
    fn: Callable[[AgentNode], None],
    *,
    force: bool = False,
) -> None:
    node = _node(db, task_id, node_key)
    _check_task_control(db, task_id, node)
    if node.status == "success" and not force:
        _console("node skipped because already completed", {"task_id": task_id, "node_key": node_key})
        add_log(db, task_id, node.id, f"{node.node_name} skipped because it already completed")
        db.commit()
        return
    update_task_status(db, task_id, task_status)
    started = now_bj()
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
        _check_task_control(db, task_id, node)
        ended = now_bj()
        node.status = "success"
        node.ended_at = ended
        node.duration_ms = int((ended - started).total_seconds() * 1000)
        add_log(db, task_id, node.id, f"{node.node_name} completed")
        db.commit()
        _console("node completed", {"task_id": task_id, "node_key": node_key, "duration_ms": node.duration_ms})
    except TaskPaused:
        ended = now_bj()
        node.status = "paused"
        node.ended_at = ended
        node.duration_ms = int((ended - started).total_seconds() * 1000)
        node.error_message = "任务已暂停"
        db.commit()
        raise
    except TaskCanceled:
        ended = now_bj()
        node.status = "canceled"
        node.ended_at = ended
        node.duration_ms = int((ended - started).total_seconds() * 1000)
        node.error_message = "任务已取消"
        db.commit()
        raise
    except Exception as exc:
        ended = now_bj()
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


def _fixed_size_chunks(text: str, size: int = 1400, overlap: int = 180) -> list[str]:
    clean = _strip_markdown(text)
    if not clean:
        return []
    result = []
    start = 0
    step = max(1, size - overlap)
    while start < len(clean):
        result.append(clean[start : start + size])
        start += step
    return result


def _looks_like_noise_line(line: str) -> bool:
    compact = line.strip()
    if not compact:
        return False
    lowered = compact.lower()
    noise_markers = [
        "window.",
        "ytcfg",
        "wiz_global_data",
        "var ",
        "function(",
        "function ",
        "data:image",
        "<script",
        "__next_data__",
    ]
    if any(marker in lowered for marker in noise_markers) and len(compact) > 160:
        return True
    if len(compact) > 1200 and compact.count("{") + compact.count("[") > 20:
        return True
    return False


def _clean_markdown_for_chunking(markdown_text: str) -> str:
    text = (markdown_text or "").replace("\r\n", "\n").replace("\r", "\n")

    def clean_fence(match: re.Match) -> str:
        body = match.group(1) or ""
        lowered = body.lower()
        if len(body) > 1200 or any(marker in lowered for marker in ("window.", "ytcfg", "function(", "<script")):
            return "\n"
        return f"\n{body.strip()}\n"

    text = re.sub(r"```(?:[a-zA-Z0-9_-]+)?\s*(.*?)```", clean_fence, text, flags=re.S)
    cleaned_lines = [line.rstrip() for line in text.splitlines() if not _looks_like_noise_line(line)]
    text = "\n".join(cleaned_lines)
    text = re.sub(r"!\[[^\]]*]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)]\([^)]*\)", r"\1", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_markdown_block(text: str) -> str:
    text = re.sub(r"^\s*[-*+]\s+", "- ", text, flags=re.M)
    text = re.sub(r"^\s*(\d+)[.)]\s+", r"\1. ", text, flags=re.M)
    text = re.sub(r"[>*_`|]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_low_value_chunk_unit(text: str) -> bool:
    lowered = text.lower().strip()
    if not lowered:
        return True
    low_value_markers = [
        "skip to main content",
        "跳转到主要内容",
        "documentation index",
        "fetch the complete documentation index",
        "use this file to discover all available pages",
        "link to section",
        "link to ",
        "复制 markdown",
        "打印",
        "反馈",
        "目录",
    ]
    if any(marker in lowered for marker in low_value_markers):
        return True
    if len(text) < 12 and not re.search(r"[\d$¥%]|[\u4e00-\u9fff]{2,}", text):
        return True
    return False


def _split_long_text(text: str, size: int, overlap: int) -> list[str]:
    if len(text) <= size:
        return [text]
    sentences = [item.strip() for item in re.split(r"(?<=[。！？.!?])\s+", text) if item.strip()]
    if len(sentences) <= 1:
        return _fixed_size_chunks(text, size=size, overlap=overlap)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > size:
            chunks.append(current)
            tail = current[-overlap:].strip() if overlap > 0 else ""
            current = f"{tail} {sentence}".strip() if tail else sentence
        else:
            current = f"{current} {sentence}".strip() if current else sentence
    if current:
        chunks.append(current)
    return chunks


def _markdown_units(markdown_text: str) -> tuple[list[str], int]:
    heading_stack: list[tuple[int, str]] = []
    paragraph_lines: list[str] = []
    units: list[str] = []
    heading_count = 0

    def heading_path() -> str:
        return " > ".join(title for _, title in heading_stack if title)

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        raw = "\n".join(paragraph_lines).strip()
        paragraph_lines.clear()
        plain = _clean_markdown_block(raw)
        if not plain or _is_low_value_chunk_unit(plain):
            return
        path = heading_path()
        units.append(f"{path}\n{plain}" if path else plain)

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            flush_paragraph()
            level = len(match.group(1))
            title = _clean_markdown_block(match.group(2))
            if title:
                heading_count += 1
                heading_stack = [(item_level, item_title) for item_level, item_title in heading_stack if item_level < level]
                heading_stack.append((level, title))
            continue
        if not line.strip():
            flush_paragraph()
            continue
        paragraph_lines.append(line)
    flush_paragraph()
    return units, heading_count


def _chunks(text: str, size: int = 1400, overlap: int = 180) -> list[str]:
    markdown_text = _clean_markdown_for_chunking(text)
    if not markdown_text:
        return []
    units, heading_count = _markdown_units(markdown_text)
    if heading_count == 0 and len(units) < 3:
        return _fixed_size_chunks(markdown_text, size=size, overlap=overlap)
    chunks: list[str] = []
    current = ""
    for unit in units:
        if len(unit) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_text(unit, size=size, overlap=overlap))
            continue
        if current and len(current) + len(unit) + 2 > size:
            chunks.append(current)
            current = unit
        else:
            current = f"{current}\n\n{unit}".strip() if current else unit
    if current:
        chunks.append(current)
    return chunks or _fixed_size_chunks(markdown_text, size=size, overlap=overlap)



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


def _parse_llm_json_with_repair(llm: LLMClient, raw: str, original_prompt: str, *, expected: str) -> object:
    try:
        return _json_from_text(raw)
    except Exception as first_exc:
        repair_prompt = f"""
上一次模型输出不是合法 JSON，解析失败：{first_exc}

请把下面内容修正为合法 JSON。
要求：
1. 只输出合法 JSON，不要 Markdown，不要解释。
2. 期望 JSON 类型：{expected}
3. 如果原内容为空或无法修复，请基于原始任务 prompt 输出一个空 JSON 数组 []。

原始任务 prompt：
{original_prompt[-5000:]}

上一次模型输出：
{(raw or '')[:5000]}
"""
        repaired = llm.complete(repair_prompt, system="你只输出合法 JSON。")
        return _json_from_text(repaired)


def _evidence_context(chunks: list[EvidenceChunk], limit: int = 10) -> str:
    lines = []
    for chunk in chunks[:limit]:
        lines.append(
            f"[evidence_id={chunk.id}] competitor={chunk.competitor_name}; source_type={chunk.source_type}; "
            f"title={chunk.source_title}; url={chunk.source_url}; text={chunk.chunk_text[:900]}"
        )
    return "\n".join(lines)


def _dimension_analysis_query(competitor: str, prompt_spec: dict, topic: str) -> tuple[str, str | None]:
    dimension_label = prompt_spec.get("dimension_label") or prompt_spec.get("label") or ""
    focus_terms = " ".join(str(item) for item in prompt_spec.get("evidence_focus", [])[:5])
    source_type = None
    lowered = f"{dimension_label} {focus_terms}".lower()
    if "pricing" in lowered or "价格" in lowered or "billing" in lowered:
        source_type = "pricing_page"
    query = f"{competitor} {dimension_label} {focus_terms} {topic} official docs".strip()
    return query, source_type


def _fallback_dimension_prompt_spec(task_plan: dict, field: dict) -> dict:
    label = str(field.get("label") or field.get("key") or "").strip()
    key = str(field.get("key") or label).strip()
    topic = str(task_plan.get("industry") or task_plan.get("topic") or "").strip()
    return {
        "dimension_key": key,
        "dimension_label": label,
        "analysis_goal": f"围绕“{label}”比较所有竞品在能力、差异、限制和证据支撑上的表现。",
        "evidence_focus": field.get("source_requirements") or ["official_website", "docs", "blog"],
        "must_answer": [
            f"各竞品在“{label}”上的明确能力或策略是什么",
            "这些结论分别由哪些 evidence 支撑",
            "是否存在缺失、限制或不确定信息",
        ],
        "comparison_criteria": [label, "证据强度", "差异化", "风险或限制"],
        "search_query_template": f"{{competitor}} {topic} {label} official docs".strip(),
        "output_schema": "claims[] with competitor_name, dimension_key, dimension_label, claim_text, evidence_ids, confidence, risk_level",
        "industry": task_plan.get("industry"),
        "topic": task_plan.get("topic"),
    }


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = re.sub(r"\s+", " ", str(value or "").strip()).casefold()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(str(value).strip())
    return result


def _format_dimension_search_query(plan, competitor: str, prompt_spec: dict) -> str:
    dimension_label = str(prompt_spec.get("dimension_label") or prompt_spec.get("label") or "").strip()
    template = str(prompt_spec.get("search_query_template") or "").strip()
    if not template:
        template = "{competitor} {industry_or_topic} {dimension_label} official docs"
    template = template.replace("{{competitor}}", "{competitor}")
    values = {
        "competitor": competitor,
        "industry": plan.industry or "",
        "topic": plan.topic or "",
        "industry_or_topic": plan.industry or plan.topic or "",
        "target_product": plan.target_product or "",
        "dimension_key": prompt_spec.get("dimension_key") or "",
        "dimension_label": dimension_label,
    }
    try:
        query = template.format(**values)
    except Exception:
        query = f"{competitor} {plan.industry or plan.topic} {dimension_label} official docs"
    query = re.sub(r"\s+", " ", query).strip()
    if competitor.casefold() not in query.casefold():
        query = f"{competitor} {query}".strip()
    return query


def _target_nodes_from_issue(issue: dict) -> list[str]:
    target_node = issue.get("target_node")
    if target_node:
        return [target_node]
    return []


def _decide_next_action(issues: list[dict]) -> tuple[str, list[str]]:
    high_issues = [issue for issue in issues if issue.get("severity") == "high"]
    candidates = high_issues or issues
    if any(issue.get("suggested_action") == "recollect" for issue in candidates):
        target_nodes: list[str] = []
        for issue in candidates:
            target_nodes.extend(_target_nodes_from_issue(issue))
        return "recollect", sorted(set(target_nodes))
    if any(issue.get("suggested_action") == "reanalyze" for issue in candidates):
        target_nodes: list[str] = []
        for issue in candidates:
            target_nodes.extend(_target_nodes_from_issue(issue))
        return "reanalyze", sorted(set(target_nodes))
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
    dimension_labels = []
    for claim in claims:
        label = claim.dimension_label or claim.claim_type or "结构化结论"
        if label not in dimension_labels:
            dimension_labels.append(label)
    for label in dimension_labels:
        dimension_claims = [claim for claim in claims if (claim.dimension_label or claim.claim_type or "结构化结论") == label]
        if not dimension_claims:
            continue
        sections.append(
            {
                "section_id": re.sub(r"\W+", "_", label.lower()).strip("_") or "dimension",
                "title": label,
                "paragraphs": [
                    {
                        "paragraph_id": f"dimension_{len(sections) + 1}_p1",
                        "text": "；".join(claim.claim_text for claim in dimension_claims[:4]),
                        "claim_ids": [claim.id for claim in dimension_claims[:4]],
                    }
                ],
            }
        )
    return _fill_paragraph_evidence({"title": f"{task.topic}报告", "sections": sections}, evidence_by_claim)


def _section_claim_ids(section: dict) -> set[int]:
    claim_ids: set[int] = set()
    for paragraph in section.get("paragraphs", []) if isinstance(section, dict) else []:
        for claim_id in paragraph.get("claim_ids", []) if isinstance(paragraph, dict) else []:
            try:
                claim_ids.add(int(claim_id))
            except (TypeError, ValueError):
                continue
    return claim_ids


def _normalized_token(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _section_matches_alias(section: dict, aliases: set[str]) -> bool:
    text = _normalized_token(f"{section.get('section_id') or ''} {section.get('title') or ''}")
    return any(alias and len(alias) >= 2 and alias in text for alias in aliases)


def _is_global_report_section(section: dict) -> bool:
    text = _normalized_token(f"{section.get('section_id') or ''} {section.get('title') or ''}")
    keywords = (
        "executive",
        "summary",
        "overview",
        "conclusion",
        "recommend",
        "ranking",
        "takeaway",
        "摘要",
        "执行摘要",
        "总览",
        "概览",
        "总体",
        "总结",
        "结论",
        "建议",
        "推荐",
        "排名",
    )
    return any(keyword in text for keyword in keywords)


def _sanitize_report_sections(report_json: dict, valid_claim_ids: set[int]) -> dict:
    sections = []
    seen_section_ids: set[str] = set()
    for section_index, raw_section in enumerate(report_json.get("sections", []), start=1):
        if not isinstance(raw_section, dict):
            continue
        section = dict(raw_section)
        section_id = str(section.get("section_id") or f"section_{section_index}").strip() or f"section_{section_index}"
        original_section_id = section_id
        suffix = 2
        while section_id in seen_section_ids:
            section_id = f"{original_section_id}_{suffix}"
            suffix += 1
        seen_section_ids.add(section_id)
        section["section_id"] = section_id
        section["title"] = str(section.get("title") or section_id).strip() or section_id
        paragraphs = []
        for paragraph_index, raw_paragraph in enumerate(section.get("paragraphs", []), start=1):
            if not isinstance(raw_paragraph, dict):
                continue
            text = str(raw_paragraph.get("text") or "").strip()
            if not text:
                continue
            claim_ids = []
            for claim_id in raw_paragraph.get("claim_ids") or []:
                try:
                    numeric_id = int(claim_id)
                except (TypeError, ValueError):
                    continue
                if numeric_id in valid_claim_ids and numeric_id not in claim_ids:
                    claim_ids.append(numeric_id)
            paragraphs.append(
                {
                    "paragraph_id": str(raw_paragraph.get("paragraph_id") or f"{section_id}_p{paragraph_index}"),
                    "text": text,
                    "claim_ids": claim_ids,
                }
            )
        section["paragraphs"] = paragraphs
        if paragraphs:
            sections.append(section)
    return {**report_json, "sections": sections}


def _search_firecrawl_query(query: str, max_results: int = 3) -> tuple[str, list[dict]]:
    thread_web = WebContextProvider()
    return query, thread_web.search(query, max_results=max_results)


def _scrape_firecrawl_url(payload: dict) -> dict:
    thread_web = WebContextProvider()
    scraped = thread_web.scrape(payload["url"])
    return {**payload, "scraped": scraped}


def _batched(items: list[dict], batch_size: int) -> list[list[dict]]:
    size = max(1, batch_size)
    return [items[index : index + size] for index in range(0, len(items), size)]


def _embed_chunk_batch(batch: list[dict]) -> tuple[list[dict], list[dict], int]:
    thread_llm = LLMClient()
    started = perf_counter()
    failures: list[dict] = []
    try:
        embeddings = thread_llm.embed_texts([spec["chunk_text"] for spec in batch])
    except Exception as exc:
        if len(batch) <= 1:
            elapsed_ms = int((perf_counter() - started) * 1000)
            return [], [{"chunk_id": batch[0]["chunk_id"], "error": str(exc)}], elapsed_ms
        embedded: list[dict] = []
        for spec in batch:
            try:
                single_embedding = thread_llm.embed_text(spec["chunk_text"])
                embedded.append({**spec, "embedding": single_embedding})
            except Exception as single_exc:
                failures.append({"chunk_id": spec["chunk_id"], "error": str(single_exc)})
        elapsed_ms = int((perf_counter() - started) * 1000)
        return embedded, failures, elapsed_ms
    elapsed_ms = int((perf_counter() - started) * 1000)
    embedded: list[dict] = []
    for spec, embedding in zip(batch, embeddings, strict=False):
        embedded.append({**spec, "embedding": embedding})
    return embedded, failures, elapsed_ms


def _run_dimension_analyst_logic(db: Session, task_id: int, node: AgentNode, prompt_spec: dict) -> list[int]:
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise RuntimeError(f"Task {task_id} not found")
    plan = get_task_plan(task)
    retriever = EvidenceRetriever(db)
    llm = LLMClient()
    claim_ids: list[int] = []
    no_evidence_competitors: list[str] = []
    dimension_key = str(prompt_spec.get("dimension_key") or "").strip()
    dimension_label = str(prompt_spec.get("dimension_label") or dimension_key).strip()
    if not dimension_key or not dimension_label:
        raise RuntimeError(f"{node.node_key} missing dimension prompt spec")
    for competitor in plan.competitors:
        _check_task_control(db, task_id, node)
        _console(
            "dimension analyst started",
            {"task_id": task_id, "node_key": node.node_key, "competitor": competitor, "dimension": dimension_label},
        )
        query, source_type = _dimension_analysis_query(competitor, prompt_spec, plan.topic)
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
        if not evidence:
            no_evidence_competitors.append(competitor)
            add_log(
                db,
                task_id,
                node.id,
                "Dimension analyst skipped competitor because no evidence was retrieved",
                {"competitor": competitor, "dimension_key": dimension_key, "dimension_label": dimension_label, "query": query},
                log_type="warning",
            )
            db.commit()
            continue
        must_answer = "\n".join(f"- {item}" for item in prompt_spec.get("must_answer", [])[:8])
        criteria = "、".join(str(item) for item in prompt_spec.get("comparison_criteria", [])[:8])
        prompt = f"""
你是一个动态维度竞品分析 Agent。你只负责一个分析维度，不要分析其它维度。
当前维度 key：{dimension_key}
当前维度名称：{dimension_label}
分析目标：{prompt_spec.get("analysis_goal") or f"分析 {dimension_label}"}
比较标准：{criteria}
必须回答：
{must_answer}

竞品：{competitor}
分析主题：{plan.topic}
证据：
{_evidence_context(evidence, limit=12)}

输出 JSON 数组，最多 3 条。每条格式：
{{"competitor_name":"{competitor}","dimension_key":"{dimension_key}","dimension_label":"{dimension_label}","claim_text":"中文结论，必须具体且可被证据支撑","evidence_ids":[数字ID],"confidence":0.0到1.0,"risk_level":"low|medium|high"}}
不要输出 JSON 之外的内容。
"""
        raw = llm.complete(prompt, system="你只输出合法 JSON，不编造证据。")
        try:
            parsed = _parse_llm_json_with_repair(llm, raw, prompt, expected="JSON array")
        except Exception as exc:
            add_log(
                db,
                task_id,
                node.id,
                "Dimension analyst JSON parsing failed for competitor",
                {"competitor": competitor, "dimension": dimension_label, "error": str(exc), "raw_preview": (raw or "")[:500]},
                log_type="warning",
            )
            _console(
                "dimension analyst json parse failed",
                {"task_id": task_id, "node_key": node.node_key, "competitor": competitor, "error": str(exc)},
            )
            db.commit()
            raise RuntimeError(
                f"{dimension_label}分析 Agent 在分析 {competitor} 时返回了无法解析的 JSON：{exc}"
            ) from exc
        if isinstance(parsed, dict):
            parsed = parsed.get("claims", [])
        if not isinstance(parsed, list):
            add_log(
                db,
                task_id,
                node.id,
                "Dimension analyst returned non-list JSON",
                {"competitor": competitor, "dimension": dimension_label, "json_type": type(parsed).__name__},
                log_type="warning",
            )
            db.commit()
            raise RuntimeError(
                f"{dimension_label}分析 Agent 在分析 {competitor} 时返回了错误 JSON 类型：{type(parsed).__name__}"
            )
        if not parsed:
            raise RuntimeError(f"{dimension_label}分析 Agent 在已有 evidence 的情况下未返回 Claim：{competitor}")
        created_for_competitor = 0
        for item in parsed[:3]:
            evidence_ids = [int(eid) for eid in item.get("evidence_ids", []) if str(eid).isdigit()]
            valid_ids = [eid for eid in evidence_ids if any(chunk.id == eid for chunk in evidence)]
            if not valid_ids and evidence:
                valid_ids = [evidence[0].id]
            claim = Claim(
                task_id=task_id,
                agent_node_id=node.id,
                competitor_name=str(item.get("competitor_name") or competitor),
                claim_type=dimension_key,
                dimension_key=dimension_key,
                dimension_label=dimension_label,
                dimension_prompt_json=prompt_spec,
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
            created_for_competitor += 1
        if created_for_competitor == 0:
            db.commit()
            raise RuntimeError(f"{dimension_label}分析 Agent 在已有 evidence 的情况下没有生成可用 Claim：{competitor}")
        _console(
            "dimension analyst completed",
            {
                "task_id": task_id,
                "node_key": node.node_key,
                "competitor": competitor,
                "dimension": dimension_label,
                "claim_count_so_far": len(claim_ids),
            },
        )
        db.commit()
    if not claim_ids:
        if no_evidence_competitors and len(no_evidence_competitors) == len(plan.competitors):
            node.output_summary = f"{dimension_label}维度没有检索到可用 evidence，已跳过"
            add_log(
                db,
                task_id,
                node.id,
                "Dimension analyst skipped because no evidence was retrieved",
                {
                    "dimension_key": dimension_key,
                    "dimension_label": dimension_label,
                    "competitors": no_evidence_competitors,
                },
                log_type="warning",
            )
            db.commit()
            return []
        add_log(
            db,
            task_id,
            node.id,
            "Dimension analyst produced no claims",
            {"dimension_key": dimension_key, "dimension_label": dimension_label},
            log_type="warning",
        )
        db.commit()
        raise RuntimeError(f"{dimension_label}分析 Agent 已检索到 evidence，但没有生成任何 Claim")
    node.output_summary = f"{dimension_label}维度生成 {len(claim_ids)} 条 Claim"
    return claim_ids


def run_competitive_analysis(db: Session, task_id: int) -> CompetitiveAnalysisState:
    state: CompetitiveAnalysisState = {
        "task_id": task_id,
        "errors": [],
        "revision_round": 0,
        "max_revision_rounds": max(0, settings.qa_max_revision_rounds),
        "qa_passed": None,
        "qa_next_action": None,
        "qa_target_nodes": [],
        "qa_issues": [],
        "qa_followup_queries": [],
        "reanalyze_dimensions": [],
        "dimension_failures": [],
    }
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise RuntimeError(f"Task {task_id} not found")
    if db.scalar(select(AgentNode).where(AgentNode.task_id == task_id, AgentNode.node_key == "report_finalizer")) is None:
        db.add(
            AgentNode(
                task_id=task_id,
                node_key="report_finalizer",
                node_name="报告总结 Agent",
                node_type="report_finalizer",
                status="pending",
            )
        )
        db.commit()
    _console("analysis workflow started", {"task_id": task_id})

    llm = LLMClient()
    web = WebContextProvider()

    def planner(node: AgentNode) -> None:
        plan = get_task_plan(task)
        task.task_plan_json = plan.model_dump()
        task.topic = plan.topic
        task.industry = plan.industry
        task.target_product = plan.target_product
        task.report_depth = plan.report_depth
        task.output_language = plan.output_language
        node.input_summary = task.user_input[:300]
        node.output_summary = f"确认任务计划：{len(plan.competitors)} 个竞品、{len(plan.analysis_dimensions)} 个分析维度"
        state["task_plan"] = plan.model_dump()
        state["competitors"] = plan.competitors
        state["analysis_dimensions"] = plan.analysis_dimensions

    def dimension_planner(node: AgentNode) -> None:
        plan = get_task_plan(task)
        dimension_nodes = ensure_dimension_nodes(db, task, plan)
        schema = ProfileSchemaBuilder().build_schema(plan.model_dump())
        fields = schema.get("fields", [])
        fallback_specs = {
            str(field.get("key")): _fallback_dimension_prompt_spec(plan.model_dump(), field)
            for field in fields
            if field.get("key")
        }
        prompt = f"""
你是 Dimension Prompt Planner Agent。请为每一个分析维度生成专属 prompt spec，供后续独立维度分析 Agent 使用。

任务主题：{plan.topic}
行业：{plan.industry}
目标产品：{plan.target_product}
竞品：{', '.join(plan.competitors)}
动态维度字段：
{json.dumps(fields, ensure_ascii=False)}

要求：
1. 必须为每个字段输出一条 spec，不能新增或删除维度。
2. dimension_key 必须等于字段 key，dimension_label 必须等于字段 label。
3. analysis_goal、must_answer、evidence_focus、comparison_criteria、search_query_template 必须适配该维度和行业。
4. search_query_template 用于 Firecrawl 搜索证据，必须包含 {{competitor}} 占位符，并且只为当前维度生成 1 条主 query。
5. 如果竞品或行业是全球技术产品、SaaS、API、开发者工具、云服务、数据库、AI 工具，search_query_template 使用英文。
6. 如果目标市场是中国本土，或用户输入明显是中文消费场景、本土品牌、中文媒体语境，search_query_template 使用中文。
7. search_query_template 不要太长，控制在 6 到 12 个关键词。
8. 不要输出固定功能、价格、安全三类通用 query，必须围绕当前维度。
9. 不要输出完整报告，不要执行分析。
10. 只输出合法 JSON 数组。

格式：
[
  {{"dimension_key":"...","dimension_label":"...","analysis_goal":"...","evidence_focus":["official docs"],"must_answer":["..."],"comparison_criteria":["..."],"search_query_template":"{{competitor}} ... official docs"}}
]
"""
        specs_by_key = dict(fallback_specs)
        try:
            parsed = _json_from_text(llm.complete(prompt, system="你只输出合法 JSON。"))
            if isinstance(parsed, dict):
                parsed = parsed.get("dimensions", [])
            for item in parsed if isinstance(parsed, list) else []:
                key = str(item.get("dimension_key") or "").strip()
                if key in specs_by_key:
                    specs_by_key[key] = {**specs_by_key[key], **item}
        except Exception as exc:
            add_log(db, task_id, node.id, "Dimension prompt planning fallback used", {"error": str(exc)}, log_type="warning")

        node_specs = build_dimension_node_specs(plan)
        node_key_by_dimension_key = {spec["dimension_key"]: spec["node_key"] for spec in node_specs}
        existing_node_keys = {node.node_key for node in dimension_nodes}
        specs_by_node = {}
        for dimension_key, spec in specs_by_key.items():
            node_key = node_key_by_dimension_key.get(dimension_key)
            if node_key not in existing_node_keys:
                continue
            dim_node = next(node for node in dimension_nodes if node.node_key == node_key)
            if spec is None:
                continue
            dim_node.input_summary = json.dumps(spec, ensure_ascii=False)[:1800]
            specs_by_node[node_key] = spec

        state["dimension_prompt_specs"] = specs_by_node
        node.output_summary = f"生成 {len(specs_by_node)} 个动态维度 Agent prompt spec"
        add_log(
            db,
            task_id,
            node.id,
            "Dimension prompt specs generated",
            {"dimension_count": len(specs_by_node), "dimensions": [spec.get("dimension_label") for spec in specs_by_node.values()]},
        )
        db.commit()

    def collector(node: AgentNode) -> None:
        plan = get_task_plan(task)
        if plan.auto_discover_competitors and not plan.competitors:
            _check_task_control(db, task_id, node)
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
        existing_urls = {
            str(url)
            for url in db.scalars(select(SourceDocument.source_url).where(SourceDocument.task_id == task_id))
            if url
        }
        seen_urls: set[str] = set(existing_urls)
        collector_mode = str(state.get("collector_mode") or "normal")
        dimension_specs = state.get("dimension_prompt_specs") or {}
        max_results_per_query = max(1, int(settings.firecrawl_search_results_per_query))
        max_urls_per_competitor = int(settings.firecrawl_max_urls_per_competitor)
        for competitor in plan.competitors:
            _check_task_control(db, task_id, node)
            _console("collector competitor started", {"task_id": task_id, "competitor": competitor, "mode": collector_mode})
            if collector_mode == "recollect":
                queries = [
                    str(query).strip()
                    for query in state.get("qa_followup_queries", [])
                    if str(query).strip() and competitor.casefold() in str(query).casefold()
                ]
            else:
                queries = [
                    _format_dimension_search_query(plan, competitor, prompt_spec)
                    for prompt_spec in dimension_specs.values()
                    if isinstance(prompt_spec, dict)
                ]
            queries = _dedupe_preserve_order(queries)
            if not queries:
                add_log(
                    db,
                    task_id,
                    node.id,
                    "Collector skipped competitor because no search queries were available",
                    {"competitor": competitor, "mode": collector_mode},
                    log_type="warning",
                )
                db.commit()
                continue
            max_workers = max(1, min(settings.collector_max_workers, len(queries)))
            _console(
                "parallel firecrawl search started",
                {
                    "task_id": task_id,
                    "competitor": competitor,
                    "mode": collector_mode,
                    "query_count": len(queries),
                    "max_workers": max_workers,
                    "max_results_per_query": max_results_per_query,
                    "max_urls_per_competitor": max_urls_per_competitor,
                },
            )
            add_log(
                db,
                task_id,
                node.id,
                "Parallel Firecrawl search started",
                {
                    "competitor": competitor,
                    "mode": collector_mode,
                    "queries": queries,
                    "query_count": len(queries),
                    "max_workers": max_workers,
                    "max_results_per_query": max_results_per_query,
                    "max_urls_per_competitor": max_urls_per_competitor,
                },
            )
            db.commit()

            search_payloads: list[dict] = []
            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=f"collector-search-{task_id}") as executor:
                futures = {executor.submit(_search_firecrawl_query, query, max_results_per_query): query for query in queries}
                for future in as_completed(futures):
                    _check_task_control(db, task_id, node)
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
                        if max_urls_per_competitor > 0 and len(search_payloads) >= max_urls_per_competitor:
                            break
                    if max_urls_per_competitor > 0 and len(search_payloads) >= max_urls_per_competitor:
                        break
                    db.commit()
            db.commit()

            if not search_payloads:
                add_log(
                    db,
                    task_id,
                    node.id,
                    "Collector found no new URLs for competitor",
                    {"competitor": competitor, "mode": collector_mode},
                    log_type="warning",
                )
                db.commit()
                continue
            scrape_workers = max(1, min(settings.collector_max_workers, len(search_payloads)))
            _console(
                "parallel firecrawl scrape started",
                {
                    "task_id": task_id,
                    "competitor": competitor,
                    "mode": collector_mode,
                    "url_count": len(search_payloads),
                    "max_workers": scrape_workers,
                },
            )
            with ThreadPoolExecutor(max_workers=scrape_workers, thread_name_prefix=f"collector-scrape-{task_id}") as executor:
                futures = {executor.submit(_scrape_firecrawl_url, payload): payload for payload in search_payloads}
                for future in as_completed(futures):
                    _check_task_control(db, task_id, node)
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
                    existing_urls.add(url)
                    _console("firecrawl scrape saved", {"task_id": task_id, "source_document_id": doc.id, "url": url})
                    add_log(db, task_id, node.id, "Firecrawl scrape saved", {"url": url, "source_document_id": doc.id})
                    db.commit()
        if not saved_ids:
            raise RuntimeError("Firecrawl did not return any usable source documents")
        node.output_summary = f"{collector_mode} 模式真实采集并保存 {len(saved_ids)} 份新增 source_document"
        state["source_document_ids"] = saved_ids

    def evidence_extractor(node: AgentNode) -> None:
        stage_started = perf_counter()
        source_document_ids = [int(doc_id) for doc_id in state.get("source_document_ids", []) if str(doc_id).isdigit()]
        if source_document_ids:
            docs = list(
                db.scalars(
                    select(SourceDocument)
                    .where(SourceDocument.task_id == task_id, SourceDocument.id.in_(source_document_ids))
                    .order_by(SourceDocument.id)
                )
            )
        else:
            docs = list(db.scalars(select(SourceDocument).where(SourceDocument.task_id == task_id).order_by(SourceDocument.id)))
        _console(
            "evidence extractor document scope selected",
            {"task_id": task_id, "document_count": len(docs), "incremental": bool(source_document_ids)},
        )
        ids: list[int] = []
        pending_specs: list[dict] = []
        chunk_objects: list[EvidenceChunk] = []
        chunking_started = perf_counter()
        for doc in docs:
            _check_task_control(db, task_id, node)
            _console("evidence document started", {"task_id": task_id, "source_document_id": doc.id, "competitor": doc.competitor_name})
            for idx, text in enumerate(_chunks(doc.content_markdown or doc.content_text or "")[:4]):
                _check_task_control(db, task_id, node)
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
                chunk_objects.append(chunk)
        chunking_ms = int((perf_counter() - chunking_started) * 1000)
        mysql_create_started = perf_counter()
        db.flush()
        for chunk in chunk_objects:
            ids.append(chunk.id)
            pending_specs.append(
                {
                    "chunk_id": chunk.id,
                    "task_id": task_id,
                    "source_document_id": chunk.source_document_id,
                    "chunk_index": chunk.chunk_index,
                    "competitor_name": chunk.competitor_name,
                    "source_type": chunk.source_type,
                    "source_url": chunk.source_url,
                    "chunk_text": chunk.chunk_text,
                }
            )
        db.commit()
        mysql_create_ms = int((perf_counter() - mysql_create_started) * 1000)
        if not ids:
            raise RuntimeError("No evidence chunks were extracted")

        max_workers = max(1, min(settings.evidence_extractor_max_workers, len(pending_specs)))
        batch_size = max(1, settings.evidence_embedding_batch_size)
        batches = _batched(pending_specs, batch_size)
        timing_payload = {
            "stage": "evidence_extractor",
            "chunk_count": len(pending_specs),
            "document_count": len(docs),
            "batch_count": len(batches),
            "batch_size": batch_size,
            "max_workers": max_workers,
            "chunking_ms": chunking_ms,
            "mysql_create_ms": mysql_create_ms,
        }
        _console("parallel batch evidence embedding started", {"task_id": task_id, **timing_payload})
        add_log(
            db,
            task_id,
            node.id,
            "Evidence extraction timing: chunk creation completed",
            timing_payload,
            log_type="metric",
        )
        db.commit()

        failures: list[dict] = []
        embedded_specs: list[dict] = []
        embedding_started = perf_counter()
        embedding_worker_ms = 0
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=f"evidence-{task_id}") as executor:
            futures = {executor.submit(_embed_chunk_batch, batch): batch for batch in batches}
            for future in as_completed(futures):
                _check_task_control(db, task_id, node)
                batch = futures[future]
                try:
                    embedded_batch, batch_failures, batch_elapsed_ms = future.result()
                except Exception as exc:
                    failures.append({"chunk_ids": [spec["chunk_id"] for spec in batch], "error": str(exc)})
                    _console("evidence embedding batch failed", {"task_id": task_id, "chunk_count": len(batch), "error": str(exc)})
                    add_log(
                        db,
                        task_id,
                        node.id,
                        "Evidence embedding batch failed",
                        {"chunk_ids": [spec["chunk_id"] for spec in batch], "error": str(exc)},
                        log_type="error",
                    )
                    db.commit()
                    continue

                if batch_failures:
                    failures.extend(batch_failures)
                    add_log(
                        db,
                        task_id,
                        node.id,
                        "Evidence embedding fallback left failed chunks",
                        {"failures": batch_failures},
                        log_type="warning",
                    )
                    db.commit()
                embedding_worker_ms += batch_elapsed_ms
                embedded_specs.extend(embedded_batch)
                _console(
                    "evidence embedding batch completed",
                    {
                        "task_id": task_id,
                        "chunk_count": len(embedded_batch),
                        "failed_count": len(batch_failures),
                        "batch_elapsed_ms": batch_elapsed_ms,
                    },
                )
        embedding_wall_ms = int((perf_counter() - embedding_started) * 1000)

        _check_task_control(db, task_id, node)
        milvus_started = perf_counter()
        vector_ids = MilvusTool().upsert_evidence_embeddings_batch(embedded_specs) if embedded_specs else []
        milvus_ms = int((perf_counter() - milvus_started) * 1000)

        mysql_update_started = perf_counter()
        for spec, vector_id in zip(embedded_specs, vector_ids, strict=False):
            chunk = db.get(EvidenceChunk, spec["chunk_id"])
            if chunk is not None:
                chunk.milvus_vector_id = vector_id
        for failure in failures:
            chunk = db.get(EvidenceChunk, failure["chunk_id"])
            if chunk is not None:
                chunk.milvus_vector_id = f"embedding-failed-{chunk.id}"
        db.commit()
        mysql_update_ms = int((perf_counter() - mysql_update_started) * 1000)
        total_ms = int((perf_counter() - stage_started) * 1000)

        node.output_summary = f"抽取并向量化 {len(ids)} 条 evidence_chunk"
        add_log(
            db,
            task_id,
            node.id,
            "Evidence extraction timing completed",
            {
                "stage": "evidence_extractor",
                "document_count": len(docs),
                "chunk_count": len(ids),
                "batch_count": len(batches),
                "batch_size": batch_size,
                "max_workers": max_workers,
                "chunking_ms": chunking_ms,
                "mysql_create_ms": mysql_create_ms,
                "embedding_wall_ms": embedding_wall_ms,
                "embedding_worker_ms": embedding_worker_ms,
                "milvus_batch_insert_ms": milvus_ms,
                "mysql_update_ms": mysql_update_ms,
                "total_ms": total_ms,
                "completed": len(vector_ids),
                "failed": len(failures),
                "failed_chunk_ids": [failure["chunk_id"] for failure in failures],
            },
            log_type="metric",
        )
        _console(
            "evidence extraction timing completed",
            {
                "task_id": task_id,
                "chunk_count": len(ids),
                "batch_count": len(batches),
                "embedding_wall_ms": embedding_wall_ms,
                "milvus_batch_insert_ms": milvus_ms,
                "mysql_update_ms": mysql_update_ms,
                "total_ms": total_ms,
            },
        )
        state["evidence_chunk_ids"] = ids

    def _dimension_specs_from_state() -> dict[str, dict]:
        specs = state.get("dimension_prompt_specs")
        if isinstance(specs, dict) and specs:
            return specs
        plan = get_task_plan(task)
        node_specs = build_dimension_node_specs(plan)
        fallback_by_key = {
            spec["node_key"]: _fallback_dimension_prompt_spec(plan.model_dump(), spec["field"])
            for spec in node_specs
        }
        state["dimension_prompt_specs"] = fallback_by_key
        return fallback_by_key

    def _dimension_targets_from_issues(issues: list[dict]) -> list[str]:
        specs_by_node = _dimension_specs_from_state()
        if not specs_by_node:
            return []
        node_by_id = {
            node.id: node.node_key
            for node in db.scalars(
                select(AgentNode).where(
                    AgentNode.task_id == task_id,
                    AgentNode.node_key.in_(list(specs_by_node)),
                )
            )
        }
        aliases_by_node: dict[str, set[str]] = {}
        for node_key, spec in specs_by_node.items():
            aliases = {node_key}
            for value in (
                spec.get("dimension_key"),
                spec.get("dimension_label"),
                spec.get("label"),
                spec.get("analysis_goal"),
            ):
                if value:
                    aliases.add(str(value).strip().casefold())
            aliases_by_node[node_key] = {alias for alias in aliases if alias}

        targets: set[str] = set()
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            target_node = issue.get("target_node")
            if target_node in specs_by_node:
                targets.add(str(target_node))
                continue
            related_claim_id = issue.get("related_claim_id")
            if related_claim_id:
                try:
                    claim = db.get(Claim, int(related_claim_id))
                except (TypeError, ValueError):
                    claim = None
                if claim and claim.agent_node_id in node_by_id:
                    targets.add(node_by_id[claim.agent_node_id])
                    continue
            exact_values = [
                issue.get("related_dimension"),
                issue.get("dimension_key"),
                issue.get("dimension_label"),
                issue.get("claim_type"),
            ]
            exact_tokens = {str(value).strip().casefold() for value in exact_values if value}
            matched = False
            for node_key, aliases in aliases_by_node.items():
                if exact_tokens & aliases:
                    targets.add(node_key)
                    issue["target_node"] = node_key
                    matched = True
                    break
            if matched:
                continue
            free_text = " ".join(
                str(issue.get(key) or "")
                for key in ("message", "search_query", "related_dimension")
            ).casefold()
            for node_key, aliases in aliases_by_node.items():
                if any(alias and len(alias) >= 3 and alias in free_text for alias in aliases):
                    targets.add(node_key)
                    issue["target_node"] = node_key
                    break
        return sorted(targets)

    def _clear_claims_for_dimension_node(local_db: Session, node_key: str) -> None:
        node = local_db.scalar(select(AgentNode).where(AgentNode.task_id == task_id, AgentNode.node_key == node_key))
        if node is None:
            return
        claim_ids = select(Claim.id).where(Claim.task_id == task_id, Claim.agent_node_id == node.id)
        local_db.execute(delete(ClaimEvidence).where(ClaimEvidence.claim_id.in_(claim_ids)).execution_options(synchronize_session=False))
        local_db.execute(delete(Claim).where(Claim.task_id == task_id, Claim.agent_node_id == node.id).execution_options(synchronize_session=False))
        local_db.flush()

    def _run_one_dimension_analyst_thread(node_key: str, prompt_spec: dict, force: bool = False) -> tuple[str, list[int]]:
        local_db = SessionLocal()
        local_claim_ids: list[int] = []
        try:
            def run_logic(node: AgentNode) -> None:
                if force:
                    _clear_claims_for_dimension_node(local_db, node_key)
                local_claim_ids.extend(_run_dimension_analyst_logic(local_db, task_id, node, prompt_spec))

            _run_node(local_db, task_id, node_key, "analyzing", run_logic, force=force)
            return node_key, local_claim_ids
        finally:
            local_db.close()

    def run_parallel_dimension_analysts(node_keys: list[str] | None = None, force: bool = False) -> None:
        specs_by_node = _dimension_specs_from_state()
        selected_node_keys = node_keys or list(specs_by_node)
        selected_node_keys = [node_key for node_key in selected_node_keys if node_key in specs_by_node]
        if not selected_node_keys:
            return
        _console("parallel dimension analysts started", {"task_id": task_id, "node_keys": selected_node_keys, "force": force})
        add_log(db, task_id, None, "Parallel dimension analysts started", {"node_keys": selected_node_keys, "force": force})
        db.commit()
        with ThreadPoolExecutor(max_workers=len(selected_node_keys), thread_name_prefix=f"analyst-{task_id}") as executor:
            futures = {
                executor.submit(_run_one_dimension_analyst_thread, node_key, specs_by_node[node_key], force): node_key
                for node_key in selected_node_keys
            }
            for future in as_completed(futures):
                node_key = futures[future]
                try:
                    completed_node_key, claim_ids = future.result()
                except Exception as exc:
                    state.setdefault("dimension_failures", []).append({"node_key": node_key, "error": str(exc)})
                    _console("parallel dimension analyst failed", {"task_id": task_id, "node_key": node_key, "error": str(exc)})
                    add_log(
                        db,
                        task_id,
                        None,
                        "Dimension analyst failed; workflow stopped before report generation",
                        {"node_key": node_key, "error": str(exc)},
                        log_type="error",
                    )
                    db.commit()
                    raise RuntimeError(f"动态分析 Agent 执行失败，已停止生成报告：{node_key} - {exc}") from exc
                state["dimension_failures"] = [
                    failure
                    for failure in state.get("dimension_failures", [])
                    if failure.get("node_key") != completed_node_key
                ]
                state.setdefault("claim_ids", []).extend(claim_ids)
                _console(
                    "parallel dimension analyst completed",
                    {"task_id": task_id, "node_key": completed_node_key, "claim_count": len(claim_ids)},
                )
                add_log(db, task_id, None, "Parallel dimension analyst completed", {"node_key": completed_node_key, "claim_count": len(claim_ids)})
                db.commit()
        db.expire_all()
        _console("parallel dimension analysts completed", {"task_id": task_id, "node_keys": selected_node_keys})
        claim_count = db.scalar(select(func.count(Claim.id)).where(Claim.task_id == task_id))
        if not claim_count:
            raise RuntimeError("所有动态分析 Agent 都没有生成 Claim，已停止生成空报告")

    def report_writer(node: AgentNode) -> None:
        plan = get_task_plan(task)
        claims = list(db.scalars(select(Claim).where(Claim.task_id == task_id).order_by(Claim.id)))
        if not claims:
            raise RuntimeError("没有可用于生成报告的 Claim，已停止生成空报告")
        profiles = list(db.scalars(select(CompetitorProfile).where(CompetitorProfile.task_id == task_id).order_by(CompetitorProfile.id)))
        matrices = list(db.scalars(select(ComparisonMatrix).where(ComparisonMatrix.task_id == task_id).order_by(ComparisonMatrix.id)))
        evidence_by_claim = _claim_evidence_map(db, [claim.id for claim in claims])
        claim_context = "\n".join(
            f"[claim_id={claim.id}] competitor={claim.competitor_name}; type={claim.claim_type}; "
            f"dimension_key={claim.dimension_key}; dimension_label={claim.dimension_label}; "
            f"evidence_ids={evidence_by_claim.get(claim.id, [])}; text={claim.claim_text}"
            for claim in claims
        )
        profile_context = json.dumps(
            [
                {
                    "profile_id": profile.id,
                    "competitor_name": profile.competitor_name,
                    "profile_data": profile.profile_data_json,
                }
                for profile in profiles
            ],
            ensure_ascii=False,
        )[:9000]
        matrix_context = json.dumps(
            [
                {
                    "matrix_id": matrix.id,
                    "title": matrix.title,
                    "matrix_data": matrix.matrix_data_json,
                }
                for matrix in matrices
            ],
            ensure_ascii=False,
        )[:9000]
        revision_instruction = state.get("revision_reason") or ""
        valid_claim_ids = {claim.id for claim in claims}
        latest_report = db.scalar(select(Report).where(Report.task_id == task_id).order_by(Report.id.desc()))
        writer_mode = str(state.get("report_writer_mode") or "full_write")

        def generate_full_report() -> dict:
            prompt = f"""
请基于动态竞品画像、对比矩阵和结构化 Claim 生成中文竞品分析报告正文 JSON。
主题：{plan.topic}
行业：{plan.industry}
竞品：{', '.join(plan.competitors)}
分析维度：{', '.join(plan.analysis_dimensions)}
返工要求：{revision_instruction}

要求：
1. 只输出合法 JSON，不要 Markdown。
2. 只生成具体分析维度 section，不要生成执行摘要、总体结论、总体建议、排名、推荐等全文总结 section。
3. 每个关键 paragraph 必须包含 paragraph_id、text、claim_ids。
4. claim_ids 只能引用下方已有 claim_id，不要编造。
5. 不要输出 evidence_ids，后端会自动补齐。
6. 必须覆盖所有分析维度。
7. 优先基于 CompetitorProfiles 和 ComparisonMatrices 组织维度正文，但关键段落仍要引用 claim_ids。

JSON 格式：
{{"title":"...","sections":[{{"section_id":"pricing_strategy","title":"价格策略","paragraphs":[{{"paragraph_id":"pricing_strategy_p1","text":"...","claim_ids":[1,2]}}]}}]}}

CompetitorProfiles:
{profile_context}

ComparisonMatrices:
{matrix_context}

Claims:
{claim_context}
"""
            _console("llm report writer full_write started", {"task_id": task_id, "claim_count": len(claims)})
            parsed = _json_from_text(llm.complete(prompt, system="你只输出合法 JSON。"))
            if not isinstance(parsed, dict) or not parsed.get("sections"):
                raise ValueError("report_json.sections missing")
            parsed.setdefault("title", f"{plan.topic}报告")
            return parsed

        def target_revision_context() -> tuple[list[str], list[Claim], list[dict], set[str]]:
            target_nodes = [
                str(node_key)
                for node_key in state.get("qa_target_nodes", [])
                if str(node_key).startswith("dimension_analysis_")
            ]
            if not target_nodes:
                return [], [], [], set()
            nodes_by_key = {
                item.node_key: item
                for item in db.scalars(
                    select(AgentNode).where(AgentNode.task_id == task_id, AgentNode.node_key.in_(target_nodes))
                )
            }
            target_node_ids = {node.id for node in nodes_by_key.values()}
            target_claims = [claim for claim in claims if claim.agent_node_id in target_node_ids]
            specs = _dimension_specs_from_state()
            dimension_specs = []
            aliases: set[str] = set(target_nodes)
            for node_key in target_nodes:
                spec = specs.get(node_key) or {}
                node = nodes_by_key.get(node_key)
                dimension_spec = {
                    "target_node": node_key,
                    "node_name": node.node_name if node else node_key,
                    "dimension_key": spec.get("dimension_key"),
                    "dimension_label": spec.get("dimension_label") or spec.get("label") or (node.node_name if node else node_key),
                }
                dimension_specs.append(dimension_spec)
                for value in dimension_spec.values():
                    if value:
                        aliases.add(_normalized_token(value))
            for claim in target_claims:
                aliases.add(_normalized_token(claim.dimension_key))
                aliases.add(_normalized_token(claim.dimension_label))
                aliases.add(_normalized_token(claim.claim_type))
            return target_nodes, target_claims, dimension_specs, {alias for alias in aliases if alias}

        def generate_partial_report() -> dict:
            if latest_report is None or not isinstance(latest_report.report_json, dict):
                raise ValueError("partial_revision requires an existing report_json")
            previous_report_json = deepcopy(latest_report.report_json)
            previous_sections = [
                section
                for section in previous_report_json.get("sections", [])
                if isinstance(section, dict)
            ]
            target_nodes, target_claims, dimension_specs, target_aliases = target_revision_context()
            if not target_nodes or not target_claims:
                raise ValueError("partial_revision missing target dimension claims")
            target_claim_ids = {claim.id for claim in target_claims}
            target_claim_context = "\n".join(
                f"[claim_id={claim.id}] competitor={claim.competitor_name}; type={claim.claim_type}; "
                f"dimension_key={claim.dimension_key}; dimension_label={claim.dimension_label}; "
                f"evidence_ids={evidence_by_claim.get(claim.id, [])}; text={claim.claim_text}"
                for claim in target_claims
            )
            existing_target_sections = [
                section
                for section in previous_sections
                if (_section_claim_ids(section) & target_claim_ids) or _section_matches_alias(section, target_aliases)
            ]
            partial_prompt = f"""
请对已有中文竞品分析报告正文做局部修订，只输出合法 JSON。

任务主题：{plan.topic}
行业：{plan.industry}
竞品：{', '.join(plan.competitors)}
本轮返工要求：{revision_instruction}

本轮只允许修订这些动态维度：
{json.dumps(dimension_specs, ensure_ascii=False)}

要求：
1. 只输出 JSON，不要 Markdown。
2. 只输出上述目标维度的 dimension_sections，不要改写其它维度。
3. 不要生成执行摘要、总体结论、总体建议、排名、推荐等全文总结 section。
4. 每个 section 必须包含 section_id、title、paragraphs；每个 paragraph 必须包含 paragraph_id、text、claim_ids。
5. claim_ids 只能引用“目标维度 Claims”或“全部 Claims”中存在的 claim_id，不要编造。
6. 不要输出 evidence_ids，后端会自动补齐。

JSON 格式：
{{"title":"...","dimension_sections":[{{"section_id":"pricing_strategy","title":"价格策略","paragraphs":[{{"paragraph_id":"pricing_strategy_p1","text":"...","claim_ids":[12,13]}}]}}]}}

上一版目标维度 section：
{json.dumps(existing_target_sections, ensure_ascii=False)[:5000]}

CompetitorProfiles:
{profile_context}

ComparisonMatrices:
{matrix_context}

目标维度 Claims：
{target_claim_context}

全部 Claims：
{claim_context}
"""
            _console(
                "llm report writer partial_revision started",
                {"task_id": task_id, "target_nodes": target_nodes, "target_claim_count": len(target_claims)},
            )
            parsed = _json_from_text(llm.complete(partial_prompt, system="你只输出合法 JSON。"))
            if not isinstance(parsed, dict):
                raise ValueError("partial report payload must be an object")
            dimension_sections = parsed.get("dimension_sections") or parsed.get("sections") or []
            replacement_json = _sanitize_report_sections(
                {
                    "title": parsed.get("title") or previous_report_json.get("title") or f"{plan.topic}报告",
                    "sections": dimension_sections,
                },
                valid_claim_ids,
            )
            target_replacements = replacement_json.get("sections", [])
            if not target_replacements:
                raise ValueError("partial report sections missing")

            merged_sections: list[dict] = []
            inserted_targets = False
            for section in previous_sections:
                is_global = _is_global_report_section(section)
                is_target = (_section_claim_ids(section) & target_claim_ids) or _section_matches_alias(section, target_aliases)
                if is_global:
                    continue
                if is_target:
                    if not inserted_targets:
                        merged_sections.extend(target_replacements)
                        inserted_targets = True
                    continue
                merged_sections.append(section)
            if not inserted_targets:
                merged_sections.extend(target_replacements)
            return {
                **previous_report_json,
                "title": parsed.get("title") or previous_report_json.get("title") or f"{plan.topic}报告",
                "sections": merged_sections,
                "revision_mode": "partial_revision",
                "partial_revision_target_nodes": target_nodes,
            }

        try:
            if writer_mode == "partial_revision":
                report_json = generate_partial_report()
            else:
                report_json = generate_full_report()
            report_json = _sanitize_report_sections(report_json, valid_claim_ids)
            report_json["sections"] = [
                section for section in report_json.get("sections", []) if not _is_global_report_section(section)
            ]
            if not report_json.get("sections"):
                raise ValueError("report_json.sections missing after sanitize")
            report_json = _fill_paragraph_evidence(report_json, evidence_by_claim)
        except Exception as exc:
            add_log(
                db,
                task_id,
                node.id,
                "Report JSON generation fallback used",
                {"error": str(exc), "mode": writer_mode},
                log_type="warning",
            )
            if writer_mode == "partial_revision":
                _, target_claims, _, _ = target_revision_context()
                fallback_claims = target_claims or claims
                if latest_report is not None and isinstance(latest_report.report_json, dict) and target_claims:
                    fallback_partial = _fallback_report_json(task, fallback_claims, evidence_by_claim)
                    previous_report_json = deepcopy(latest_report.report_json)
                    target_claim_ids = {claim.id for claim in fallback_claims}
                    merged_sections = [
                        section
                        for section in previous_report_json.get("sections", [])
                        if not (_section_claim_ids(section) & target_claim_ids)
                    ]
                    merged_sections.extend(fallback_partial.get("sections", []))
                    report_json = {**previous_report_json, "sections": merged_sections, "revision_mode": "partial_revision_fallback"}
                else:
                    report_json = _fallback_report_json(task, fallback_claims, evidence_by_claim)
            else:
                report_json = _fallback_report_json(task, claims, evidence_by_claim)
            report_json = _sanitize_report_sections(report_json, valid_claim_ids)
            report_json["sections"] = [
                section for section in report_json.get("sections", []) if not _is_global_report_section(section)
            ]
            report_json = _fill_paragraph_evidence(report_json, evidence_by_claim)
        content = _render_report_markdown(report_json)
        report = Report(
            task_id=task_id,
            title=report_json.get("title") or f"{plan.topic}报告",
            content_markdown=content,
            content_html=markdown.markdown(content, extensions=["tables"]),
            report_json={
                **report_json,
                "mode": "firecrawl_llm_milvus_rag",
                "report_writer_mode": writer_mode,
                "profile_ids": [profile.id for profile in profiles],
                "matrix_ids": [matrix.id for matrix in matrices],
            },
        )
        db.add(report)
        db.flush()
        node.output_summary = f"使用 {writer_mode} 模式生成报告 #{report.id}"
        _console("llm report writer completed", {"task_id": task_id, "report_id": report.id, "mode": writer_mode})
        state["report_id"] = report.id

    def report_finalizer(node: AgentNode) -> None:
        plan = get_task_plan(task)
        latest_report = db.scalar(select(Report).where(Report.task_id == task_id).order_by(Report.id.desc()))
        if latest_report is None or not isinstance(latest_report.report_json, dict):
            raise RuntimeError("没有可用于生成最终摘要的报告正文")
        claims = list(db.scalars(select(Claim).where(Claim.task_id == task_id).order_by(Claim.id)))
        if not claims:
            raise RuntimeError("没有可用于生成最终摘要的 Claim")
        profiles = list(db.scalars(select(CompetitorProfile).where(CompetitorProfile.task_id == task_id).order_by(CompetitorProfile.id)))
        matrices = list(db.scalars(select(ComparisonMatrix).where(ComparisonMatrix.task_id == task_id).order_by(ComparisonMatrix.id)))
        evidence_by_claim = _claim_evidence_map(db, [claim.id for claim in claims])
        valid_claim_ids = {claim.id for claim in claims}
        body_report_json = deepcopy(latest_report.report_json)
        body_sections = [
            section
            for section in body_report_json.get("sections", [])
            if isinstance(section, dict) and not _is_global_report_section(section)
        ]
        if not body_sections:
            raise RuntimeError("报告正文缺少可总结的维度 section")
        claim_context = "\n".join(
            f"[claim_id={claim.id}] competitor={claim.competitor_name}; type={claim.claim_type}; "
            f"dimension_key={claim.dimension_key}; dimension_label={claim.dimension_label}; "
            f"evidence_ids={evidence_by_claim.get(claim.id, [])}; text={claim.claim_text}"
            for claim in claims
        )
        profile_context = json.dumps(
            [
                {
                    "profile_id": profile.id,
                    "competitor_name": profile.competitor_name,
                    "profile_data": profile.profile_data_json,
                }
                for profile in profiles
            ],
            ensure_ascii=False,
        )[:9000]
        matrix_context = json.dumps(
            [
                {
                    "matrix_id": matrix.id,
                    "title": matrix.title,
                    "matrix_data": matrix.matrix_data_json,
                }
                for matrix in matrices
            ],
            ensure_ascii=False,
        )[:9000]
        finalizer_prompt = f"""
请基于当前最终竞品分析正文，生成最终报告的全文总结 section，只输出合法 JSON。

主题：{plan.topic}
行业：{plan.industry}
竞品：{', '.join(plan.competitors)}
分析维度：{', '.join(plan.analysis_dimensions)}
维度正文 QA 是否通过：{state.get("qa_passed")}
维度正文 QA 残留问题：
{json.dumps(state.get("qa_issues", []), ensure_ascii=False)[:5000]}

要求：
1. 只输出 JSON，不要 Markdown。
2. 只生成 global_sections，不要改写具体分析维度 section。
3. global_sections 应包含执行摘要、总体结论、关键建议或风险提示；如需排名或推荐，必须能被正文 Claim 支撑。
4. 每个 paragraph 必须包含 paragraph_id、text、claim_ids。
5. claim_ids 只能引用下方已有 claim_id，不要编造。
6. 不要输出 evidence_ids，后端会自动补齐。
7. 不要引入正文和 Claim 中没有的新事实。
8. 如果 QA 未通过，必须在风险提示或结论中明确说明仍存在的证据、覆盖或写作问题，不要把未通过内容包装成完全可靠结论。

JSON 格式：
{{"title":"...","global_sections":[{{"section_id":"executive_summary","title":"执行摘要","paragraphs":[{{"paragraph_id":"executive_summary_p1","text":"...","claim_ids":[1,2]}}]}}]}}

当前最终正文 sections：
{json.dumps(body_sections, ensure_ascii=False)[:9000]}

CompetitorProfiles:
{profile_context}

ComparisonMatrices:
{matrix_context}

Claims:
{claim_context}
"""
        _console("llm report finalizer started", {"task_id": task_id, "body_section_count": len(body_sections)})
        try:
            parsed = _json_from_text(llm.complete(finalizer_prompt, system="你只输出合法 JSON。"))
            if not isinstance(parsed, dict):
                raise ValueError("finalizer payload must be an object")
            finalizer_json = _sanitize_report_sections(
                {
                    "title": parsed.get("title") or body_report_json.get("title") or f"{plan.topic}报告",
                    "sections": parsed.get("global_sections") or parsed.get("sections") or [],
                },
                valid_claim_ids,
            )
            global_sections = [
                section for section in finalizer_json.get("sections", []) if _is_global_report_section(section)
            ] or finalizer_json.get("sections", [])
            if not global_sections:
                raise ValueError("global_sections missing")
        except Exception as exc:
            add_log(db, task_id, node.id, "Report finalizer fallback used", {"error": str(exc)}, log_type="warning")
            top_claims = claims[: min(6, len(claims))]
            if state.get("qa_passed"):
                fallback_text = "本报告基于已通过 QA 的维度分析正文、结构化 Claim 和证据链生成。核心结论请以各维度正文及其 Claim/Evidence 绑定为准。"
            else:
                fallback_text = "本报告在达到当前返工限制后生成，仍存在未通过 QA 的残留问题。请优先查看风险提示、低置信度 Claim 和证据绑定情况，核心结论需结合各维度正文及其 Claim/Evidence 绑定谨慎使用。"
            global_sections = [
                {
                    "section_id": "executive_summary",
                    "title": "执行摘要",
                    "paragraphs": [
                        {
                            "paragraph_id": "executive_summary_p1",
                            "text": fallback_text,
                            "claim_ids": [claim.id for claim in top_claims],
                        }
                    ],
                }
            ]
        final_report_json = {
            **body_report_json,
            "title": body_report_json.get("title") or f"{plan.topic}报告",
            "sections": [*global_sections, *body_sections],
            "report_finalized": True,
            "qa_passed": state.get("qa_passed"),
            "qa_issues": state.get("qa_issues", []),
        }
        final_report_json = _sanitize_report_sections(final_report_json, valid_claim_ids)
        final_report_json = _fill_paragraph_evidence(final_report_json, evidence_by_claim)
        content = _render_report_markdown(final_report_json)
        report = Report(
            task_id=task_id,
            title=final_report_json.get("title") or f"{plan.topic}报告",
            content_markdown=content,
            content_html=markdown.markdown(content, extensions=["tables"]),
            report_json={
                **final_report_json,
                "mode": "firecrawl_llm_milvus_rag",
                "report_writer_mode": "finalized",
                "source_report_id": latest_report.id,
                "profile_ids": [profile.id for profile in profiles],
                "matrix_ids": [matrix.id for matrix in matrices],
            },
        )
        db.add(report)
        db.flush()
        node.output_summary = f"基于报告正文 #{latest_report.id} 生成最终摘要报告 #{report.id}"
        _console("llm report finalizer completed", {"task_id": task_id, "source_report_id": latest_report.id, "report_id": report.id})
        state["report_id"] = report.id

    def build_dynamic_knowledge() -> None:
        profiles = CompetitorProfileService(db).build_profiles_for_task(task_id)
        matrices = ComparisonMatrixService(db).build_matrices_for_task(task_id) if profiles else []
        plan = get_task_plan(task)
        failed_dimensions = [
            item.get("node_key")
            for item in state.get("dimension_failures", [])
            if isinstance(item, dict)
        ]
        payload = {
            "profile_count": len(profiles),
            "matrix_count": len(matrices),
            "template_key": plan.template_key,
            "field_count": len(plan.analysis_dimensions),
            "analysis_dimensions": plan.analysis_dimensions,
            "failed_dimension_nodes": failed_dimensions,
        }
        add_log(db, task_id, None, "Built dynamic competitor profiles and comparison matrices", payload)
        db.commit()
        _console("dynamic competitor knowledge built", {"task_id": task_id, **payload})

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
        node_key_by_id = {node.id: node.node_key for node in db.scalars(select(AgentNode).where(AgentNode.task_id == task_id))}
        issues = []
        for failure in state.get("dimension_failures", []):
            if not isinstance(failure, dict):
                continue
            failed_node = db.scalar(
                select(AgentNode).where(AgentNode.task_id == task_id, AgentNode.node_key == failure.get("node_key"))
            )
            issues.append(
                {
                    "type": "schema_incomplete",
                    "severity": "medium",
                    "message": f"{failed_node.node_name if failed_node else failure.get('node_key')} 执行失败，报告可能缺少该维度结论",
                    "related_claim_id": None,
                    "related_dimension": failed_node.node_name if failed_node else failure.get("node_key"),
                    "suggested_action": "reanalyze",
                    "target_node": failure.get("node_key"),
                }
            )
        for claim in claims:
            if claim.id not in linked_claim_ids:
                issues.append(
                    {
                        "type": "missing_evidence",
                        "severity": "high",
                        "message": f"Claim {claim.id} 缺少证据绑定",
                        "related_claim_id": claim.id,
                        "related_competitor": claim.competitor_name,
                        "related_dimension": claim.dimension_label or claim.claim_type,
                        "suggested_action": "reanalyze",
                        "target_node": node_key_by_id.get(claim.agent_node_id) if claim.agent_node_id else None,
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
                        "related_dimension": claim.dimension_label or claim.claim_type,
                        "suggested_action": "reanalyze",
                        "target_node": node_key_by_id.get(claim.agent_node_id) if claim.agent_node_id else None,
                    }
                )
        if report:
            missing_dimensions = [dim for dim in plan.analysis_dimensions if dim not in report.content_markdown]
            if missing_dimensions:
                issues.append({"type": "schema_incomplete", "severity": "medium", "message": f"报告可能未显式覆盖维度：{', '.join(missing_dimensions)}", "related_claim_id": None, "suggested_action": "rewrite"})
            if not report.content_markdown or len(report.content_markdown) < 500 or "##" not in report.content_markdown:
                issues.append({"type": "writing_issue", "severity": "high", "message": "报告为空、过短或缺少结构化章节", "suggested_action": "rewrite"})
        if not claims:
            issues.append({"type": "schema_incomplete", "severity": "high", "message": "所有动态维度 Agent 都未生成 Claim", "related_claim_id": None, "suggested_action": "reanalyze"})
        dimension_targets = [
            {
                "target_node": node_key,
                "dimension_key": spec.get("dimension_key"),
                "dimension_label": spec.get("dimension_label"),
            }
            for node_key, spec in _dimension_specs_from_state().items()
        ]
        qa_prompt = f"""
请复核这份竞品分析报告是否存在明显逻辑或证据问题。
仅基于报告和问题列表输出 JSON：
{{"passed":true/false,"score":0.0到1.0,"issues":[{{"type":"logic_gap|unsupported_claim|weak_evidence|schema_incomplete|writing_issue","severity":"low|medium|high","message":"中文问题","related_claim_id":null,"related_dimension":"动态维度名称","suggested_action":"recollect|reanalyze|rewrite|ignore","target_node":null,"search_query":null}}]}}

如果 suggested_action 是 recollect，必须提供一条具体 search_query，且 search_query 必须包含相关竞品名称。
如果 suggested_action 是 recollect 或 reanalyze，并且问题能定位到某个动态维度，target_node 必须填写下面可用动态维度节点中的 target_node，不要填写 collector。

可用动态维度节点：
{json.dumps(dimension_targets, ensure_ascii=False)}

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
        inferred_target_nodes = _dimension_targets_from_issues(issues)
        for issue in issues:
            if issue.get("target_node") in {"collector", "report_writer"}:
                issue["target_node"] = None
        if inferred_target_nodes:
            for issue in issues:
                if not issue.get("target_node"):
                    targets_for_issue = _dimension_targets_from_issues([issue])
                    if len(targets_for_issue) == 1:
                        issue["target_node"] = targets_for_issue[0]
        next_action, target_nodes = _decide_next_action(issues)
        if next_action in {"recollect", "reanalyze"} and not target_nodes:
            target_nodes = inferred_target_nodes
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
    _run_node(db, task_id, "dimension_planner", "planning_dimensions", dimension_planner)
    _run_node(db, task_id, "collector", "collecting", collector)
    _run_node(db, task_id, "evidence_extractor", "extracting", evidence_extractor)
    run_parallel_dimension_analysts()
    build_dynamic_knowledge()
    state["report_writer_mode"] = "full_write"
    _run_node(db, task_id, "report_writer", "writing", report_writer)
    _run_node(db, task_id, "qa", "qa_checking", qa)
    while not state.get("qa_passed") and state.get("revision_round", 0) < state.get("max_revision_rounds", 1):
        action = state.get("qa_next_action") or "end"
        target_nodes = state.get("qa_target_nodes", [])
        if action == "end":
            _console(
                "qa revision stopped because no actionable revision was requested",
                {"task_id": task_id, "revision_round": state.get("revision_round", 0)},
            )
            break
        state["revision_round"] = int(state.get("revision_round", 0)) + 1
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
            targets = [node_key for node_key in target_nodes if node_key.startswith("dimension_analysis_")]
            if not targets:
                raise RuntimeError("QA 要求补采资料，但没有定位到需要重跑的动态维度 Agent")
            try:
                state["collector_mode"] = "recollect"
                _run_node(db, task_id, "collector", "collecting", collector, force=True)
                _run_node(db, task_id, "evidence_extractor", "extracting", evidence_extractor, force=True)
            finally:
                state["collector_mode"] = "normal"
            run_parallel_dimension_analysts(targets, force=True)
            build_dynamic_knowledge()
            state["report_writer_mode"] = "partial_revision"
            _run_node(db, task_id, "report_writer", "writing", report_writer, force=True)
            _run_node(db, task_id, "qa", "qa_checking", qa, force=True)
        elif action == "reanalyze":
            targets = [node_key for node_key in target_nodes if node_key.startswith("dimension_analysis_")]
            if not targets:
                raise RuntimeError("QA 要求重新分析，但没有定位到需要重跑的动态维度 Agent")
            run_parallel_dimension_analysts(targets, force=True)
            build_dynamic_knowledge()
            state["report_writer_mode"] = "partial_revision"
            _run_node(db, task_id, "report_writer", "writing", report_writer, force=True)
            _run_node(db, task_id, "qa", "qa_checking", qa, force=True)
        elif action == "rewrite":
            state["report_writer_mode"] = "full_write"
            _run_node(db, task_id, "report_writer", "writing", report_writer, force=True)
            _run_node(db, task_id, "qa", "qa_checking", qa, force=True)
    if not state.get("qa_passed"):
        finalizer_node = _node(db, task_id, "report_finalizer")
        add_log(
            db,
            task_id,
            finalizer_node.id,
            "Report finalizer running with unresolved QA issues",
            {
                "revision_round": state.get("revision_round", 0),
                "max_revision_rounds": state.get("max_revision_rounds", 0),
                "qa_next_action": state.get("qa_next_action"),
                "issue_count": len(state.get("qa_issues", [])),
            },
            log_type="warning",
        )
        db.commit()
    _run_node(db, task_id, "report_finalizer", "finalizing", report_finalizer, force=True)
    _check_task_control(db, task_id)
    update_task_status(db, task_id, "success")
    _console("analysis workflow completed", {"task_id": task_id})
    return state
