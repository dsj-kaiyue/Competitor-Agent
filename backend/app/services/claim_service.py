from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.claim_evidence import ClaimEvidence


def list_claims_with_evidence(db: Session, task_id: int) -> list[tuple[Claim, list[int]]]:
    claims = list(db.scalars(select(Claim).where(Claim.task_id == task_id).order_by(Claim.id)))
    if not claims:
        return []
    ids = [claim.id for claim in claims]
    links = list(db.scalars(select(ClaimEvidence).where(ClaimEvidence.claim_id.in_(ids))))
    evidence_map: dict[int, list[int]] = {}
    for link in links:
        evidence_map.setdefault(link.claim_id, []).append(link.evidence_chunk_id)
    return [(claim, evidence_map.get(claim.id, [])) for claim in claims]
