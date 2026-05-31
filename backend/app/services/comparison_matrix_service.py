from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timezone import now_bj
from app.models.comparison_matrix import ComparisonMatrix
from app.models.competitor_profile import CompetitorProfile


class ComparisonMatrixService:
    def __init__(self, db: Session):
        self.db = db

    def build_matrices_for_task(self, task_id: int) -> list[ComparisonMatrix]:
        return [self.build_overall_matrix(task_id)]

    def build_overall_matrix(self, task_id: int) -> ComparisonMatrix:
        profiles = list(
            self.db.scalars(
                select(CompetitorProfile)
                .where(CompetitorProfile.task_id == task_id)
                .order_by(CompetitorProfile.id)
            )
        )
        if not profiles:
            raise RuntimeError(f"No competitor profiles for task {task_id}")

        schema = profiles[0].profile_schema_json
        columns = [profile.competitor_name for profile in profiles]
        rows = [{"key": field["key"], "label": field["label"]} for field in schema.get("fields", [])]
        matrix_schema = {
            "template_key": schema.get("template_key"),
            "columns": columns,
            "rows": rows,
        }
        matrix_rows = []
        all_claim_ids: set[int] = set()
        all_evidence_ids: set[int] = set()
        for field in schema.get("fields", []):
            values = {}
            for profile in profiles:
                data = (profile.profile_data_json or {}).get(field["key"], {})
                all_claim_ids.update(data.get("claim_ids") or [])
                all_evidence_ids.update(data.get("evidence_ids") or [])
                values[profile.competitor_name] = {
                    "summary": data.get("value"),
                    "claim_ids": data.get("claim_ids") or [],
                    "evidence_ids": data.get("evidence_ids") or [],
                    "confidence": data.get("confidence") or 0,
                }
            matrix_rows.append({"key": field["key"], "label": field["label"], "values": values})
        matrix_data = {"rows": matrix_rows}

        matrix = self.db.scalar(
            select(ComparisonMatrix).where(
                ComparisonMatrix.task_id == task_id,
                ComparisonMatrix.matrix_type == "overall",
            )
        )
        if matrix is None:
            matrix = ComparisonMatrix(
                task_id=task_id,
                template_key=schema.get("template_key"),
                matrix_type="overall",
                title="竞品动态对比矩阵",
                matrix_schema_json=matrix_schema,
                matrix_data_json=matrix_data,
                claim_ids_json=sorted(all_claim_ids),
                evidence_ids_json=sorted(all_evidence_ids),
            )
            self.db.add(matrix)
        else:
            matrix.template_key = schema.get("template_key")
            matrix.title = "竞品动态对比矩阵"
            matrix.matrix_schema_json = matrix_schema
            matrix.matrix_data_json = matrix_data
            matrix.claim_ids_json = sorted(all_claim_ids)
            matrix.evidence_ids_json = sorted(all_evidence_ids)
            matrix.updated_at = now_bj()
        self.db.flush()
        self.db.commit()
        return matrix
