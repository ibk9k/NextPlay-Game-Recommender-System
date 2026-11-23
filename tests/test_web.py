from fastapi.testclient import TestClient

from game_recommender.api import create_app


def test_player_interface_and_assets_are_served(tmp_path, demo_dir):
    app = create_app(demo_dir, tmp_path / "ratings.sqlite3", tmp_path / "artifacts")
    with TestClient(app) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "Nextplay" in home.text
        assert "/static/app.js" in home.text
        for asset in ("app.js", "styles.css", "favicon.svg"):
            response = client.get(f"/static/{asset}")
            assert response.status_code == 200
            assert len(response.content) > 0

