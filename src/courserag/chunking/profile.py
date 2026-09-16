from __future__ import annotations

from pathlib import Path

from courserag.domain.chunk import ChunkProfile


def load_chunk_profile(path: Path) -> ChunkProfile:
    if not path.is_file():
        raise FileNotFoundError(f"Chunk Profile not found: {path}")
    return ChunkProfile.model_validate_json(path.read_text(encoding="utf-8"))
