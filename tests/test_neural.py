import json
from dataclasses import replace

import numpy as np
import pytest

from game_recommender.neural import NeuralSearch, NeuralUnavailable


def write_index(path, catalog):
    path.mkdir()
    dimension = len(catalog.games)
    np.save(path / "embeddings.npy", np.eye(dimension, dtype=np.float32))
    (path / "neural.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "catalog_fingerprint": catalog.fingerprint,
                "model_id": "test-encoder",
                "app_ids": [g.app_id for g in catalog.games],
                "dimensions": dimension,
            }
        ),
        encoding="utf-8",
    )


def test_neural_without_index_reports_unavailable(tmp_path, small_catalog):
    search = NeuralSearch(small_catalog, tmp_path)
    assert not search.ready
    with pytest.raises(NeuralUnavailable, match="build-neural"):
        search.search("a quiet space adventure")


def test_index_is_invalidated_when_game_description_changes(tmp_path, small_catalog):
    path = tmp_path / "index"
    write_index(path, small_catalog)
    assert NeuralSearch(small_catalog, path).ready
    updated_games = (
        replace(small_catalog.games[0], description="A different game description."),
        *small_catalog.games[1:],
    )
    changed = replace(small_catalog, games=updated_games)
    search = NeuralSearch(changed, path)
    assert not search.ready
    assert "another catalogue" in search.unavailable_reason


def test_corrupt_embeddings_are_rejected(tmp_path, small_catalog):
    path = tmp_path / "index"
    write_index(path, small_catalog)
    bad = np.eye(len(small_catalog.games))
    bad[0, 0] = float("nan")
    np.save(path / "embeddings.npy", bad)
    assert not NeuralSearch(small_catalog, path).ready


def test_neural_ranks_query_embeddings_without_lexical_substitution(tmp_path, small_catalog):
    path = tmp_path / "index"
    write_index(path, small_catalog)
    search = NeuralSearch(small_catalog, path)

    class TestEncoder:
        def encode(self, texts, **kwargs):
            # Unit fixture only: actual model installation is a separate integration step.
            vector = np.zeros((1, len(small_catalog.games)), dtype=np.float32)
            vector[0, 1] = 1
            return vector

    search.encoder = TestEncoder()
    result = search.search("a quiet space adventure", 2)
    assert result.method == "neural"
    assert result.results[0].app_id == 2
    assert result.results[0].score == 1
