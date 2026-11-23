"""Persistent browser profiles; Steam training interactions never enter this database."""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path


class RatingStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connection() as db:
            db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS profiles (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS ratings (
                    profile_id TEXT NOT NULL REFERENCES profiles(id),
                    app_id INTEGER NOT NULL,
                    rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(profile_id, app_id)
                );
                """
            )

    @contextmanager
    def connection(self):
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute("PRAGMA foreign_keys=ON")
            yield db

    def resolve_profile(self, candidate: str | None) -> tuple[str, bool]:
        with self.connection() as db:
            if (
                candidate
                and db.execute("SELECT 1 FROM profiles WHERE id=?", (candidate,)).fetchone()
            ):
                return candidate, False
            profile_id = uuid.uuid4().hex
            db.execute("INSERT INTO profiles(id) VALUES (?)", (profile_id,))
            return profile_id, True

    def ratings(self, profile_id: str) -> dict[int, int]:
        with self.connection() as db:
            return dict(
                db.execute("SELECT app_id, rating FROM ratings WHERE profile_id=?", (profile_id,))
            )

    def set_rating(self, profile_id: str, app_id: int, rating: int) -> None:
        with self.connection() as db:
            db.execute(
                """INSERT INTO ratings(profile_id, app_id, rating) VALUES (?, ?, ?)
                ON CONFLICT(profile_id, app_id) DO UPDATE
                SET rating=excluded.rating, updated_at=CURRENT_TIMESTAMP""",
                (profile_id, app_id, rating),
            )

    def delete_rating(self, profile_id: str, app_id: int) -> None:
        with self.connection() as db:
            db.execute("DELETE FROM ratings WHERE profile_id=? AND app_id=?", (profile_id, app_id))
