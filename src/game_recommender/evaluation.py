"""Reproducible positive-item holdout evaluation without test-interaction leakage."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from dataclasses import replace

from game_recommender.catalog import Catalog
from game_recommender.engine import RecommendationEngine


def evaluate(catalog: Catalog, *, seed=42, k=10) -> dict:
    if not 1 <= k <= 10:
        raise ValueError("Evaluation k must be between 1 and 10.")
    by_user = defaultdict(list)
    for item in catalog.interactions:
        by_user[item.user_id].append(item)
    held_out = {}
    training = []
    for user_id, items in sorted(by_user.items()):
        positives = [item for item in items if item.rating >= 4]
        if len(items) >= 3 and len(positives) >= 2:
            target = min(
                positives,
                key=lambda item: hashlib.sha256(
                    f"{seed}:{user_id}:{item.app_id}".encode()
                ).digest(),
            )
            held_out[user_id] = target.app_id
            training.extend(item for item in items if item.app_id != target.app_id)
        else:
            training.extend(items)
    if not held_out:
        raise ValueError(
            "Evaluation needs users with at least 3 interactions and 2 positive items."
        )
    model = RecommendationEngine(replace(catalog, interactions=tuple(training)))
    profiles = defaultdict(dict)
    for item in training:
        profiles[item.user_id][item.app_id] = item.rating
    reports = {}
    for method in ("popularity", "content", "collaborative"):
        hits = ndcg = fallbacks = 0
        coverage = set()
        for user_id, target in held_out.items():
            if method == "collaborative":
                result = model.collaborative(profiles[user_id], k, exclude_user_id=user_id)
            else:
                result = getattr(model, "popular" if method == "popularity" else method)(
                    profiles[user_id], k
                )
            ids = [item.app_id for item in result.results]
            coverage.update(ids)
            fallbacks += int(result.fallback)
            if target in ids:
                hits += 1
                ndcg += 1 / math.log2(ids.index(target) + 2)
        reports[method] = {
            f"recall@{k}": round(hits / len(held_out), 6),
            f"ndcg@{k}": round(ndcg / len(held_out), 6),
            "catalog_coverage": round(len(coverage) / len(catalog.games), 6),
            "fallback_count": fallbacks,
        }
    return {
        "data_mode": catalog.mode,
        "synthetic_data": catalog.mode == "demo",
        "protocol": "one-positive-per-user deterministic random holdout",
        "seed": seed,
        "k": k,
        "evaluated_users": len(held_out),
        "ineligible_users": len(by_user) - len(held_out),
        "training_interactions": len(training),
        "test_interactions": len(held_out),
        "catalog_fingerprint": catalog.fingerprint,
        "models": reports,
        "note": (
            "Synthetic fixture metrics verify the evaluation pipeline, "
            "not real recommendation quality."
            if catalog.mode == "demo"
            else "Random holdout on the selected sample; "
            "not a temporal or population-wide estimate."
        ),
    }
