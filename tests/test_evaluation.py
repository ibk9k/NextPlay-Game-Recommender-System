import pytest

import game_recommender.evaluation as evaluation_module
from game_recommender.evaluation import evaluate


def test_evaluation_removes_every_held_out_pair_from_model_training(small_catalog, monkeypatch):
    captured = []
    actual = evaluation_module.RecommendationEngine

    def capture(catalog):
        captured.append(catalog)
        return actual(catalog)

    monkeypatch.setattr(evaluation_module, "RecommendationEngine", capture)
    result = evaluate(small_catalog, seed=42, k=3)
    original = {(i.user_id, i.app_id) for i in small_catalog.interactions}
    trained = {(i.user_id, i.app_id) for i in captured[0].interactions}
    held_out = original - trained
    assert len(held_out) == result["evaluated_users"] == 5
    assert len({user_id for user_id, _ in held_out}) == 5
    assert len(trained) + len(held_out) == len(original)
    assert result["synthetic_data"]
    assert set(result["models"]) == {"popularity", "content", "collaborative"}
    for metrics in result["models"].values():
        assert metrics["recall@3"] == round(metrics["hits"] / len(held_out), 6)
        assert 0 <= metrics["recall@3"] <= 1
        assert 0 <= metrics["ndcg@3"] <= 1
        assert 0 <= metrics["catalog_coverage"] <= 1


def test_evaluation_is_reproducible_and_labels_demo(demo_catalog):
    result = evaluate(demo_catalog)
    assert result == evaluate(demo_catalog)
    assert result["evaluated_users"] == 32
    assert "not real" in result["note"]


def test_evaluation_rejects_invalid_k(small_catalog):
    with pytest.raises(ValueError, match="k must"):
        evaluate(small_catalog, k=11)
