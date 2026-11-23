"""Optional neural retrieval. Never silently substitute lexical search for neural inference."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

import numpy as np

from game_recommender.catalog import Catalog
from game_recommender.engine import RankedGame, Recommendation

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class NeuralUnavailable(RuntimeError):
    pass


def sentence_encoder(model_id: str, *, local_only=False, cache_folder: Path | None = None):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise NeuralUnavailable("Install the neural extra: pip install -e '.[neural]'.") from exc
    try:
        return SentenceTransformer(
            model_id,
            local_files_only=local_only,
            cache_folder=str(cache_folder) if cache_folder else None,
        )
    except OSError as exc:
        raise NeuralUnavailable(
            "Encoder unavailable locally. Run game-rs build-neural first."
        ) from exc


def build_index(catalog: Catalog, directory: Path, model_id=DEFAULT_MODEL, batch_size=32) -> dict:
    encoder = sentence_encoder(model_id, cache_folder=directory / "models")
    embeddings = encoder.encode(
        [g.search_text for g in catalog.games],
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype(np.float32)
    directory.mkdir(parents=True, exist_ok=True)
    metadata = {
        "schema_version": 1,
        "catalog_fingerprint": catalog.fingerprint,
        "model_id": model_id,
        "app_ids": [g.app_id for g in catalog.games],
        "dimensions": int(embeddings.shape[1]),
        "pretrained": True,
    }
    # The manifest is the completion marker; incomplete builds are never used.
    marker = directory / "neural.json"
    marker.unlink(missing_ok=True)
    np.save(directory / "embeddings.npy", embeddings, allow_pickle=False)
    marker.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


class NeuralSearch:
    def __init__(self, catalog: Catalog, directory: Path):
        self.catalog = catalog
        self.directory = directory
        self.encoder = None
        self.lock = Lock()
        self.metadata = None
        self.embeddings = None
        self.unavailable_reason = "Neural index not built. Run game-rs build-neural."
        marker = directory / "neural.json"
        if not marker.exists():
            return
        try:
            metadata = json.loads(marker.read_text(encoding="utf-8"))
            if (
                metadata.get("schema_version") != 1
                or metadata.get("catalog_fingerprint") != catalog.fingerprint
                or metadata.get("app_ids") != [g.app_id for g in catalog.games]
                or not isinstance(metadata.get("model_id"), str)
            ):
                self.unavailable_reason = "Neural index belongs to another catalogue. Rebuild it."
                return
            embeddings = np.load(directory / "embeddings.npy", allow_pickle=False)
            if (
                embeddings.shape != (len(catalog.games), metadata["dimensions"])
                or not np.isfinite(embeddings).all()
                or not np.allclose(np.linalg.norm(embeddings, axis=1), 1, atol=1e-3)
            ):
                self.unavailable_reason = "Neural index is invalid. Rebuild it."
                return
            self.metadata = metadata
            self.embeddings = embeddings
            self.unavailable_reason = ""
        except (ValueError, OSError, KeyError, TypeError):
            self.unavailable_reason = "Neural index cannot be read. Rebuild it."

    @property
    def ready(self) -> bool:
        return self.embeddings is not None

    def search(self, query: str, limit=10) -> Recommendation:
        if not self.ready:
            raise NeuralUnavailable(self.unavailable_reason)
        with self.lock:
            if self.encoder is None:
                self.encoder = sentence_encoder(
                    self.metadata["model_id"],
                    local_only=True,
                    cache_folder=self.directory / "models",
                )
            query_vector = self.encoder.encode(
                [query], normalize_embeddings=True, convert_to_numpy=True
            )[0]
        scores = self.embeddings @ query_vector
        order = sorted(
            range(len(scores)), key=lambda i: (-float(scores[i]), self.catalog.games[i].app_id)
        )[:limit]
        return Recommendation(
            tuple(
                RankedGame(
                    self.catalog.games[i].app_id,
                    round(float(scores[i]), 6),
                    "Semantically similar to your description.",
                )
                for i in order
            ),
            "neural",
            message=f"Pretrained encoder: {self.metadata['model_id']}",
        )
