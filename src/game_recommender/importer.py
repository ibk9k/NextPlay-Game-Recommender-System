"""Bounded-memory, deterministic preparation of the proposal's Kaggle dataset."""

from __future__ import annotations

import csv
import hashlib
import heapq
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import ijson


def csv_rows(path: Path, required: set[str]):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path.name} is missing columns: {', '.join(sorted(missing))}")
        yield from reader


def sample_active_users(path: Path, count: int, min_reviews: int, seed: int) -> set[str]:
    # Select the smallest seeded hashes, retaining at most `count` candidates.
    heap = []
    selected = set()
    for row in csv_rows(path, {"user_id", "reviews"}):
        user_id = row["user_id"].strip()
        if not user_id or int(row["reviews"]) < min_reviews or user_id in selected:
            continue
        priority = int.from_bytes(hashlib.sha256(f"{seed}:{user_id}".encode()).digest(), "big")
        entry = (-priority, user_id)
        if len(heap) < count:
            heapq.heappush(heap, entry)
            selected.add(user_id)
        elif entry > heap[0]:
            _, removed = heapq.heapreplace(heap, entry)
            selected.remove(removed)
            selected.add(user_id)
    return selected


def metadata_rows(path: Path):
    with path.open("rb") as stream:
        first = b""
        while not first.strip():
            first = stream.read(1)
            if not first:
                raise ValueError("Game metadata is empty.")
        stream.seek(0)
        if first == b"[":
            yield from ijson.items(stream, "item")
        else:
            for line in stream:
                if line.strip():
                    yield json.loads(line)


def prepare_dataset(
    raw_dir: Path,
    output_dir: Path,
    *,
    users=2000,
    min_reviews=5,
    seed=42,
    max_interactions=2_000_000,
) -> dict:
    if users < 1 or min_reviews < 2 or max_interactions < 1:
        raise ValueError("users >= 1, min-reviews >= 2, and max-interactions >= 1 are required.")
    if raw_dir.resolve() == output_dir.resolve():
        raise ValueError("Raw input and processed output must be different directories.")
    required = ["games.csv", "users.csv", "recommendations.csv", "games_metadata.json"]
    missing = [name for name in required if not (raw_dir / name).is_file()]
    if missing:
        raise ValueError(f"Missing Kaggle files: {', '.join(missing)}")
    if (output_dir / "manifest.json").exists():
        raise ValueError("Output already contains a catalogue. Choose a new output directory.")

    games = {}
    for row in csv_rows(raw_dir / "games.csv", {"app_id", "title"}):
        app_id = int(row["app_id"])
        if app_id <= 0 or not row["title"].strip() or app_id in games:
            raise ValueError(f"Invalid or duplicate games.csv app_id: {app_id}")
        games[app_id] = {"app_id": app_id, "title": row["title"].strip()}
    metadata_seen = set()
    for row in metadata_rows(raw_dir / "games_metadata.json"):
        app_id = int(row["app_id"])
        if app_id not in games:
            continue
        if app_id in metadata_seen:
            raise ValueError(f"Duplicate metadata for app_id {app_id}")
        metadata_seen.add(app_id)
        tags = row.get("tags", [])
        description = row.get("description") or ""
        if not isinstance(tags, list) or not isinstance(description, str):
            raise ValueError(f"Invalid metadata for app_id {app_id}")
        if any(not isinstance(t, str) for t in tags):
            raise ValueError(f"Invalid tags for app_id {app_id}")
        tags = list(dict.fromkeys(t.strip() for t in tags if t.strip()))
        if tags and description.strip():
            games[app_id].update(tags=tags, description=description.strip())
    games = {app_id: g for app_id, g in games.items() if "tags" in g}
    if not games:
        raise ValueError("No games have both tags and descriptions after the metadata join.")

    active_users = sample_active_users(raw_dir / "users.csv", users, min_reviews, seed)
    if not active_users:
        raise ValueError("No active users satisfy the requested minimum review count.")
    interactions = {}
    scanned = 0
    ignored_metadata = 0
    for row in csv_rows(raw_dir / "recommendations.csv", {"user_id", "app_id", "is_recommended"}):
        scanned += 1
        if scanned % 1_000_000 == 0:
            print(f"Scanned {scanned:,} reviews; retained {len(interactions):,} pairs.", flush=True)
        user_id = row["user_id"].strip()
        if user_id not in active_users:
            continue
        app_id = int(row["app_id"])
        if app_id not in games:
            ignored_metadata += 1
            continue
        signal = row["is_recommended"].strip().lower()
        if signal not in {"true", "false", "1", "0"}:
            raise ValueError(f"Invalid is_recommended signal at review row {scanned}: {signal!r}")
        rating = 5 if signal in {"true", "1"} else 1
        key = (user_id, app_id)
        timestamp = row.get("date", "")
        if key not in interactions or timestamp >= interactions[key][0]:
            interactions[key] = (timestamp, rating)
        if len(interactions) > max_interactions:
            raise ValueError(
                "Interaction limit exceeded. Reduce --users or raise --max-interactions."
            )

    observed_counts = Counter(user_id for user_id, _ in interactions)
    retained_users = {u for u, n in observed_counts.items() if n >= min_reviews}
    interactions = {key: value for key, value in interactions.items() if key[0] in retained_users}
    if not interactions:
        raise ValueError("No sampled users retain enough reviews after the metadata join.")
    manifest = {
        "schema_version": 1,
        "mode": "kaggle",
        "dataset": "antonkozyriev/game-recommendations-on-steam",
        "prepared_at": datetime.now(UTC).isoformat(),
        "sampling": {"method": "seeded-smallest-hash", "seed": seed, "requested_users": users},
        "min_reviews": min_reviews,
        "selected_users": len(active_users),
        "retained_users": len(retained_users),
        "scanned_reviews": scanned,
        "ignored_reviews_missing_metadata": ignored_metadata,
        "game_count": len(games),
        "interaction_count": len(interactions),
        "binary_mapping": {"recommended": 5, "not_recommended": 1},
        "raw_file_sizes": {name: (raw_dir / name).stat().st_size for name in required},
        "note": "Source reviews are binary; these are model inputs, not observed star ratings.",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    ordered_games = [games[app_id] for app_id in sorted(games)]
    (output_dir / "catalog.json").write_text(
        json.dumps(ordered_games, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    with (output_dir / "interactions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["user_id", "app_id", "rating", "source"])
        for (user_id, app_id), (_, rating) in sorted(interactions.items()):
            writer.writerow([user_id, app_id, rating, "steam_binary"])
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
