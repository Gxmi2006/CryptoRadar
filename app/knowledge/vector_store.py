from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.knowledge.chunker import chunk_text
from app.knowledge.document_loader import DocumentLoader
from app.knowledge.embeddings import EmbeddingService, cosine
from app.knowledge.source_quality import assess_source


class LocalVectorStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.mkdir(parents=True, exist_ok=True)
        self.index_path = self.path / "chunks.json"

    def save(self, chunks: list[dict[str, Any]]) -> None:
        self.index_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self) -> list[dict[str, Any]]:
        if not self.index_path.exists():
            return []
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def search(self, query_vector: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        scored = []
        for chunk in self.load():
            score = cosine(query_vector, chunk.get("embedding", []))
            scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [{**chunk, "score": score} for score, chunk in scored[:top_k] if score > 0]


class ChromaVectorStore:
    def __init__(self, path: Path):
        import chromadb

        self.client = chromadb.PersistentClient(path=str(path))
        self.collection = self.client.get_or_create_collection("cryptoradar")

    def save(self, chunks: list[dict[str, Any]]) -> None:
        if not chunks:
            return
        try:
            existing = self.collection.get(include=[])
            ids = existing.get("ids", [])
            if ids:
                self.collection.delete(ids=ids)
        except Exception:
            pass
        self.collection.add(
            ids=[chunk["id"] for chunk in chunks],
            documents=[chunk["text"] for chunk in chunks],
            embeddings=[chunk["embedding"] for chunk in chunks],
            metadatas=[
                {
                    "file_name": chunk["file_name"],
                    "source_id": chunk["source_id"],
                    "trust_level": chunk.get("trust_level", "Medium trust"),
                }
                for chunk in chunks
            ],
        )

    def search(self, query_vector: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        results = self.collection.query(query_embeddings=[query_vector], n_results=top_k)
        chunks: list[dict[str, Any]] = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0] if results.get("distances") else [0] * len(ids)
        for chunk_id, text, meta, distance in zip(ids, docs, metas, distances):
            chunks.append({"id": chunk_id, "text": text, **meta, "score": 1 - float(distance)})
        return chunks


def open_vector_store(path: Path) -> Any:
    try:
        return ChromaVectorStore(path)
    except Exception:
        return LocalVectorStore(path)


def rebuild_knowledge_index(config: dict[str, Any], db: Any, project_root: Path) -> str:
    folder = project_root / config["knowledge"].get("folder", "./knowledge")
    vector_path = project_root / config["knowledge"].get("vector_db", "./data/vector_db")
    loader = DocumentLoader(folder)
    embedder = EmbeddingService(config)
    all_chunks: list[dict[str, Any]] = []
    docs = loader.load()
    db.execute("DELETE FROM knowledge_chunks")

    for doc in docs:
        quality = assess_source(doc.path, doc.text)
        db.execute(
            """
            INSERT INTO knowledge_sources(
                id, file_name, source_title, author, source_date, category, trust_level,
                enabled, notes, performance_score, warnings_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                file_name=excluded.file_name,
                source_title=excluded.source_title,
                category=excluded.category,
                trust_level=excluded.trust_level,
                enabled=excluded.enabled,
                notes=excluded.notes,
                warnings_json=excluded.warnings_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                quality["id"],
                quality["file_name"],
                quality["source_title"],
                quality["author"],
                quality["source_date"],
                quality["category"],
                quality["trust_level"],
                quality["enabled"],
                quality["notes"],
                quality["performance_score"],
                db.dumps(quality["warnings"]),
            ),
        )
        for chunk in chunk_text(
            doc.text,
            int(config["knowledge"].get("chunk_size", 1200)),
            int(config["knowledge"].get("chunk_overlap", 160)),
        ):
            chunk_id = f"{quality['id']}-{chunk.index}"
            vector = embedder.embed(chunk.text)
            payload = {
                "id": chunk_id,
                "source_id": quality["id"],
                "file_name": quality["file_name"],
                "trust_level": quality["trust_level"],
                "chunk_index": chunk.index,
                "text": chunk.text,
                "embedding": vector,
                "metadata": quality,
            }
            all_chunks.append(payload)
            db.execute(
                """
                INSERT INTO knowledge_chunks(id, source_id, file_name, chunk_index, text, embedding_json, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    quality["id"],
                    quality["file_name"],
                    chunk.index,
                    chunk.text,
                    db.dumps(vector),
                    db.dumps(quality),
                ),
            )

    store = open_vector_store(vector_path)
    store.save(all_chunks)
    return f"Knowledge index rebuilt. Sources={len(docs)}, chunks={len(all_chunks)}, store={type(store).__name__}."
