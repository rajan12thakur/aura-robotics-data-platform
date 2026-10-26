from __future__ import annotations

import os
import hashlib
from pathlib import Path
from typing import Protocol


class EmbeddingProvider(Protocol):
    model_name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LocalSentenceTransformer:
    def __init__(self, model_path: Path, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self._model = SentenceTransformer(
            str(model_path), device="cpu", model_kwargs={"local_files_only": True},
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False,
        )
        return vectors.tolist()


class PersistentChromaStore:
    def __init__(self, path: Path, model_name: str):
        from chromadb import PersistentClient
        from chromadb.config import Settings

        self._client = PersistentClient(
            path=str(path), settings=Settings(anonymized_telemetry=False),
        )
        collection_suffix = hashlib.sha256(model_name.encode("utf-8")).hexdigest()[:16]
        self._collection = self._client.get_or_create_collection(
            f"aura_knowledge_{collection_suffix}", metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, ids: list[str], texts: list[str], embeddings: list[list[float]], metadatas: list[dict]):
        self._collection.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)

    def delete(self, ids: list[str]):
        if ids:
            self._collection.delete(ids=ids)

    def query(self, text: str, embedding: list[float], project_id: str, source_ids: list[str], limit: int):
        if not source_ids:
            return []
        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=limit,
            where={"$and": [{"project_id": project_id}, {"source_id": {"$in": source_ids}}]},
            include=["distances", "metadatas"],
        )
        identifiers = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        return [{"id": identifier, "distance": distances[index]} for index, identifier in enumerate(identifiers)]


def configured_embedding_provider() -> LocalSentenceTransformer | None:
    model_path = os.getenv("AURA_EMBEDDING_MODEL_PATH", "").strip()
    if not model_path or not Path(model_path).is_dir():
        return None
    model_name = os.getenv("AURA_EMBEDDING_MODEL", Path(model_path).name)
    return LocalSentenceTransformer(Path(model_path), model_name)


def configured_vector_store(path: Path, model_name: str) -> PersistentChromaStore | None:
    try:
        import chromadb  # noqa: F401
    except ImportError:
        return None
    return PersistentChromaStore(path, model_name)
