from pathlib import Path
import os
import sys


os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.models.report import Report
from app.services.report_service import build_markdown_export


def test_markdown_export_places_executive_summary_before_dimensions_and_conclusion_after_dimensions():
    report = Report(
        task_id=1,
        title="测试报告",
        content_markdown="# 旧报告\n\n## 总体结论\n\n旧总结\n\n## 安全合规\n\n旧正文",
        report_json={
            "title": "测试报告",
            "sections": [
                {
                    "section_id": "risk_notes",
                    "title": "风险提示",
                    "paragraphs": [{"paragraph_id": "risk_p1", "text": "不应导出", "claim_ids": [3], "evidence_ids": [30]}],
                },
                {
                    "section_id": "overall_conclusion",
                    "title": "总体结论",
                    "paragraphs": [{"paragraph_id": "overall_p1", "text": "最终总结", "claim_ids": [2], "evidence_ids": [20]}],
                },
                {
                    "section_id": "executive_summary",
                    "title": "执行摘要",
                    "paragraphs": [{"paragraph_id": "summary_p1", "text": "摘要内容", "claim_ids": [1], "evidence_ids": [10]}],
                },
                {
                    "section_id": "security",
                    "title": "安全合规",
                    "paragraphs": [{"paragraph_id": "security_p1", "text": "维度正文", "claim_ids": [1], "evidence_ids": [10]}],
                },
            ],
            "quality_summary": {"final_status": "未通过"},
            "finalizer_qa": {
                "issues": [
                    {
                        "severity": "high",
                        "paragraph_id": "overall_p1",
                        "claim_ids": [2],
                        "message": "总体结论引用的 Claim 支撑不足",
                    }
                ]
            },
        },
    )

    markdown = build_markdown_export(report)

    assert markdown.index("## 执行摘要") < markdown.index("## 安全合规")
    assert markdown.index("## 安全合规") < markdown.index("## 总体结论")
    assert "## 风险提示" not in markdown
    assert "不应导出" not in markdown
    assert "### 报告总结 Agent QA 问题" in markdown
    assert "总体结论引用的 Claim 支撑不足" in markdown
