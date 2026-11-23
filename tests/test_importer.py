import csv
import json

import pytest

from game_recommender.catalog import load_catalog
from game_recommender.importer import prepare_dataset, sample_active_users


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)


def raw_fixture(tmp_path, metadata_format="array"):
    raw = tmp_path / "raw"
    raw.mkdir()
    write_csv(raw / "games.csv", ["app_id", "title"], [[1, "Orbit"], [2, "Farm"], [3, "No tags"]])
    write_csv(
        raw / "users.csv",
        ["user_id", "reviews"],
        [["76561198000000001", 8], ["76561198000000002", 6], ["inactive", 1]],
    )
    write_csv(
        raw / "recommendations.csv",
        ["user_id", "app_id", "is_recommended", "date"],
        [
            ["76561198000000001", 1, "True", "2023-01-02"],
            ["76561198000000001", 1, "False", "2023-01-01"],
            ["76561198000000001", 2, "False", "2023-01-02"],
            ["76561198000000002", 1, "1", "2023-01-02"],
            ["76561198000000002", 2, "0", "2023-01-02"],
            ["inactive", 1, "True", "2023-01-02"],
            ["76561198000000001", 3, "True", "2023-01-02"],
        ],
    )
    records = [
        {"app_id": 1, "description": "Explore space.", "tags": ["Space", "Space"]},
        {"app_id": 2, "description": "Grow crops.", "tags": ["Farming Sim"]},
        {"app_id": 3, "description": "Unusable metadata.", "tags": []},
    ]
    text = (
        json.dumps(records) if metadata_format == "array" else "\n".join(map(json.dumps, records))
    )
    (raw / "games_metadata.json").write_text(text, encoding="utf-8")
    return raw


@pytest.mark.parametrize("metadata_format", ["array", "jsonl"])
def test_streaming_join_preserves_binary_provenance_and_deduplicates(tmp_path, metadata_format):
    raw = raw_fixture(tmp_path, metadata_format)
    output = tmp_path / "processed"
    manifest = prepare_dataset(raw, output, users=2, min_reviews=2)
    catalog = load_catalog(output)
    assert catalog.mode == "kaggle"
    assert len(catalog.games) == 2
    assert len(catalog.interactions) == 4
    assert manifest["retained_users"] == 2
    assert manifest["scanned_reviews"] == 7
    assert manifest["ignored_reviews_missing_metadata"] == 1
    assert {item.source for item in catalog.interactions} == {"steam_binary"}
    assert {item.rating for item in catalog.interactions} == {1, 5}
    assert catalog.games[0].tags == ("Space",)
    latest = [r for r in catalog.interactions if r.user_id == "76561198000000001" and r.app_id == 1]
    assert latest[0].rating == 5


def test_sampling_is_deterministic_and_independent_of_file_order(tmp_path):
    path = tmp_path / "users.csv"
    rows = [[f"user-{i}", 10] for i in range(100)]
    write_csv(path, ["user_id", "reviews"], rows)
    first = sample_active_users(path, 7, 5, 42)
    write_csv(path, ["user_id", "reviews"], list(reversed(rows)))
    assert first == sample_active_users(path, 7, 5, 42)
    assert len(first) == 7
    assert first != sample_active_users(path, 7, 5, 43)


def test_import_does_not_silently_truncate_or_overwrite(tmp_path):
    raw = raw_fixture(tmp_path)
    output = tmp_path / "processed"
    with pytest.raises(ValueError, match="limit exceeded"):
        prepare_dataset(raw, output, users=2, min_reviews=2, max_interactions=1)
    assert not (output / "manifest.json").exists()
    prepare_dataset(raw, output, users=2, min_reviews=2)
    with pytest.raises(ValueError, match="already contains"):
        prepare_dataset(raw, output, users=2, min_reviews=2)


def test_required_columns_and_signals_are_validated(tmp_path):
    raw = raw_fixture(tmp_path)
    output = tmp_path / "processed"
    write_csv(raw / "recommendations.csv", ["user_id", "app_id"], [["76561198000000001", 1]])
    with pytest.raises(ValueError, match="missing columns"):
        prepare_dataset(raw, output, users=2, min_reviews=2)
    write_csv(
        raw / "recommendations.csv",
        ["user_id", "app_id", "is_recommended"],
        [["76561198000000001", 1, "maybe"]],
    )
    with pytest.raises(ValueError, match="Invalid is_recommended"):
        prepare_dataset(raw, output, users=2, min_reviews=2)


def test_minimum_observed_reviews_checked_after_join(tmp_path):
    raw = raw_fixture(tmp_path)
    with pytest.raises(ValueError, match="enough reviews"):
        prepare_dataset(raw, tmp_path / "processed", users=2, min_reviews=3)
