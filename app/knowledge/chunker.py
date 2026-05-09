from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    index: int


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 160) -> list[Chunk]:
    clean = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not clean:
        return []
    chunks: list[Chunk] = []
    start = 0
    index = 0
    step = max(1, chunk_size - overlap)
    while start < len(clean):
        end = min(len(clean), start + chunk_size)
        chunks.append(Chunk(text=clean[start:end], index=index))
        index += 1
        if end >= len(clean):
            break
        start += step
    return chunks
