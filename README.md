# 🎬 MovieGuide: ALS Movie Recommendation Prototype

MovieGuide is a local, academic movie discovery prototype. It uses explicit-rating ALS implemented with NumPy/SciPy, genre similarity for local profiles that are not in the trained factors, and a Bayesian popularity score for a new profile. Streamlit presents the catalog and stores local profiles and ratings in SQLite. Training runs directly in Python and does not require Java or Spark.

## Requirements and setup

- Windows and Python 3.10 or 3.11.
- Install the recommender and UI libraries:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The explicit ALS model alternates regularized least-squares updates over user and movie factors and saves portable NumPy artifacts. Streamlit runs the app script with `streamlit run`. See the [Streamlit CLI documentation](https://docs.streamlit.io/develop/api-reference/cli).

## Data and model lifecycle

`python -m movie_recommender.cli prepare` downloads MovieLens `latest-small` on first run, validates rating values and required fields, keeps the latest timestamp for duplicate user/movie pairs, creates a chronological per-user split, and initializes the SQLite store. HTTPS certificate checks stay enabled; downloads use the `certifi` root bundle by default. If your network uses a private inspection proxy, set `SSL_CERT_FILE` to its trusted PEM CA bundle. Alternatively, download the dataset from [GroupLens](https://grouplens.org/datasets/movielens/latest/) and put `ratings.csv` and `movies.csv` in `data/raw/ml-latest-small/`. The test portion is the latest rating per user; the immediately preceding rating is validation when that user has at least three ratings. Users with fewer ratings retain at least one training interaction.

`python -m movie_recommender.cli train` trains CPU ALS on training interactions, selects regularization using validation RMSE, tunes hybrid source weights against validation NDCG@10, then refits on train plus validation and writes factor arrays, ID mappings, configuration and metrics under `artifacts/models/<UTC version>/`. New app feedback is merged into the next batch training set. Run `python -m movie_recommender.cli evaluate` to also calculate held-out RMSE/MAE and ranking metrics at K=10. Relevance is defined as a held-out rating >= 4.0. The report compares popularity, ALS-only and normalized hybrid ranking with precision@10, recall@10, NDCG@10 and catalog coverage. Test interactions are not used for model selection.

Common settings are exposed as CLI options:

```powershell
python -m movie_recommender.cli evaluate --rank 4 --max-iter 2 --reg-param 0.1 --seed 42 --relevance-threshold 4.0
```

The data, artifact, and database paths can also be overridden with `--data-dir`, `--artifact-dir`, and `--database`. Hybrid source weights can be set with `--als-weight`, `--content-weight`, and `--popularity-weight` (the validation tuning step selects the saved model's weights). Environment equivalents include `MOVIE_DATA_DIR`, `MOVIE_ARTIFACT_DIR`, `MOVIE_DATABASE`, `ALS_RANK`, `ALS_MAX_ITER`, `ALS_REG_PARAM`, `ALS_SEED`, `RELEVANCE_THRESHOLD`, `ALS_WEIGHT`, `CONTENT_WEIGHT`, and `POPULARITY_WEIGHT`. Training is a batch operation; saving a rating does not trigger a model rebuild.

## Run the app

```powershell
python -m movie_recommender.cli prepare
python -m movie_recommender.cli train
streamlit run app.py
```

Create a pseudonymous local profile or seed one from a sample MovieLens user's ratings. Current profile ratings are used to infer a profile-specific ALS factor immediately; genre similarity and popularity broaden candidates. Profiles without ratings see popularity picks. Recommendations exclude rated movies and return fewer than requested when the eligible catalog is small.

## Architecture

- `movie_recommender/data.py`: MovieLens download, validation, duplicate handling, chronological split, ID maps.
- `movie_recommender/model.py`: CPU explicit ALS training and artifact load/save.
- `movie_recommender/service.py`: ALS/content/popularity candidate generation, filtering and ranking.
- `movie_recommender/storage.py`: SQLite profiles, ratings, imported data and model registry.
- `movie_recommender/evaluation.py`: rating and top-K metrics.
- `movie_recommender/cli.py`: prepare, train and evaluate entry point.
- `app.py`: Streamlit profile, rating and recommendation UI.

## Reproducibility and limitations

The default seed is 42. Data splits sort interactions by timestamp per user and use stable ordering for ties. ALS predictions and ranking quality depend on the data and parameter choices; report the generated metric JSON rather than claiming a preset accuracy. Local profiles have no authentication or synchronization. Cold-start genre similarity uses MovieLens genre tags, not plot or cast metadata. Saved ratings are used immediately to infer a profile-specific ALS factor against the current movie factors; full movie factors refresh on the next batch training run.

## Tests

Run the unit and service checks with `pytest`. The tests cover invalid records, duplicate policy, chronological splitting, ID mapping, native ALS artifact round-trip, rating storage and updates, cold-start fallbacks, rated-item filtering, and metric calculations. No Spark or Java runtime is required.
