from datetime import datetime
from io import BytesIO
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.comparison_matrix import ComparisonMatrix
from app.models.report import Report


def get_report(db: Session, task_id: int) -> Report | None:
    return db.scalar(select(Report).where(Report.task_id == task_id).order_by(Report.id.desc()))


def safe_report_filename(report: Report, extension: str) -> str:
    title = re.sub(r"[\\/:*?\"<>|\s]+", "_", report.title or f"analysis_report_{report.task_id}").strip("_")
    if not title:
        title = f"analysis_report_{report.task_id}"
    return f"{title[:80]}.{extension}"


def _markdown_cell(value: object) -> str:
    if value is None:
        return "暂无证据"
    if isinstance(value, list):
        text = "；".join(str(item) for item in value if item is not None)
    else:
        text = str(value)
    return text.replace("\n", " ").replace("|", "\\|").strip() or "暂无证据"


def _format_confidence(value: object) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _split_revision_reason(value: object) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in re.split(r"\s*(?:\r?\n|；|;)\s*", str(value)) if item.strip()]


def _is_global_report_section(section: dict) -> bool:
    text = f"{section.get('section_id') or ''} {section.get('title') or ''}".casefold()
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


def _is_executive_summary_section(section: dict) -> bool:
    text = f"{section.get('section_id') or ''} {section.get('title') or ''}".casefold()
    return any(keyword in text for keyword in ("executive", "summary", "overview", "摘要", "执行摘要", "总览", "概览"))


def _is_conclusion_section(section: dict) -> bool:
    text = f"{section.get('section_id') or ''} {section.get('title') or ''}".casefold()
    return any(keyword in text for keyword in ("conclusion", "takeaway", "总体", "总结", "结论"))


def _is_recommendation_or_risk_section(section: dict) -> bool:
    text = f"{section.get('section_id') or ''} {section.get('title') or ''}".casefold()
    return any(keyword in text for keyword in ("recommend", "ranking", "risk", "warning", "建议", "推荐", "排名", "风险", "提示"))


def _ordered_report_sections(report_json: dict | None) -> list[dict]:
    if not isinstance(report_json, dict):
        return []
    sections = [section for section in report_json.get("sections", []) if isinstance(section, dict)]
    allowed_sections = [section for section in sections if not _is_recommendation_or_risk_section(section)]
    executive_sections = [section for section in allowed_sections if _is_executive_summary_section(section)]
    body_sections = [section for section in allowed_sections if not _is_global_report_section(section)]
    conclusion_sections = [
        section
        for section in allowed_sections
        if _is_conclusion_section(section) and not _is_executive_summary_section(section)
    ]
    other_global_sections = [
        section
        for section in allowed_sections
        if _is_global_report_section(section) and section not in executive_sections and section not in conclusion_sections
    ]
    return [*executive_sections, *body_sections, *conclusion_sections, *other_global_sections]


def _report_body_markdown(report: Report) -> str:
    ordered_sections = _ordered_report_sections(report.report_json)
    if not ordered_sections:
        return report.content_markdown or ""
    title = report.report_json.get("title") if isinstance(report.report_json, dict) else None
    lines: list[str] = [f"# {title or report.title or '竞品分析报告'}", ""]
    for section in ordered_sections:
        section_title = section.get("title")
        if section_title:
            lines.extend([f"## {section_title}", ""])
        for paragraph in section.get("paragraphs", []):
            if not isinstance(paragraph, dict):
                continue
            text = str(paragraph.get("text") or "").strip()
            if not text:
                continue
            lines.extend([text, ""])
    return "\n".join(lines).strip()


def _matrix_markdown(matrices: list[ComparisonMatrix]) -> str:
    if not matrices:
        return ""
    sections: list[str] = ["", "## 竞品动态对比矩阵"]
    for matrix in matrices:
        columns = list((matrix.matrix_schema_json or {}).get("columns") or [])
        rows = list((matrix.matrix_data_json or {}).get("rows") or [])
        sections.extend(["", f"### {matrix.title}", ""])
        if not columns or not rows:
            sections.append("暂无矩阵数据。")
            continue
        header = ["维度", *columns]
        sections.append("| " + " | ".join(_markdown_cell(item) for item in header) + " |")
        sections.append("| " + " | ".join("---" for _ in header) + " |")
        for row in rows:
            values = row.get("values") or {}
            line = [_markdown_cell(row.get("label") or row.get("key"))]
            for column in columns:
                cell = values.get(column) or {}
                summary = _markdown_cell(cell.get("summary"))
                claim_count = len(cell.get("claim_ids") or [])
                evidence_count = len(cell.get("evidence_ids") or [])
                confidence = _format_confidence(cell.get("confidence"))
                line.append(f"{summary}<br>Claim {claim_count} / Evidence {evidence_count} / 置信度 {confidence}")
            sections.append("| " + " | ".join(line) + " |")
    return "\n".join(sections)


def _quality_summary_markdown(report_json: dict | None, qa_payload: dict | None = None) -> str:
    if not isinstance(report_json, dict):
        return ""
    quality = report_json.get("quality_summary") or {}
    if not isinstance(quality, dict) or not quality:
        return ""
    dimension_scores = report_json.get("dimension_qa_scores") or []
    final_status = quality.get("final_status") or "-"
    blockers = quality.get("blockers") or []
    blocker_text = "；".join(str(item) for item in blockers) if isinstance(blockers, list) else str(blockers or "无")
    score_formula = (
        f"{_format_confidence(quality.get('dimension_avg'))} × 70% + "
        f"{_format_confidence(quality.get('finalizer_score'))} × 30%"
    )
    sections = [
        "",
        "## 报告质量概览",
        "",
        "| 项目 | 结果 |",
        "| --- | --- |",
        f"| 维度正文 QA | {_markdown_cell(quality.get('dimension_body_qa_status') or '-')} |",
        f"| 总结溯源检查 | {_markdown_cell(quality.get('finalizer_grounding_status') or '-')} |",
        f"| 最终 QA 分数 | {_format_confidence(quality.get('final_score'))} |",
        f"| 分数构成 | {score_formula} |",
        f"| 最终 QA 状态 | {_markdown_cell(final_status)} |",
        f"| 硬性阻断原因 | {_markdown_cell(blocker_text or '无')} |",
    ]
    if dimension_scores:
        sections.extend(
            [
                "",
                "### 每维 QA 分数",
                "",
                "| 维度 | 分数 | 状态 |",
                "| --- | --- | --- |",
            ]
        )
        for item in dimension_scores:
            if not isinstance(item, dict):
                continue
            sections.append(
                "| "
                + " | ".join(
                    [
                        _markdown_cell(item.get("dimension_label") or item.get("dimension_key") or item.get("target_node")),
                        _format_confidence(item.get("score")),
                        "通过" if item.get("passed") else "未通过",
                    ]
                )
                + " |"
            )
    sections.extend(_qa_issues_markdown(qa_payload, heading_level=3))
    sections.extend(_finalizer_qa_issues_markdown(report_json.get("finalizer_qa"), heading_level=3))
    return "\n".join(sections)


def _qa_issues_markdown(qa_payload: dict | None, heading_level: int = 2) -> list[str]:
    heading = "#" * heading_level
    if not qa_payload:
        return ["", f"{heading} QA 问题", "", "暂无 QA 问题。"]
    issues = qa_payload.get("issues") or []
    if not issues:
        return ["", f"{heading} QA 问题", "", "暂无 QA 问题。"]
    sections = [
        "",
        f"{heading} QA 问题",
        "",
        "| # | 风险级别 | 问题类型 | 相关维度 | 建议动作 | 问题说明 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for index, issue in enumerate(issues, start=1):
        if not isinstance(issue, dict):
            sections.append(f"| {index} | - | 其他问题 | - | - | {_markdown_cell(issue)} |")
            continue
        dimension = issue.get("related_dimension") or issue.get("target_node_label") or "-"
        context = []
        if issue.get("related_claim_id"):
            context.append(f"Claim #{issue.get('related_claim_id')}")
        if issue.get("related_competitor"):
            context.append(f"竞品：{issue.get('related_competitor')}")
        if issue.get("target_node_label") and issue.get("target_node_label") != dimension:
            context.append(f"节点：{issue.get('target_node_label')}")
        message = issue.get("message") or issue.get("type_label") or issue.get("type") or "未命名问题"
        if context:
            message = f"{message}（{'；'.join(context)}）"
        sections.append(
            "| "
            + " | ".join(
                [
                    str(index),
                    _markdown_cell(issue.get("severity_label") or issue.get("severity") or "-"),
                    _markdown_cell(issue.get("type_label") or issue.get("type") or "-"),
                    _markdown_cell(dimension),
                    _markdown_cell(issue.get("suggested_action_label") or issue.get("suggested_action") or "-"),
                    _markdown_cell(message),
                ]
            )
            + " |"
        )
    return sections


def _finalizer_qa_issues_markdown(finalizer_qa: dict | None, heading_level: int = 2) -> list[str]:
    heading = "#" * heading_level
    if not isinstance(finalizer_qa, dict):
        return ["", f"{heading} 报告总结 Agent QA 问题", "", "暂无报告总结 Agent QA 问题。"]
    issues = finalizer_qa.get("issues") or []
    if not issues:
        return ["", f"{heading} 报告总结 Agent QA 问题", "", "暂无报告总结 Agent QA 问题。"]
    sections = [
        "",
        f"{heading} 报告总结 Agent QA 问题",
        "",
        "| # | 风险级别 | 段落 | Claim | 问题说明 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for index, issue in enumerate(issues, start=1):
        if not isinstance(issue, dict):
            sections.append(f"| {index} | - | - | - | {_markdown_cell(issue)} |")
            continue
        claim_ids = issue.get("claim_ids") if isinstance(issue.get("claim_ids"), list) else []
        sections.append(
            "| "
            + " | ".join(
                [
                    str(index),
                    _markdown_cell(issue.get("severity") or "-"),
                    _markdown_cell(issue.get("paragraph_id") or "-"),
                    _markdown_cell(", ".join(str(item) for item in claim_ids) if claim_ids else "-"),
                    _markdown_cell(issue.get("message") or "未命名问题"),
                ]
            )
            + " |"
        )
    return sections


def _claims_markdown(claims_with_evidence: list[tuple[Claim, list[int]]]) -> str:
    sections = ["", "## 结构化结论"]
    if not claims_with_evidence:
        sections.append("暂无结构化结论。")
        return "\n".join(sections)
    sections.extend(["", "| 竞品 | 维度 | 结论 | 置信度 | 风险 |", "| --- | --- | --- | --- | --- |"])
    for claim, _evidence_ids in claims_with_evidence:
        sections.append(
            "| "
            + " | ".join(
                [
                    _markdown_cell(claim.competitor_name or "-"),
                    _markdown_cell(claim.dimension_label or claim.dimension_key or "-"),
                    _markdown_cell(claim.claim_text),
                    _format_confidence(claim.confidence),
                    _markdown_cell(claim.risk_level or "-"),
                ]
            )
            + " |"
        )
    return "\n".join(sections)


def build_markdown_export(
    report: Report,
    matrices: list[ComparisonMatrix] | None = None,
    qa_payload: dict | None = None,
    claims_with_evidence: list[tuple[Claim, list[int]]] | None = None,
) -> str:
    exported_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    metadata = [
        "<!--",
        f"task_id: {report.task_id}",
        f"report_id: {report.id}",
        f"exported_at: {exported_at}",
        "-->",
        "",
    ]
    content = "\n".join(metadata) + _report_body_markdown(report)
    content += _matrix_markdown(matrices or [])
    content += _claims_markdown(claims_with_evidence or [])
    content += _quality_summary_markdown(report.report_json, qa_payload)
    return content


def _register_pdf_font() -> str:
    from pathlib import Path

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.otf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    ]
    for path in candidates:
        if path.exists():
            try:
                font_name = "CompetitorAgentCJK"
                pdfmetrics.registerFont(TTFont(font_name, str(path)))
                return font_name
            except Exception:
                continue
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


def _is_table_separator(line: str) -> bool:
    if not line.startswith("|"):
        return False
    content = line.replace("|", "").replace(" ", "")
    return bool(content) and set(content) <= {"-", ":"}


def _parse_table_row(line: str) -> list[str]:
    return [cell.strip().replace("<br>", "<br/>") for cell in line.strip().strip("|").split("|")]


def _markdown_blocks(markdown_text: str) -> list[tuple[str, str | list[list[str]]]]:
    blocks: list[tuple[str, str | list[list[str]]]] = []
    table_rows: list[list[str]] = []

    def flush_table() -> None:
        nonlocal table_rows
        if table_rows:
            blocks.append(("table", table_rows))
            table_rows = []

    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            flush_table()
            blocks.append(("space", ""))
            continue
        if line.startswith("# "):
            flush_table()
            blocks.append(("title", line[2:].strip()))
        elif line.startswith("## "):
            flush_table()
            blocks.append(("heading", line[3:].strip()))
        elif line.startswith("### "):
            flush_table()
            blocks.append(("subheading", line[4:].strip()))
        elif _is_table_separator(line):
            continue
        elif line.startswith("|"):
            table_rows.append(_parse_table_row(line))
        elif line.startswith(("- ", "* ")):
            flush_table()
            blocks.append(("body", f"- {line[2:].strip()}"))
        else:
            flush_table()
            clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
            clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
            blocks.append(("body", clean))
    flush_table()
    return blocks


def _pdf_safe_text(text: object) -> str:
    clean = str(text).replace("&", "&amp;").replace("<br/>", "___BR___").replace("<", "&lt;").replace(">", "&gt;")
    clean = clean.replace("___BR___", "<br/>")
    clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", clean)
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
    return clean


def _shorten_pdf_table_cell(text: object, max_chars: int = 220) -> str:
    clean = str(text or "").replace("<br/>", "；").replace("<br>", "；")
    clean = re.sub(r"\s+", " ", clean).strip()
    if len(clean) <= max_chars:
        return clean
    return clean[:max_chars].rstrip() + "..."


def _table_column_chunks(rows: list[list[str]], max_columns: int = 4) -> list[list[list[str]]]:
    if not rows:
        return []
    column_count = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (column_count - len(row)) for row in rows]
    if column_count <= max_columns:
        return [normalized_rows]

    fixed_column = 0
    variable_columns_per_chunk = max_columns - 1
    chunks: list[list[list[str]]] = []
    for start in range(1, column_count, variable_columns_per_chunk):
        indices = [fixed_column, *range(start, min(column_count, start + variable_columns_per_chunk))]
        chunks.append([[row[index] for index in indices] for row in normalized_rows])
    return chunks


def build_pdf_export(
    report: Report,
    matrices: list[ComparisonMatrix] | None = None,
    qa_payload: dict | None = None,
    claims_with_evidence: list[tuple[Claim, list[int]]] | None = None,
) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise RuntimeError("PDF export requires reportlab. Install it with: pip install reportlab") from exc

    font_name = _register_pdf_font()
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=report.title,
    )
    styles = getSampleStyleSheet()
    style_map = {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=styles["Title"],
            fontName=font_name,
            fontSize=20,
            leading=26,
            spaceAfter=14,
        ),
        "heading": ParagraphStyle(
            "ReportHeading",
            parent=styles["Heading2"],
            fontName=font_name,
            fontSize=15,
            leading=20,
            spaceBefore=10,
            spaceAfter=8,
        ),
        "subheading": ParagraphStyle(
            "ReportSubHeading",
            parent=styles["Heading3"],
            fontName=font_name,
            fontSize=12,
            leading=17,
            spaceBefore=8,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "ReportBody",
            parent=styles["BodyText"],
            fontName=font_name,
            fontSize=10.5,
            leading=16,
            spaceAfter=6,
            wordWrap="CJK",
        ),
        "table": ParagraphStyle(
            "ReportTable",
            parent=styles["BodyText"],
            fontName=font_name,
            fontSize=8,
            leading=11,
            wordWrap="CJK",
        ),
        "table_header": ParagraphStyle(
            "ReportTableHeader",
            parent=styles["BodyText"],
            fontName=font_name,
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#1f2937"),
            wordWrap="CJK",
        ),
    }

    story = []
    markdown_text = build_markdown_export(report, matrices, qa_payload, claims_with_evidence)
    page_width = A4[0] - 36 * mm
    for kind, text in _markdown_blocks(markdown_text or report.title):
        if kind == "space":
            story.append(Spacer(1, 5))
            continue
        if kind == "table":
            rows = text if isinstance(text, list) else []
            if not rows:
                continue
            for chunk_index, table_rows in enumerate(_table_column_chunks(rows)):
                if chunk_index:
                    story.append(Spacer(1, 6))
                column_count = max(len(row) for row in table_rows)
                table_data = [
                    [
                        Paragraph(
                            _pdf_safe_text(_shorten_pdf_table_cell(cell, 120 if row_index == 0 else 220)),
                            style_map["table_header"] if row_index == 0 else style_map["table"],
                        )
                        for cell in row
                    ]
                    for row_index, row in enumerate(table_rows)
                ]
                first_column_width = min(90, page_width * 0.24)
                if column_count == 1:
                    column_widths = [page_width]
                else:
                    remaining_width = page_width - first_column_width
                    column_widths = [first_column_width, *[remaining_width / (column_count - 1) for _ in range(column_count - 1)]]
                pdf_table = Table(table_data, colWidths=column_widths, repeatRows=1, hAlign="LEFT", splitByRow=1)
                pdf_table.setStyle(
                    TableStyle(
                        [
                            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d1d5db")),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 4),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ]
                    )
                )
                story.append(pdf_table)
                story.append(Spacer(1, 8))
            continue
        safe_text = _pdf_safe_text(text)
        story.append(Paragraph(safe_text, style_map.get(kind, style_map["body"])))
    document.build(story)
    return buffer.getvalue()
