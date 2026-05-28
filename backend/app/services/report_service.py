from datetime import datetime
from io import BytesIO
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.report import Report


def get_report(db: Session, task_id: int) -> Report | None:
    return db.scalar(select(Report).where(Report.task_id == task_id).order_by(Report.id.desc()))


def safe_report_filename(report: Report, extension: str) -> str:
    title = re.sub(r"[\\/:*?\"<>|\s]+", "_", report.title or f"analysis_report_{report.task_id}").strip("_")
    if not title:
        title = f"analysis_report_{report.task_id}"
    return f"{title[:80]}.{extension}"


def build_markdown_export(report: Report) -> str:
    exported_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    metadata = [
        "<!--",
        f"task_id: {report.task_id}",
        f"report_id: {report.id}",
        f"exported_at: {exported_at}",
        "-->",
        "",
    ]
    return "\n".join(metadata) + (report.content_markdown or "")


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


def _plain_report_lines(markdown_text: str) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            lines.append(("space", ""))
            continue
        if line.startswith("# "):
            lines.append(("title", line[2:].strip()))
        elif line.startswith("## "):
            lines.append(("heading", line[3:].strip()))
        elif line.startswith("### "):
            lines.append(("subheading", line[4:].strip()))
        elif line.startswith(("- ", "* ")):
            lines.append(("body", f"- {line[2:].strip()}"))
        else:
            clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
            clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
            lines.append(("body", clean))
    return lines


def build_pdf_export(report: Report) -> bytes:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
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
    }

    story = []
    for kind, text in _plain_report_lines(report.content_markdown or report.title):
        if kind == "space":
            story.append(Spacer(1, 5))
            continue
        safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(Paragraph(safe_text, style_map.get(kind, style_map["body"])))
    document.build(story)
    return buffer.getvalue()
