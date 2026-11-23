"""Regenerate SYNTHETIC test interactions, never real Steam review data."""

import csv
import json
import random
from pathlib import Path

directory = Path(__file__).resolve().parents[1] / "src" / "game_recommender" / "demo"
games = json.loads((directory / "catalog.json").read_text(encoding="utf-8"))
ids = [g["app_id"] for g in games]
groups = [
    [400, 620, 424840, 238460, 367520, 204360],
    [413150, 1248130, 227300, 255710, 105600, 294100],
    [892970, 105600, 322330, 108600, 252490, 346110, 427520],
    [646570, 1145360, 588650, 250900, 311690, 367520],
    [292030, 1091500, 1245620, 1086940, 435150, 1593500, 1151640],
    [427520, 294100, 255710, 281990, 1158310, 646570],
    [570, 730, 440, 252490, 311690, 204360],
    [281990, 359320, 1091500, 400, 620, 1151640],
]
rng = random.Random(42)
rows = []
for group_id, liked in enumerate(groups):
    for member in range(4):
        user_id = f"synthetic-{group_id + 1:02}-{member + 1:02}"
        profile = {app_id: rng.choice([4, 5, 5]) for app_id in liked}
        others = [app_id for app_id in ids if app_id not in profile]
        for app_id in rng.sample(others, 3):
            profile[app_id] = rng.choice([1, 2])
        for app_id, rating in sorted(profile.items()):
            rows.append([user_id, app_id, rating, "demo_synthetic"])
with (directory / "interactions.csv").open("w", encoding="utf-8", newline="") as stream:
    writer = csv.writer(stream)
    writer.writerow(["user_id", "app_id", "rating", "source"])
    writer.writerows(rows)
manifest = {
    "schema_version": 1,
    "mode": "demo",
    "game_count": len(games),
    "peer_count": len(groups) * 4,
    "interaction_count": len(rows),
    "seed": 42,
    "note": "Manually written game metadata and SYNTHETIC peer ratings, not Kaggle training data.",
}
(directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(f"Generated {len(rows)} synthetic interactions for {len(groups) * 4} demo profiles.")
