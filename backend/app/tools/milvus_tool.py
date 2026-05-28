import logging

from app.core.config import settings


logger = logging.getLogger("competitive-agent")


class MilvusTool:
    def __init__(self) -> None:
        self.collection_name = settings.milvus_collection

    def _client(self):
        from pymilvus import MilvusClient

        return MilvusClient(uri=settings.milvus_uri, token=settings.milvus_token)

    def ensure_collection(self, dimension: int) -> None:
        from pymilvus import DataType

        client = self._client()
        if self.collection_name in client.list_collections():
            return
        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.INT64, is_primary=True)
        schema.add_field("task_id", DataType.INT64)
        schema.add_field("chunk_id", DataType.INT64)
        schema.add_field("competitor_name", DataType.VARCHAR, max_length=255)
        schema.add_field("source_type", DataType.VARCHAR, max_length=100)
        schema.add_field("source_url", DataType.VARCHAR, max_length=2048)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dimension)
        index_params = client.prepare_index_params()
        index_params.add_index("embedding", metric_type="COSINE", index_type="AUTOINDEX")
        client.create_collection(self.collection_name, schema=schema, index_params=index_params)
        logger.info("milvus collection created | collection=%s dimension=%s", self.collection_name, dimension)

    def upsert_evidence_embedding(
        self,
        chunk_id: int,
        task_id: int,
        competitor_name: str | None,
        source_type: str | None,
        source_url: str,
        embedding: list[float],
    ) -> str:
        return self.upsert_evidence_embeddings_batch(
            [
                {
                    "chunk_id": chunk_id,
                    "task_id": task_id,
                    "competitor_name": competitor_name,
                    "source_type": source_type,
                    "source_url": source_url,
                    "embedding": embedding,
                }
            ]
        )[0]

    def upsert_evidence_embeddings_batch(self, items: list[dict]) -> list[str]:
        if not items:
            return []
        vector_ids = [f"{item['task_id']}-{item['chunk_id']}" for item in items]
        try:
            first_embedding = items[0].get("embedding") or []
            self.ensure_collection(len(first_embedding))
            client = self._client()
            client.insert(
                collection_name=self.collection_name,
                data=[
                    {
                        "id": item["chunk_id"],
                        "task_id": item["task_id"],
                        "chunk_id": item["chunk_id"],
                        "competitor_name": item.get("competitor_name") or "",
                        "source_type": item.get("source_type") or "",
                        "source_url": item.get("source_url") or "",
                        "embedding": item["embedding"],
                    }
                    for item in items
                ],
            )
            client.flush(self.collection_name)
            logger.info(
                "milvus batch insert completed | collection=%s count=%s first_vector_id=%s",
                self.collection_name,
                len(items),
                vector_ids[0],
            )
        except Exception as exc:
            logger.exception(
                "milvus batch insert failed, fallback to mock vector ids | collection=%s count=%s error=%s",
                self.collection_name,
                len(items),
                exc,
            )
            return [f"mock-{vector_id}" for vector_id in vector_ids]
        return vector_ids

    def search_evidence_embeddings(
        self,
        query_embedding: list[float],
        filter_expr: str,
        top_k: int,
    ) -> list[dict]:
        client = self._client()
        raw_results = client.search(
            collection_name=self.collection_name,
            data=[query_embedding],
            anns_field="embedding",
            filter=filter_expr,
            limit=top_k,
            output_fields=["chunk_id", "task_id", "competitor_name", "source_type", "source_url"],
        )
        hits = raw_results[0] if raw_results else []
        normalized: list[dict] = []
        for hit in hits:
            entity = hit.get("entity", {}) if isinstance(hit, dict) else getattr(hit, "entity", {})
            chunk_id = entity.get("chunk_id") if isinstance(entity, dict) else None
            normalized.append(
                {
                    "chunk_id": int(chunk_id),
                    "score": hit.get("distance") if isinstance(hit, dict) else getattr(hit, "distance", None),
                }
            )
        return normalized
