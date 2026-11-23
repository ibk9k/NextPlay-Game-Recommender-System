from pathlib import Path

import pytest

from game_recommender.catalog import Catalog, Game, Interaction, load_catalog


@pytest.fixture
def small_catalog():
    games = (
        Game(1, "Space Battle", "Fight in space.", ("Space", "Action")),
        Game(2, "Quiet Orbit", "Explore space and distant planets.", ("Space", "Exploration")),
        Game(3, "Peaceful Farm", "Grow crops on a peaceful farm.", ("Farming Sim", "Relaxing")),
        Game(4, "River Farm", "Grow crops and fish.", ("Farming Sim", "Relaxing")),
        Game(5, "Hard Harvest", "Grow crops through challenging seasons.", ("Farming Sim", "Hard")),
        Game(6, "Haunted Battle", "Fight ghosts and monsters.", ("Horror", "Action")),
        Game(7, "Logic Rooms", "Solve puzzles in a laboratory.", ("Puzzle", "Logic")),
    )
    peers = {
        "space-1": {1: 5, 2: 5, 3: 1},
        "space-2": {1: 5, 2: 4, 5: 1},
        "farm-1": {3: 5, 4: 5, 1: 1},
        "farm-2": {3: 5, 5: 5, 1: 1},
        "puzzle-1": {7: 5, 6: 4, 2: 1},
    }
    interactions = tuple(
        Interaction(user_id, app_id, rating, "demo_synthetic")
        for user_id, ratings in peers.items()
        for app_id, rating in ratings.items()
    )
    return Catalog(games, interactions, "demo", {"schema_version": 1, "mode": "demo"})


@pytest.fixture
def demo_dir():
    return Path(__file__).resolve().parents[1] / "src" / "game_recommender" / "demo"


@pytest.fixture
def demo_catalog(demo_dir):
    return load_catalog(demo_dir)
