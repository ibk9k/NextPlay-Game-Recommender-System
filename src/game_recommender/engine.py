"""Independent, explainable recommendation algorithms over sparse matrices."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from game_recommender.catalog import Catalog


def whole_tags(tags):
    return tags


@dataclass(frozen=True)
class RankedGame:
    app_id: int
    score: float
    reason: str


@dataclass(frozen=True)
class Recommendation:
    results: tuple[RankedGame, ...]
    method: str
    fallback: bool = False
    message: str = ""
    neighbor_count: int = 0


class RecommendationEngine:
    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self.games = catalog.games
        self.positions = {g.app_id: i for i, g in enumerate(self.games)}
        self.tag_vectorizer = TfidfVectorizer(analyzer=whole_tags, dtype=np.float32)
        self.tags = self.tag_vectorizer.fit_transform([g.tags for g in self.games]).tocsr()
        self.words = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), dtype=np.float32)
        self.descriptions = self.words.fit_transform([g.search_text for g in self.games])

        user_ids = sorted({r.user_id for r in catalog.interactions})
        self.user_positions = {user_id: i for i, user_id in enumerate(user_ids)}
        rows, columns, values = [], [], []
        for item in catalog.interactions:
            rows.append(self.user_positions[item.user_id])
            columns.append(self.positions[item.app_id])
            values.append(float(item.rating - 3))
        shape = (len(user_ids), len(self.games))
        self.preferences = csr_matrix((values, (rows, columns)), shape=shape, dtype=np.float32)
        self.observed = csr_matrix(
            (np.ones(len(values), dtype=np.float32), (rows, columns)), shape=shape
        )
        self.normalized_users = normalize(self.preferences, axis=1)
        positives = self.preferences.copy()
        positives.data = (positives.data > 0).astype(np.float32)
        self.popularity = np.asarray(positives.sum(axis=0)).ravel()

    def valid_ratings(self, ratings: dict[int, int]) -> dict[int, int]:
        return {app_id: rating for app_id, rating in ratings.items() if app_id in self.positions}

    def _rank(self, scores, excluded, limit, reason, minimum=None) -> tuple[RankedGame, ...]:
        eligible = [
            i
            for i, game in enumerate(self.games)
            if game.app_id not in excluded
            and np.isfinite(scores[i])
            and (minimum is None or scores[i] > minimum)
        ]
        eligible.sort(key=lambda i: (-float(scores[i]), self.games[i].app_id))
        return tuple(
            RankedGame(self.games[i].app_id, round(float(scores[i]), 6), reason(i))
            for i in eligible[:limit]
        )

    def popular(self, ratings: dict[int, int], limit=10, message="") -> Recommendation:
        def explanation(i):
            count = int(self.popularity[i])
            if self.catalog.mode == "demo":
                return f"Liked by {count} synthetic demo profiles."
            return f"Recommended by {count} users in the imported sample."

        return Recommendation(
            self._rank(self.popularity, ratings, limit, explanation),
            "popularity",
            fallback=True,
            message=message or "Rate games to personalize this list.",
        )

    def content(self, ratings: dict[int, int], limit=10) -> Recommendation:
        ratings = self.valid_ratings(ratings)
        weights = np.zeros(len(self.games), dtype=np.float32)
        for app_id, rating in ratings.items():
            weights[self.positions[app_id]] = rating - 3
        profile = csr_matrix(weights.reshape(1, -1)) @ self.tags
        if not ratings or not profile.nnz or np.linalg.norm(profile.data) < 1e-8:
            return self.popular(
                ratings, limit, "Rate a game above or below 3 stars to build a profile."
            )
        scores = (normalize(profile) @ self.tags.T).toarray().ravel()
        tag_weights = dict(
            zip(self.tag_vectorizer.get_feature_names_out(), profile.toarray()[0], strict=True)
        )

        def explanation(i):
            overlap = sorted(
                (t for t in self.games[i].tags if tag_weights.get(t, 0) > 0),
                key=lambda t: -tag_weights[t],
            )[:3]
            if overlap:
                return f"Matches your taste in {', '.join(overlap)}."
            return "Ranks above games sharing the tags you disliked."

        return Recommendation(self._rank(scores, ratings, limit, explanation), "content")

    def collaborative(
        self, ratings: dict[int, int], limit=10, neighbors=30, exclude_user_id=None
    ) -> Recommendation:
        ratings = self.valid_ratings(ratings)
        indices = [self.positions[app_id] for app_id in ratings]
        values = [ratings[app_id] - 3 for app_id in ratings]
        query = csr_matrix((values, ([0] * len(indices), indices)), shape=(1, len(self.games)))
        if not indices or np.linalg.norm(query.data) < 1e-8 or not self.user_positions:
            return self.popular(
                ratings, limit, "Rate games to find players with similar preferences."
            )
        similarities = (self.normalized_users @ normalize(query).T).toarray().ravel()
        if exclude_user_id in self.user_positions:
            similarities[self.user_positions[exclude_user_id]] = 0
        overlaps = np.asarray(self.observed[:, indices].sum(axis=1)).ravel()
        # Significance weighting: one common game carries less evidence than five.
        similarities *= np.minimum(overlaps / 5.0, 1.0)
        selected = np.flatnonzero(similarities > 1e-8)
        selected = sorted(selected, key=lambda i: (-float(similarities[i]), int(i)))[:neighbors]
        if not selected:
            return self.popular(ratings, limit, "No similar players yet; showing sample favorites.")
        weights = similarities[selected]
        peer_preferences = self.preferences[selected]
        peer_observed = self.observed[selected]
        numerators = np.asarray(peer_preferences.T @ weights).ravel()
        denominators = np.asarray(peer_observed.T @ weights).ravel()
        scores = np.divide(
            numerators, denominators, out=np.zeros(len(self.games)), where=denominators > 0
        )
        supporters = peer_preferences.copy()
        supporters.data = (supporters.data > 0).astype(np.float32)
        supporters = np.asarray(supporters.sum(axis=0)).ravel()

        def explanation(i):
            noun = "synthetic demo profiles" if self.catalog.mode == "demo" else "similar players"
            return f"Liked by {int(supporters[i])} {noun}."

        results = self._rank(scores, ratings, limit, explanation, minimum=0)
        if not results:
            return self.popular(ratings, limit, "Similar players have no new positive matches yet.")
        return Recommendation(results, "collaborative", neighbor_count=len(selected))

    def lexical_search(self, query: str, limit=10) -> Recommendation:
        vector = self.words.transform([query])
        if not vector.nnz:
            return Recommendation(
                (), "lexical", message="No matching words. Try a game style, setting, or mechanic."
            )
        scores = (self.descriptions @ vector.T).toarray().ravel()
        return Recommendation(
            self._rank(
                scores, {}, limit, lambda i: "Matches words in the description or tags.", minimum=0
            ),
            "lexical",
            message="Keyword baseline. Build the neural index to enable semantic search.",
        )

    @property
    def tag_counts(self) -> list[dict]:
        counts = Counter(t for game in self.games for t in game.tags)
        return [{"tag": t, "count": c} for t, c in sorted(counts.items())]
