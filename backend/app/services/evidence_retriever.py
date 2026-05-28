from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence_chunk import EvidenceChunk
from app.services.log_service import add_log
from app.tools.llm_client import LLMClient
from app.tools.milvus_tool import MilvusTool


class EvidenceRetriever:
    def __init__(self, db: Session):
        self.db = db
        self.llm = LLMClient()
        self.milvus = MilvusTool()
        self.last_search_log: dict = {}

    def search(
        self,
        task_id: int,
        query: str,
        competitor_name: str | None = None,
        source_type: str | None = None,
        top_k: int = 8,
        node_id: int | None = None,
    ) -> list[EvidenceChunk]:
        filter_expr = f"task_id == {task_id}"
        if competitor_name:
            filter_expr += f' and competitor_name == "{competitor_name}"'
        if source_type:
            filter_expr += f' and source_type == "{source_type}"'

        try:
            query_embedding = self.llm.embed_text(query)
            results = self.milvus.search_evidence_embeddings(query_embedding, filter_expr, top_k)
            chunk_ids = [item["chunk_id"] for item in results if item.get("chunk_id")]
            chunks = self._chunks_by_ids(chunk_ids)
            if not chunks:
                raise RuntimeError("Milvus returned no chunks")
            self.last_search_log = {
                "retrieval_mode": "milvus_rag",
                "query": query,
                "competitor_name": competitor_name,
                "source_type": source_type,
                "top_k": top_k,
                "retrieved_chunk_ids": [chunk.id for chunk in chunks],
                "fallback_used": False,
            }
        except Exception as exc:
            chunks = self._fallback_chunks(task_id, competitor_name, source_type, top_k)
            self.last_search_log = {
                "retrieval_mode": "mysql_fallback",
                "query": query,
                "competitor_name": competitor_name,
                "source_type": source_type,
                "top_k": top_k,
                "retrieved_chunk_ids": [chunk.id for chunk in chunks],
                "fallback_used": True,
                "reason": f"Milvus search failed: {exc}",
            }

        add_log(self.db, task_id, node_id, "Evidence retrieval completed", self.last_search_log)
        self.db.commit()
        return chunks

    def _chunks_by_ids(self, chunk_ids: list[int]) -> list[EvidenceChunk]:
        if not chunk_ids:
            return []
        chunks = list(self.db.scalars(select(EvidenceChunk).where(EvidenceChunk.id.in_(chunk_ids))))
        chunk_by_id = {chunk.id: chunk for chunk in chunks}
        return [chunk_by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in chunk_by_id]

    def _fallback_chunks(
        self,
        task_id: int,
        competitor_name: str | None,
        source_type: str | None,
        top_k: int,
    ) -> list[EvidenceChunk]:
        stmt = select(EvidenceChunk).where(EvidenceChunk.task_id == task_id)
        if competitor_name:
            stmt = stmt.where(EvidenceChunk.competitor_name == competitor_name)
        if source_type:
            stmt = stmt.where(EvidenceChunk.source_type == source_type)
        stmt = stmt.order_by(EvidenceChunk.reliability_score.desc(), EvidenceChunk.id).limit(top_k)
        return list(self.db.scalars(stmt))
