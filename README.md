# NextPlay - Game Recommender System

A local Python implementation of the supplied Steam game recommender proposal.
Read [the proposal interpretation and implementation decisions](docs/PROJECT_UNDERSTANDING.md)
before changing model behavior.

This first stage is a runnable local application with a dark, compact game library,
three independent recommendation/search approaches, saved ratings, and offline data
tools. The user confirmed Python/FastAPI, SQLite, a lightweight browser interface,
and a pretrained neural encoder. The API explorer at `/docs` remains available.

## What works

- A responsive player interface with title search, tag filters, pagination, 1-5 star
  ratings, saved games, recommendation reasons, and description search. Steam-hosted
  cover images have local title fallbacks when images cannot load.
- Tag-based TF-IDF profiles with cosine ranking, likes/dislikes, unseen-game exclusion,
  and an explicit popularity fallback.
- User-based collaborative recommendations from a sparse review matrix, positive
  cosine neighbors, and shared-item significance weighting.
- Persistent, isolated browser profiles with real 1-5 star ratings in SQLite.
- Description search using a clearly labeled lexical baseline, plus an optional
  pretrained sentence-transformer encoder and validated neural embedding index.
- Streaming Kaggle preparation with reproducible active-user sampling, metadata joins,
  latest-review deduplication, bounded retained interactions, and data provenance.
- A reproducible positive-item holdout evaluation of content, collaborative, and
  popularity models, reporting Recall@10, NDCG@10, and catalogue coverage.

The bundled demo has **36 games, 32 synthetic peer profiles, and 296 synthetic
interactions**. Descriptions and tags are manually written fixtures. These are not
the Kaggle dataset, observed Steam star ratings, or evidence of model quality.

## Start locally on Windows

Requires Python 3.11 or newer. Run from this project directory:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e '.[dev]'
.venv\Scripts\python.exe -m game_recommender.cli serve
```

Then open **http://127.0.0.1:8000/**. Use the last command to restart the server.

Start in **Discover** and rate a few familiar games. Compare **Your taste** with
**Similar players**, or choose **Describe a game** to search in natural language.
**Your ratings** lets you update or clear saved ratings. The demo-data disclosure is
always visible. To enable semantic search, follow the setup below.

On macOS/Linux, replace `.venv\Scripts\python.exe` with `.venv/bin/python`.
An editable install also supplies `game-rs serve`, `game-rs prepare`,
`game-rs build-neural`, and `game-rs evaluate`.

For API development, open **http://127.0.0.1:8000/docs**, click an endpoint,
**Try it out**, and **Execute**:

1. `GET /api/status` shows the dataset mode and neural-index status.
2. `GET /api/games` browses the catalogue; try `q=Stardew` or `tag=Farming Sim`.
3. `PUT /api/ratings/413150` with body `{"rating": 5}` saves a rating for Stardew Valley.
4. `GET /api/profile` confirms the rating. The same browser keeps its profile cookie.
5. `GET /api/recommendations` compares `method=content` and `method=collaborative`.
6. `POST /api/search` with body `{"query": "a peaceful farm where I grow crops"}`
   performs description retrieval and reports the engine actually used.
7. `DELETE /api/ratings/413150` removes the rating.

Scores are similarities or weighted neighbor preferences, **not confidence
percentages or predicted stars**. Requests return at most ten unique unseen games.
Collaborative results may be shorter when there is insufficient positive evidence.

## Use the real Kaggle dataset

Download [Game Recommendations on Steam by Anton Kozyriev](https://www.kaggle.com/datasets/antonkozyriev/game-recommendations-on-steam)
using your own Kaggle account and place the extracted files in `data/raw/`:

```text
data/raw/
  games.csv
  users.csv
  recommendations.csv
  games_metadata.json
```

Required fields:

| File | Required fields |
| --- | --- |
| games.csv | app_id, title |
| users.csv | user_id, reviews |
| recommendations.csv | user_id, app_id, is_recommended; optional date for latest-review selection |
| games_metadata.json | app_id, description, tags; accepts a JSON array or JSON Lines |

```powershell
.venv\Scripts\python.exe -m game_recommender.cli prepare --users 2000 --min-reviews 5
.venv\Scripts\python.exe -m game_recommender.cli serve
```

Restart any running server after preparation. The default server selects
`data/processed/` when it contains a completed manifest; otherwise it uses the demo.
An explicitly configured invalid directory fails rather than silently choosing the
demo. The importer scans the complete recommendations file and retains only reviews
from the selected users, keeping at most 2,000,000 distinct interactions by default.
This can take time on a large file. Use `--users 500` for a smaller experiment.

Users are selected by a seeded hash from those with enough declared reviews, then
checked again for the minimum *observed* count after games missing metadata are
removed. Games require both tags and descriptions. Duplicates keep the latest date
when available; ties use the last source row. The manifest records sampling settings,
row counts, file sizes, and the binary mapping. Keep the source dataset version and
download date with your experiment notes; the download cannot be verified here until
the real files are supplied.

Binary Steam reviews map to **5 for recommended, 1 for not recommended** as a documented
modeling convention. They retain `steam_binary` provenance. Actual player star ratings
are stored separately and are never presented as the original Steam reviews.

Raw data, processed data, model artifacts, and local ratings are ignored by Git.
The importer refuses to overwrite a completed catalogue; choose a new `--output-dir`
for another experiment.

## Enable neural description search

```powershell
.venv\Scripts\python.exe -m pip install -e '.[neural]'
.venv\Scripts\python.exe -m game_recommender.cli build-neural
.venv\Scripts\python.exe -m game_recommender.cli serve
```

The build command downloads `sentence-transformers/all-MiniLM-L6-v2` on its first run
and creates normalized description embeddings in `artifacts/`. Its encoder cache is
kept in `artifacts/models/` inside the workspace. This is pretrained
neural inference, **not training a network ourselves**. Model downloads require internet
access and the neural extra adds PyTorch. CPU inference is sufficient for an initial
sample. See the [Sentence Transformers quickstart](https://sbert.net/docs/quickstart.html).

Restart the server after building. Send `"engine": "neural"` to require the neural
model or `"engine": "lexical"` to compare the baseline. The default `"engine": "auto"`
uses the neural index when present and the lexical baseline otherwise. Responses always
identify the method. Neural requests return HTTP 503 with setup instructions when the
index or locally cached encoder is unavailable. The server does not download models
inside an HTTP request.

Changing the game catalogue invalidates its neural index: run `build-neural` again.
The index checks the full catalogue fingerprint, item order, dimensions, finite values,
and vector norms. It loads NumPy arrays with pickle disabled.

## Evaluation and verification

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp tmp\pytest
.venv\Scripts\ruff.exe check src scripts tests
.venv\Scripts\python.exe -m game_recommender.cli evaluate
```

The evaluation holds out one positive review per eligible user and removes all test
pairs before constructing either model. A user needs at least three interactions and
two positives. The collaborative model excludes the query user's own training row
from neighbor selection. All methods rank against the same catalogue.

This is a random holdout experiment. Choose/tune parameters using a separate validation
split before reporting final test metrics; do not tune on the final holdout. Neural
search needs a separately judged query/game test set, which has not been supplied.
Demo evaluation results are explicitly marked synthetic and should not be included
as real project accuracy. The normal report is written to `artifacts/evaluation.json`.

The correctness suite verifies algorithm behavior, persistence, profile isolation,
validation, metadata joins, sampling reproducibility, holdout separation, and neural
index validation. Its test encoder is a controlled fixture; that unit test alone does
not verify a downloaded neural model.

`requirements-tested.txt` records the tested Windows/Python 3.12 environment,
including CPU PyTorch and neural dependencies. Reproduce that environment with
`pip install -r requirements-tested.txt` followed by `pip install -e '.[dev,neural]'`.
This snapshot is platform specific rather than a universal dependency lock.

## Configuration and structure

| Environment variable | Purpose |
| --- | --- |
| GAME_RS_DATA_DIR | Override the catalogue directory |
| GAME_RS_DB_PATH | Override the SQLite ratings database path |
| GAME_RS_ARTIFACT_DIR | Override the neural-index directory |

```text
src/game_recommender/
  api.py           HTTP API and app lifecycle
  catalog.py       Validated game and interaction data
  storage.py       SQLite profiles and explicit ratings
  engine.py        Content, user-based CF, and lexical retrieval
  neural.py        Pretrained embeddings and neural retrieval
  importer.py      Streaming Kaggle sample preparation
  evaluation.py    Positive-item holdout and ranking metrics
  cli.py           Local server and offline commands
  demo/            Labeled fixture catalogue and synthetic interactions
  web/             Player interface, styles, and browser logic
tests/             Algorithm and integration checks
scripts/           Reproducible synthetic fixture generation
docs/              Scope, modeling decisions, and next stages
```

The local browser profile is a convenience for this academic stage. Account login,
Steam account import, public deployment, neural fine-tuning, and
real-data quality results are not implemented yet. The server binds to loopback by
default. The source proposal does not require these additional account/deployment
features.

