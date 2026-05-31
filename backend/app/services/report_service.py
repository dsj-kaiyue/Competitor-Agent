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


def _qa_markdown(qa_payload: dict | None) -> str:
    sections = ["", "## QA 结果"]
    if not qa_payload:
        sections.append("暂无 QA 结果。")
        return "\n".join(sections)
    passed = "通过" if qa_payload.get("passed") else "未通过"
    score = _format_confidence(qa_payload.get("score"))
    next_action = qa_payload.get("next_action") or "end"
    revision_round = qa_payload.get("revision_round") or 0
    sections.extend(
        [
            "",
            f"- 结果：{passed}",
            f"- 分数：{score}",
            f"- 下一步动作：{next_action}",
            f"- 返工轮次：{revision_round}",
        ]
    )
    target_nodes = qa_payload.get("target_nodes") or []
    if target_nodes:
        sections.append(f"- 目标节点：{', '.join(str(item) for item in target_nodes)}")
    revision_reason = qa_payload.get("revision_reason")
    if revision_reason:
        sections.append(f"- 返工原因：{revision_reason}")
    issues = qa_payload.get("issues") or []
    if not issues:
        sections.append("- 问题：无")
        return "\n".join(sections)
    sections.extend(["", "### QA 问题"])
    for index, issue in enumerate(issues, start=1):
        if not isinstance(issue, dict):
            sections.append(f"{index}. {issue}")
            continue
        details = [
            f"严重级别：{issue.get('severity') or '-'}",
            f"建议动作：{issue.get('suggested_action') or '-'}",
        ]
        if issue.get("related_claim_id"):
            details.append(f"Claim #{issue.get('related_claim_id')}")
        if issue.get("related_competitor"):
            details.append(f"竞品：{issue.get('related_competitor')}")
        if issue.get("target_node"):
            details.append(f"节点：{issue.get('target_node')}")
        sections.append(f"{index}. {issue.get('message') or issue.get('type') or '未命名问题'}（{'；'.join(details)}）")
    return "\n".join(sections)


def _claims_markdown(claims_with_evidence: list[tuple[Claim, list[int]]]) -> str:
    sections = ["", "## 结构化结论"]
    if not claims_with_evidence:
        sections.append("暂无结构化结论。")
        return "\n".join(sections)
    sections.extend(["", "| ID | 竞品 | 类型 | 结论 | 置信度 | 风险 | Evidence |", "| --- | --- | --- | --- | --- | --- | --- |"])
    for claim, evidence_ids in claims_with_evidence:
        sections.append(
            "| "
            + " | ".join(
                [
                    str(claim.id),
                    _markdown_cell(claim.competitor_name or "-"),
                    _markdown_cell(claim.claim_type or "-"),
                    _markdown_cell(claim.claim_text),
                    _format_confidence(claim.confidence),
                    _markdown_cell(claim.risk_level or "-"),
                    _markdown_cell(", ".join(str(item) for item in evidence_ids) if evidence_ids else "-"),
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
    content = "\n".join(metadata) + (report.content_markdown or "")
    content += _matrix_markdown(matrices or [])
    content += _qa_markdown(qa_payload)
    content += _claims_markdown(claims_with_evidence or [])
    return content


def _register_pdf_font() -> str:
    from pathlib import Path

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    ]
    for path in candidates:
        if path.exists():
            font_name = "CompetitorAgentCJK"
            pdfmetrics.registerFont(TTFont(font_name, str(path)))
            return font_name
    return "Helvetica"


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
