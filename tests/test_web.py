import json
import re

from fastapi.testclient import TestClient

from game_recommender.api import create_app
from game_recommender.evaluation import evaluate


def test_player_interface_and_assets_are_served(tmp_path, demo_dir):
    app = create_app(demo_dir, tmp_path / "ratings.sqlite3", tmp_path / "artifacts")
    with TestClient(app) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "Nextplay" in home.text
        assert 'href="#evaluation"' in home.text
        assert "/static/app.js" in home.text
        for asset in ("app.js", "styles.css", "favicon.svg"):
            response = client.get(f"/static/{asset}")
            assert response.status_code == 200
            assert len(response.content) > 0


def test_evaluation_serves_only_reports_for_current_sample(tmp_path, demo_dir, demo_catalog):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    path = artifacts / "evaluation.json"
    app = create_app(demo_dir, tmp_path / "ratings.sqlite3", artifacts)
    with TestClient(app) as client:
        assert client.get("/api/evaluation").status_code == 404

        report = evaluate(demo_catalog)
        path.write_text(json.dumps(report), encoding="utf-8")
        assert client.get("/api/evaluation").json() == report

        report["training_interactions"] -= 1
        path.write_text(json.dumps(report), encoding="utf-8")
        assert client.get("/api/evaluation").status_code == 409

        path.write_text("{", encoding="utf-8")
        assert client.get("/api/evaluation").status_code == 503


def test_home_loads_versioned_assets_for_the_latest_navigation(tmp_path, demo_dir):
    app = create_app(demo_dir, tmp_path / "ratings.sqlite3", tmp_path / "artifacts")
    with TestClient(app) as client:
        home = client.get("/")
        assert 'href="#evaluation"' in home.text
        script = re.search(r'src="(/static/app\.js\?v=[a-f0-9]+)"', home.text)
        assert script, "The browser could reuse the cached script from before Evaluation was added."
        assert home.headers["cache-control"] == "no-store"
        assert '"/api/evaluation"' in client.get(script.group(1)).text

