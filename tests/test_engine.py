import pytest

from game_recommender.engine import RecommendationEngine


def ids(result):
    return [item.app_id for item in result.results]


def test_content_rewards_likes_penalizes_dislikes_and_excludes_seen(small_catalog):
    model = RecommendationEngine(small_catalog)
    result = model.content({1: 5, 3: 1})
    assert result.method == "content"
    assert ids(result)[0] == 2
    assert {1, 3}.isdisjoint(ids(result))
    scores = {item.app_id: item.score for item in result.results}
    assert scores[2] > scores[7] > scores[4]
    assert "Space" in result.results[0].reason


def test_multiword_tags_remain_distinct(small_catalog):
    model = RecommendationEngine(small_catalog)
    assert ids(model.content({3: 5}, 1)) == [4]
    assert "Farming Sim" in model.content({3: 5}, 1).results[0].reason


@pytest.mark.parametrize("ratings", [{}, {1: 3}, {999: 5}])
def test_cold_start_is_explicit_and_finite(small_catalog, ratings):
    model = RecommendationEngine(small_catalog)
    for algorithm in (model.content, model.collaborative):
        result = algorithm(ratings)
        assert result.fallback
        assert result.method == "popularity"
        assert result.message
        assert len(ids(result)) == len(set(ids(result)))
        assert set(ratings).isdisjoint(ids(result))


def test_collaborative_uses_peer_ratings_and_excludes_seen(small_catalog):
    model = RecommendationEngine(small_catalog)
    result = model.collaborative({1: 5, 3: 1})
    assert not result.fallback
    assert result.neighbor_count == 2
    assert ids(result) == [2]
    assert result.results[0].score > 0
    assert "synthetic" in result.results[0].reason


def test_rating_change_changes_neighbor_group(small_catalog):
    model = RecommendationEngine(small_catalog)
    result = model.collaborative({1: 1, 3: 5})
    assert set(ids(result)) == {4, 5}


def test_all_rated_returns_empty_instead_of_seen_games(small_catalog):
    model = RecommendationEngine(small_catalog)
    ratings = {game.app_id: 5 for game in small_catalog.games}
    assert not model.content(ratings).results
    assert not model.collaborative(ratings).results


def test_query_search_is_labeled_lexical(small_catalog):
    result = RecommendationEngine(small_catalog).lexical_search("peaceful farm crops")
    assert result.method == "lexical"
    assert ids(result)[0] == 3
    assert "baseline" in result.message.lower()
    assert not RecommendationEngine(small_catalog).lexical_search("qzzxqzzx").results


def test_demo_produces_ranked_top_ten(demo_catalog):
    model = RecommendationEngine(demo_catalog)
    for result in (model.content({413150: 5, 1248130: 4}), model.collaborative({413150: 5})):
        assert 0 < len(result.results) <= 10
        assert {413150, 1248130}.isdisjoint(ids(result)) if result.method == "content" else True
        assert 413150 not in ids(result)
        assert len(ids(result)) == len(set(ids(result)))
        assert [item.score for item in result.results] == sorted(
            (item.score for item in result.results), reverse=True
        )
