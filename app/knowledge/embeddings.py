from __future__ import annotations

import hashlib
import math
import re
from typing import Any

from app.ai.ollama_client import OllamaClient


TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


class EmbeddingService:
    def __init__(self, config: dict[str, Any]):
        ai_cfg = config.get("ai", {})
        self.ollama = OllamaClient(ai_cfg.get("base_url", "http://localhost:11434"))
        self.model = ai_cfg.get("embedding_model", "nomic-embed-text")
        self.use_ollama = ai_cfg.get("provider", "ollama") == "ollama"

    def embed(self, text: str) -> list[float]:
        if self.use_ollama:
            vector = self.ollama.embed(self.model, text)
            if vector:
                return normalize(vector)
        return hashing_embedding(text)


def hashing_embedding(text: str, dimensions: int = 384) -> list[float]:
    vector = [0.0] * dimensions
    for token in TOKEN_RE.findall(text.lower()):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1 if digest[4] % 2 == 0 else -1
        vector[bucket] += sign
    return normalize(vector)


def normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [value / norm for value in vector]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    size = min(len(a), len(b))
    return sum(a[index] * b[index] for index in range(size))
