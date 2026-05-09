from __future__ import annotations

from pathlib import Path

from app.knowledge.retriever import KnowledgeRetriever
from app.knowledge.vector_store import LocalVectorStore, rebuild_knowledge_index


def test_rag_retrieval_and_source_citation(config: dict, db, tmp_path: Path, monkeypatch) -> None:
    knowledge_dir = Path(config["knowledge"]["folder"])
    knowledge_dir.mkdir(parents=True)
    (knowledge_dir / "breakout-risk.md").write_text(
        "Breakout trading needs volume confirmation, invalidation, stop loss, and risk management.",
        encoding="utf-8",
    )

    import app.knowledge.vector_store as vector_store_module

    monkeypatch.setattr(vector_store_module, "open_vector_store", lambda path: LocalVectorStore(path))
    summary = rebuild_knowledge_index(config, db, tmp_path)
    assert "chunks=1" in summary

    retriever = KnowledgeRetriever(config, db, tmp_path)
    chunks = retriever.retrieve("volume breakout invalidation risk", top_k=3)
    assert chunks
    assert chunks[0]["file_name"] == "breakout-risk.md"
