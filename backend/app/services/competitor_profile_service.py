from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timezone import now_bj
from app.models.analysis_task import AnalysisTask
from app.models.claim import Claim
from app.models.claim_evidence import ClaimEvidence
from app.models.competitor_profile import CompetitorProfile
from app.services.profile_schema_builder import ProfileSchemaBuilder
from app.services.task_service import get_task_plan


CLAIM_TYPE_FIELDS = {
    "pricing": {"pricing_strategy"},
    "security": {"security_compliance", "enterprise_capabilities"},
    "market": {"target_users", "positioning"},
    "feature": {"core_features", "agent_capabilities", "ide_integration"},
}


def _confidence_value(value: Decimal | None) -> float:
    return float(value) if value is not None else 0.75


class CompetitorProfileService:
    def __init__(self, db: Session):
        self.db = db

    def build_profiles_for_task(self, task_id: int) -> list[CompetitorProfile]:
        task = self.db.get(AnalysisTask, task_id)
        if task is None:
            raise RuntimeError(f"Task {task_id} not found")
        plan = get_task_plan(task)
        schema = ProfileSchemaBuilder().build_schema(plan.model_dump())
        profiles = [
            self.build_profile_for_competitor(task_id, competitor_name, schema)
            for competitor_name in plan.competitors
            if competitor_name.strip()
        ]
        self.db.commit()
        return profiles

    def build_profile_for_competitor(
        self,
        task_id: int,
        competitor_name: str,
        profile_schema: dict,
    ) -> CompetitorProfile:
        claims = list(
            self.db.scalars(
                select(Claim)
                .where(Claim.task_id == task_id, Claim.competitor_name == competitor_name)
                .order_by(Claim.id)
            )
        )
        evidence_by_claim = self._evidence_by_claim([claim.id for claim in claims])
        profile_data: dict[str, dict] = {}
        all_claim_ids: set[int] = set()
        all_evidence_ids: set[int] = set()

        for field in profile_schema.get("fields", []):
            matched = self._match_claims(field, claims)
            claim_ids = [claim.id for claim in matched]
            evidence_ids = sorted({eid for claim_id in claim_ids for eid in evidence_by_claim.get(claim_id, [])})
            all_claim_ids.update(claim_ids)
            all_evidence_ids.update(evidence_ids)
            if not matched:
                profile_data[field["key"]] = {
                    "value": None,
                    "claim_ids": [],
                    "evidence_ids": [],
                    "confidence": 0,
                    "missing_reason": "缺少相关 Claim",
                }
                continue

            if field.get("type") == "list":
                value: str | list[str] = [claim.claim_text for claim in matched[:5]]
            else:
                value = "；".join(claim.claim_text for claim in matched[:3])
            profile_data[field["key"]] = {
                "value": value,
                "claim_ids": claim_ids,
                "evidence_ids": evidence_ids,
                "confidence": round(sum(_confidence_value(claim.confidence) for claim in matched) / len(matched), 2),
            }

        profile = self.db.scalar(
            select(CompetitorProfile).where(
                CompetitorProfile.task_id == task_id,
                CompetitorProfile.competitor_name == competitor_name,
            )
        )
        if profile is None:
            profile = CompetitorProfile(
                task_id=task_id,
                competitor_name=competitor_name,
                template_key=profile_schema.get("template_key"),
                profile_schema_json=profile_schema,
                profile_data_json=profile_data,
                claim_ids_json=sorted(all_claim_ids),
                evidence_ids_json=sorted(all_evidence_ids),
            )
            self.db.add(profile)
        else:
            profile.template_key = profile_schema.get("template_key")
            profile.profile_schema_json = profile_schema
            profile.profile_data_json = profile_data
            profile.claim_ids_json = sorted(all_claim_ids)
            profile.evidence_ids_json = sorted(all_evidence_ids)
            profile.updated_at = now_bj()
        self.db.flush()
        return profile

    def _evidence_by_claim(self, claim_ids: list[int]) -> dict[int, list[int]]:
        if not claim_ids:
            return {}
        rows = list(self.db.scalars(select(ClaimEvidence).where(ClaimEvidence.claim_id.in_(claim_ids))))
        result: dict[int, list[int]] = {}
        for row in rows:
            result.setdefault(row.claim_id, []).append(row.evidence_chunk_id)
        return result

    def _match_claims(self, field: dict, claims: list[Claim]) -> list[Claim]:
        key = str(field.get("key") or "")
        label = str(field.get("label") or "")
        matched: list[Claim] = []
        for claim in claims:
            claim_type = claim.claim_type or ""
            text = claim.claim_text or ""
            if key in CLAIM_TYPE_FIELDS.get(claim_type, set()):
                matched.append(claim)
                continue
            if label and label in text:
                matched.append(claim)
                continue
            if key and key.replace("_", " ") in text.lower():
                matched.append(claim)
        return matched
