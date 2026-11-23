# Project understanding

This document distinguishes proposal requirements from implementation
decisions. The proposal does not specify a framework, deployment provider, evaluation
protocol, or whether the neural encoder must be trained from scratch.

## Purpose

Build a web application that helps a player discover Steam games. A personalized
recommendation request returns a ranked top-10 list of games the player has not rated.
The player can also describe a desired game in natural language.

## Required techniques

| Proposal requirement | Implementation and acceptance criterion |
| --- | --- |
| Content filtering over game tags | TF-IDF vectors with whole tags as features; a rating-weighted user profile; cosine ranking; rated games excluded. |
| User-based collaborative filtering | A sparse user-game matrix and cosine nearest neighbors; positive neighbor evidence produces a ranked list; no dense all-user similarity matrix. |
| Neural search over descriptions | A sentence encoder embeds game descriptions and text queries; normalized-vector similarity retrieves games. A lexical baseline is labeled separately. |
| Ratings from 1 to 5 | Players submit integer star ratings stored in SQLite; low ratings influence content preferences negatively. |
| Ranked top 10 per user | At most ten unique unseen games; a smaller list is legitimate when evidence or eligible games are insufficient. |
| Active-user subsample | Deterministic sampling of eligible users, chunk-independent review streaming, and a minimum observed interaction threshold. |
| Honest work | Synthetic fixtures and baseline search are identified; no reported training or evaluation results without the actual experiment. |

## Data and the rating mismatch

The specified source is Anton Kozyriev's [Game Recommendations on Steam on
Kaggle](https://www.kaggle.com/datasets/antonkozyriev/game-recommendations-on-steam).
The proposal describes over 41 million binary reviews, user profiles, descriptions,
and tags. The intended local input files are `games.csv`, `users.csv`,
`recommendations.csv`, and `games_metadata.json`; the importer validates their required
columns instead of assuming a download is correct.

Steam's `is_recommended` signal is not a measured star rating. For this first
implementation, positive reviews map to **5** and negative reviews to **1** at the
model input boundary. Every imported interaction retains `steam_binary` provenance.
This is an explicit modeling convention, not a claim about the source data. Real
1-5 user ratings remain separate. Do not derive intermediate star ratings from
playtime or helpfulness without a justified experiment.

The bundled catalogue contains real game identifiers, manually written descriptions,
and illustrative tags. Its peer interactions are synthetic test fixtures. It exists
to exercise the complete local workflow and establish correctness; it is not the
Kaggle subsample and cannot demonstrate real recommendation quality.

## Architecture decisions

- Python/FastAPI owns catalogue access, recommendation logic, neural search, and API
  validation. A browser interface calls the API on the same origin.
- SQLite stores local browser profiles and explicit ratings. This first stage is a
  local academic application, without account authentication or Steam sign-in.
- SciPy sparse matrices and scikit-learn TF-IDF keep the chosen sample practical.
  Full 41-million-review ingestion is a separate offline streaming operation.
- The catalogue is immutable during one server run. Importing a different catalogue
  requires a server restart. Stale star ratings for missing games are ignored.
- Neural embeddings are built offline and bound to a catalogue fingerprint and model
  identifier. Serving checks these before using an index.
- Start with a pretrained sentence encoder. Fine-tuning or training from scratch
  remains a later academic decision; the user confirmed a pretrained encoder for the
  first implementation. Pretrained inference is not reported as our training.
- Avoid an unrequested hybrid algorithm: content and collaborative results remain
  independently inspectable, matching the three techniques in the proposal.

## Ranking behavior

Content profiles use weights `rating - 3`. Neutral ratings supply no preference;
dislikes subtract tag evidence. If there is no useful profile, return an explicitly
labeled popularity fallback based on positive peer interaction counts. Cosine values
are similarity scores, not percentages or predicted stars.

Collaborative similarity uses centered ratings (`rating - 3`) and positive cosine
neighbors. Neighbor contributions are adjusted for shared rated games to reduce
single-overlap matches. Games need positive net neighbor evidence. When none exists,
return a labeled popularity fallback; never claim nonexistent similar users.

Description search defaults to a TF-IDF lexical baseline until the neural extra and
embeddings are installed. The response and interface state which engine actually ran.
Requesting the neural engine before setup returns an actionable unavailable response.

## Evaluation plan

For content and collaborative models, hold out one positive interaction for every
eligible user using a deterministic seed. Fit both models on the remaining interactions
only and rank against the same complete catalogue. Report Recall@10, NDCG@10, catalogue
coverage, evaluated-user count, cold-start cases, and fallback frequency, alongside a
popularity baseline. This is a random holdout, not a temporal generalization claim.

Neural search needs human-reviewed query/relevant-game judgments; describe the query
set and report retrieval metrics separately. No such judgments are supplied in the
proposal, so do not invent a neural accuracy score.

## Work stages

1. **Working foundation:** validated catalogue, real content and collaborative
   algorithms, rating persistence, API, importer, baseline search, neural-index
   setup path, a responsive player interface, correctness tests, and setup documentation.
2. **Real-data experiment:** download the specified source, record its version,
   prepare the active-user sample, run the holdout evaluation, inspect coverage and
   cold starts, and build neural embeddings.
3. **Refinement:** review results and query judgments, tune using validation data,
   decide whether to fine-tune the neural model, improve explanations and interface,
   and prepare the final report and demonstration.

## Verified implementation references

- [Sentence Transformers quickstart](https://sbert.net/docs/quickstart.html): a
  pretrained encoder produces embeddings suitable for similarity retrieval.
- [scikit-learn feature extraction](https://scikit-learn.org/stable/modules/feature_extraction.html):
  TF-IDF vectorization and sparse feature representations.
- [FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/): validated HTTP API implementation.

