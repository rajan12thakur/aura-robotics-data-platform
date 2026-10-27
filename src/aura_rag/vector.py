from __future__ import annotations

import hashlib
import importlib.util
import os
from functools import lru_cache
from pathlib import Path
from typing import Protocol


class EmbeddingProvider(Protocol):
    model_name: str
    model_revision: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LocalSentenceTransformer:
    def __init__(self, model_path: Path, model_name: str, model_revision: str):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.model_revision = model_revision
        self._model = SentenceTransformer(
            str(model_path), device="cpu", model_kwargs={"local_files_only": True},
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False,
        )
        return vectors.tolist()


class PersistentChromaStore:
    def __init__(self, path: Path, model_name: str, model_revision: str):
        from chromadb import PersistentClient
        from chromadb.config import Settings

        self._client = PersistentClient(
            path=str(path), settings=Settings(anonymized_telemetry=False),
        )
        collection_key = model_name if not model_revision else f"{model_name}:{model_revision}"
        collection_suffix = hashlib.sha256(collection_key.encode("utf-8")).hexdigest()[:16]
        self._collection = self._client.get_or_create_collection(
            f"aura_knowledge_{collection_suffix}",
            metadata={
                "hnsw:space": "cosine",
                "model_name": model_name,
                "model_revision": model_revision,
            },
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


def model_directory_revision(model_path: Path) -> str:
    configured_revision = os.getenv("AURA_EMBEDDING_MODEL_REVISION", "").strip()
    if configured_revision:
        return configured_revision[:128]
    files = sorted(path for path in model_path.rglob("*") if path.is_file())
    manifest = "\n".join(
        f"{path.relative_to(model_path)}:{path.stat().st_size}:{path.stat().st_mtime_ns}"
        for path in files
    )
    return hashlib.sha256(manifest.encode("utf-8")).hexdigest()[:32]


def configured_model_identity() -> tuple[str, str] | None:
    model_path_value = os.getenv("AURA_EMBEDDING_MODEL_PATH", "").strip()
    if not model_path_value:
        return None
    model_path = Path(model_path_value)
    if not model_path.is_dir():
        return None
    model_name = os.getenv("AURA_EMBEDDING_MODEL", model_path.name)
    return model_name, model_directory_revision(model_path)


@lru_cache(maxsize=1)
def _load_embedding_provider(
    model_path: str, model_name: str, model_revision: str,
) -> LocalSentenceTransformer:
    return LocalSentenceTransformer(Path(model_path), model_name, model_revision)


def configured_embedding_provider() -> LocalSentenceTransformer | None:
    model_path = os.getenv("AURA_EMBEDDING_MODEL_PATH", "").strip()
    if not model_path or not Path(model_path).is_dir():
        return None
    model_name = os.getenv("AURA_EMBEDDING_MODEL", Path(model_path).name)
    model_revision = model_directory_revision(Path(model_path))
    return _load_embedding_provider(str(Path(model_path).resolve()), model_name, model_revision)


def dense_backend_status() -> dict[str, object]:
    model_path = os.getenv("AURA_EMBEDDING_MODEL_PATH", "").strip()
    model_configured = bool(model_path and Path(model_path).is_dir())
    embedding_installed = importlib.util.find_spec("sentence_transformers") is not None
    chroma_installed = importlib.util.find_spec("chromadb") is not None
    return {
        "model_configured": model_configured,
        "sentence_transformers_installed": embedding_installed,
        "chroma_installed": chroma_installed,
        "available": model_configured and embedding_installed and chroma_installed,
    }


def configured_vector_store(
    path: Path, model_name: str, model_revision: str,
) -> PersistentChromaStore | None:
    try:
        import chromadb  # noqa: F401
    except ImportError:
        return None
    return PersistentChromaStore(path, model_name, model_revision)
