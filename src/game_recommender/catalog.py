"""Validated, versioned catalogue input shared by the web app and offline tools."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Game:
    app_id: int
    title: str
    description: str
    tags: tuple[str, ...]

    @property
    def search_text(self) -> str:
        return f"{self.title}. {self.description} Tags: {', '.join(self.tags)}"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Interaction:
    user_id: str
    app_id: int
    rating: int
    source: str


@dataclass(frozen=True)
class Catalog:
    games: tuple[Game, ...]
    interactions: tuple[Interaction, ...]
    mode: str
    manifest: dict

    @property
    def fingerprint(self) -> str:
        # Content changes matter just as much as item IDs for a neural index.
        payload = json.dumps([g.to_dict() for g in self.games], sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_catalog(directory: Path) -> Catalog:
    with (directory / "manifest.json").open(encoding="utf-8") as stream:
        manifest = json.load(stream)
    if manifest.get("schema_version") != 1 or manifest.get("mode") not in {"demo", "kaggle"}:
        raise ValueError("Unsupported catalogue manifest; run the import command again.")
    with (directory / "catalog.json").open(encoding="utf-8") as stream:
        records = json.load(stream)
    games = []
    ids = set()
    for record in records:
        app_id = record["app_id"]
        tags = record["tags"]
        if (
            type(app_id) is not int
            or app_id <= 0
            or app_id in ids
            or not isinstance(record["title"], str)
            or not record["title"].strip()
            or not isinstance(record["description"], str)
            or not isinstance(tags, list)
            or not tags
            or any(not isinstance(t, str) or not t.strip() for t in tags)
        ):
            raise ValueError(f"Invalid or duplicate game record: {app_id!r}")
        ids.add(app_id)
        games.append(
            Game(app_id, record["title"].strip(), record["description"], tuple(dict.fromkeys(tags)))
        )
    if not games:
        raise ValueError("The catalogue is empty.")
    interactions = []
    pairs = set()
    with (directory / "interactions.csv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            item = Interaction(
                row["user_id"], int(row["app_id"]), int(row["rating"]), row["source"]
            )
            pair = (item.user_id, item.app_id)
            if (
                not item.user_id
                or item.app_id not in ids
                or not 1 <= item.rating <= 5
                or pair in pairs
                or item.source not in {"demo_synthetic", "steam_binary"}
            ):
                raise ValueError(f"Invalid or duplicate interaction: {pair!r}")
            if manifest["mode"] == "demo" and item.source != "demo_synthetic":
                raise ValueError("Demo interactions must identify their synthetic provenance.")
            pairs.add(pair)
            interactions.append(item)
    return Catalog(tuple(games), tuple(interactions), manifest["mode"], manifest)
