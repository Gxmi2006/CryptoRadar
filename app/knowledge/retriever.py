from __future__ import annotations

from pathlib import Path
from typing import Any

from app.knowledge.embeddings import EmbeddingService, cosine
from app.knowledge.vector_store import LocalVectorStore


class KnowledgeRetriever:
    def __init__(self, config: dict[str, Any], db: Any, project_root: Path):
        self.config = config
        self.db = db
        self.project_root = project_root
        self.embedder = EmbeddingService(config)
        vector_path = project_root / config["knowledge"].get("vector_db", "./data/vector_db")
        self.local_store = LocalVectorStore(vector_path)

    def retrieve(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        top_k = top_k or int(self.config["knowledge"].get("top_k", 5))
        rows = self.db.query(
            """
            SELECT c.id, c.source_id, c.file_name, c.text, c.embedding_json, c.metadata_json, s.trust_level, s.enabled
            FROM knowledge_chunks c
            LEFT JOIN knowledge_sources s ON s.id = c.source_id
            WHERE COALESCE(s.enabled, 1) = 1
            """
        )
        local_chunks = [] if rows else self.local_store.load()
        if not rows and not local_chunks:
            return []
        vector = self.embedder.embed(query)
        if rows:
            scored = []
            for row in rows:
                chunk_vector = self.db.loads(row.get("embedding_json"), [])
                score = cosine(vector, chunk_vector)
                scored.append((score, row))
            scored.sort(key=lambda item: item[0], reverse=True)
            return [
                {
                    "id": row["id"],
                    "source_id": row["source_id"],
                    "file_name": row["file_name"],
                    "trust_level": row.get("trust_level") or "Medium trust",
                    "text": row["text"],
                    "score": score,
                    "metadata": self.db.loads(row.get("metadata_json"), {}),
                }
                for score, row in scored[:top_k]
                if score > 0
            ]
        scored = []
        for chunk in local_chunks:
            score = cosine(vector, chunk.get("embedding", []))
            scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [{**chunk, "score": score} for score, chunk in scored[:top_k] if score > 0]

    def retrieve_for_market(self, symbol: str, snapshot: dict[str, Any], candle_map: dict[str, Any]) -> list[dict[str, Any]]:
        query = " ".join(
            [
                symbol,
                "technical analysis breakout volume risk management",
                f"24h change {snapshot.get('change_24h')}",
                f"volume {snapshot.get('volume_usdt')}",
                "RSI MACD EMA support resistance fake breakout",
            ]
        )
        return self.retrieve(query)
