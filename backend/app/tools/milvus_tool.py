from app.core.config import settings


class MilvusTool:
    def __init__(self) -> None:
        self.collection_name = settings.milvus_collection

    def upsert_evidence_embedding(
        self,
        chunk_id: int,
        task_id: int,
        competitor_name: str | None,
        source_type: str | None,
        source_url: str,
        embedding: list[float],
    ) -> str:
        vector_id = f"{task_id}-{chunk_id}"
        try:
            from pymilvus import MilvusClient

            client = MilvusClient(uri=settings.milvus_uri, token=settings.milvus_token)
            client.insert(
                collection_name=self.collection_name,
                data=[
                    {
                        "id": chunk_id,
                        "task_id": task_id,
                        "chunk_id": chunk_id,
                        "competitor_name": competitor_name or "",
                        "source_type": source_type or "",
                        "source_url": source_url,
                        "embedding": embedding,
                    }
                ],
            )
        except Exception:
            return f"mock-{vector_id}"
        return vector_id
