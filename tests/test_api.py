from fastapi.testclient import TestClient

from game_recommender.api import create_app


def test_ratings_persist_are_isolated_and_change_recommendations(tmp_path, demo_dir):
    app = create_app(demo_dir, tmp_path / "ratings.sqlite3", tmp_path / "artifacts")
    with TestClient(app) as player:
        assert player.get("/api/profile").json()["ratings"] == {}
        cookie = player.cookies.get("game_rs_profile")
        assert player.put("/api/ratings/413150", json={"rating": 5}).status_code == 200
        assert player.get("/api/profile").json()["ratings"] == {"413150": 5}
        result = player.get("/api/recommendations?method=content").json()
        assert result["method"] == "content"
        assert 413150 not in [item["app_id"] for item in result["items"]]
        with TestClient(app) as second_player:
            assert second_player.get("/api/profile").json()["ratings"] == {}
    restarted = create_app(demo_dir, tmp_path / "ratings.sqlite3", tmp_path / "artifacts")
    with TestClient(restarted) as player:
        player.cookies.set("game_rs_profile", cookie)
        assert player.get("/api/profile").json()["ratings"] == {"413150": 5}
        assert player.delete("/api/ratings/413150").status_code == 200
        assert player.get("/api/profile").json()["ratings"] == {}


def test_validation_and_missing_game(tmp_path, demo_dir):
    app = create_app(demo_dir, tmp_path / "ratings.sqlite3", tmp_path / "artifacts")
    with TestClient(app) as client:
        for rating in (0, 6, 2.5, "5", True):
            assert client.put("/api/ratings/413150", json={"rating": rating}).status_code == 422
        assert client.put("/api/ratings/9999999", json={"rating": 4}).status_code == 404
        assert client.get("/api/recommendations?method=hybrid").status_code == 422
        assert client.get("/api/recommendations?limit=11").status_code == 422
        assert client.post("/api/search", json={"query": "   "}).status_code == 422
        assert client.post("/api/search", json={"query": "space", "limit": 11}).status_code == 422


def test_search_never_claims_missing_neural_engine(tmp_path, demo_dir):
    app = create_app(demo_dir, tmp_path / "ratings.sqlite3", tmp_path / "artifacts")
    with TestClient(app) as client:
        status = client.get("/api/status").json()
        assert status["data_mode"] == "demo"
        assert not status["neural_index_ready"]
        result = client.post("/api/search", json={"query": "farming crops"}).json()
        assert result["method"] == "lexical"
        assert not result["fallback"]
        unavailable = client.post("/api/search", json={"query": "farming", "engine": "neural"})
        assert unavailable.status_code == 503
        assert "build-neural" in unavailable.json()["detail"]


def test_catalog_search_filter_and_pagination(tmp_path, demo_dir):
    app = create_app(demo_dir, tmp_path / "ratings.sqlite3", tmp_path / "artifacts")
    with TestClient(app) as client:
        result = client.get("/api/games?q=portal").json()
        assert result["total"] == 2
        filtered = client.get("/api/games?tag=Farming%20Sim").json()
        assert filtered["total"] == 2
        first = client.get("/api/games?limit=5&offset=0").json()
        second = client.get("/api/games?limit=5&offset=5").json()
        assert {g["app_id"] for g in first["items"]}.isdisjoint(
            g["app_id"] for g in second["items"]
        )
        assert first["total"] == second["total"] == 36
        assert client.get("/api/games?limit=101").status_code == 422
