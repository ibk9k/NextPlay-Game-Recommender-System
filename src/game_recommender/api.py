"""Same-origin HTTP interface for the local academic application."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from game_recommender.catalog import load_catalog
from game_recommender.engine import Recommendation, RecommendationEngine
from game_recommender.neural import NeuralSearch, NeuralUnavailable
from game_recommender.storage import RatingStore

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parents[1]


def default_catalog_dir() -> Path:
    configured = os.environ.get("GAME_RS_DATA_DIR")
    if configured:
        return Path(configured)
    processed = PROJECT_DIR / "data" / "processed"
    return processed if (processed / "manifest.json").exists() else PACKAGE_DIR / "demo"


class RatingInput(BaseModel):
    rating: Annotated[int, Field(strict=True, ge=1, le=5)]


class SearchInput(BaseModel):
    query: Annotated[str, Field(min_length=2, max_length=500)]
    engine: Literal["auto", "lexical", "neural"] = "auto"
    limit: Annotated[int, Field(strict=True, ge=1, le=10)] = 10


def resolve_profile(request: Request, response: Response) -> str:
    profile_id, created = request.app.state.store.resolve_profile(
        request.cookies.get("game_rs_profile")
    )
    if created:
        response.set_cookie(
            "game_rs_profile", profile_id, httponly=True, samesite="strict", max_age=31536000
        )
    response.headers["Cache-Control"] = "no-store"
    return profile_id


Profile = Annotated[str, Depends(resolve_profile)]


def create_app(
    data_dir: Path | None = None, db_path: Path | None = None, artifact_dir: Path | None = None
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        catalog = load_catalog(data_dir or default_catalog_dir())
        app.state.engine = RecommendationEngine(catalog)
        app.state.store = RatingStore(
            db_path
            or Path(os.environ.get("GAME_RS_DB_PATH", PROJECT_DIR / "data" / "ratings.sqlite3"))
        )
        app.state.neural = NeuralSearch(
            catalog,
            artifact_dir or Path(os.environ.get("GAME_RS_ARTIFACT_DIR", PROJECT_DIR / "artifacts")),
        )
        yield

    app = FastAPI(title="Game Recommender System", version="0.1.0", lifespan=lifespan)

    def engine() -> RecommendationEngine:
        return app.state.engine

    def profile_ratings(profile_id: str):
        return engine().valid_ratings(app.state.store.ratings(profile_id))

    def serialize(result: Recommendation) -> dict:
        model = engine()
        return {
            "items": [
                {
                    **model.games[model.positions[item.app_id]].to_dict(),
                    "score": item.score,
                    "reason": item.reason,
                    "rank": i + 1,
                }
                for i, item in enumerate(result.results)
            ],
            "method": result.method,
            "fallback": result.fallback,
            "message": result.message,
            "neighbor_count": result.neighbor_count,
            "data_mode": model.catalog.mode,
        }

    @app.get("/api/status")
    def status():
        model = engine()
        return {
            "data_mode": model.catalog.mode,
            "game_count": len(model.games),
            "peer_count": len(model.user_positions),
            "interaction_count": len(model.catalog.interactions),
            "catalog_fingerprint": model.catalog.fingerprint,
            "neural_index_ready": app.state.neural.ready,
            "neural_message": app.state.neural.unavailable_reason,
            "source_note": (
                "Demo catalogue with synthetic peer ratings; not the Kaggle dataset."
                if model.catalog.mode == "demo"
                else "Imported Kaggle subsample. Binary reviews map to 1 or 5 for modeling."
            ),
        }

    @app.get("/api/tags")
    def tags():
        return engine().tag_counts

    @app.get("/api/games")
    def games(
        q: Annotated[str, Query(max_length=120)] = "",
        tag: Annotated[str, Query(max_length=80)] = "",
        limit: Annotated[int, Query(ge=1, le=100)] = 24,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        needle = q.strip().casefold()
        items = [
            game
            for game in engine().games
            if (not needle or needle in game.title.casefold()) and (not tag or tag in game.tags)
        ]
        items.sort(key=lambda g: (g.title.casefold(), g.app_id))
        return {
            "items": [game.to_dict() for game in items[offset : offset + limit]],
            "total": len(items),
            "offset": offset,
            "limit": limit,
        }

    @app.get("/api/profile")
    def get_profile(profile_id: Profile):
        ratings = profile_ratings(profile_id)
        return {
            "ratings": {str(app_id): rating for app_id, rating in ratings.items()},
            "items": [
                {**engine().games[engine().positions[app_id]].to_dict(), "rating": rating}
                for app_id, rating in ratings.items()
            ],
        }

    @app.put("/api/ratings/{app_id}")
    def rate(app_id: int, body: RatingInput, profile_id: Profile):
        if app_id not in engine().positions:
            raise HTTPException(404, "Game not found in the current catalogue.")
        app.state.store.set_rating(profile_id, app_id, body.rating)
        return {"app_id": app_id, "rating": body.rating}

    @app.delete("/api/ratings/{app_id}")
    def delete_rating(app_id: int, profile_id: Profile):
        app.state.store.delete_rating(profile_id, app_id)
        return {"app_id": app_id, "removed": True}

    @app.get("/api/recommendations")
    def recommendations(
        profile_id: Profile,
        method: Literal["content", "collaborative"] = "content",
        limit: Annotated[int, Query(ge=1, le=10)] = 10,
    ):
        ratings = profile_ratings(profile_id)
        return serialize(getattr(engine(), method)(ratings, limit))

    @app.post("/api/search")
    def search(body: SearchInput):
        query = body.query.strip()
        if len(query) < 2:
            raise HTTPException(422, "Enter at least two non-space characters.")
        neural = app.state.neural
        if body.engine == "neural" or (body.engine == "auto" and neural.ready):
            try:
                return serialize(neural.search(query, body.limit))
            except NeuralUnavailable as exc:
                raise HTTPException(503, str(exc)) from exc
        return serialize(engine().lexical_search(query, body.limit))

    web_dir = PACKAGE_DIR / "web"
    if web_dir.is_dir():
        app.mount("/static", StaticFiles(directory=web_dir), name="static")

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(web_dir / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        def api_home():
            return RedirectResponse("/docs")

    return app


app = create_app()
