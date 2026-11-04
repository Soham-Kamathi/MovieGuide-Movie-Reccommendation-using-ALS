"""MovieLens ingestion, validation, chronological splitting and ID mapping."""
from __future__ import annotations
import json
import os
import ssl
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd

MOVIELENS_URL = "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip"
RATING_COLUMNS = ["userId", "movieId", "rating", "timestamp"]

def _https_context() -> ssl.SSLContext:
    """Build a verified TLS context, honoring an administrator-provided CA bundle."""
    ca_file = os.getenv("SSL_CERT_FILE") or os.getenv("REQUESTS_CA_BUNDLE")
    if ca_file:
        return ssl.create_default_context(cafile=ca_file)
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())

@dataclass
class DatasetBundle:
    ratings: pd.DataFrame
    movies: pd.DataFrame
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    user_to_index: dict[str, int]
    movie_to_index: dict[str, int]

def download_movielens(data_dir: Path) -> tuple[Path, Path]:
    data_dir = Path(data_dir)
    if (data_dir / "ratings.csv").exists() and (data_dir / "movies.csv").exists():
        return data_dir / "ratings.csv", data_dir / "movies.csv"
    data_dir.parent.mkdir(parents=True, exist_ok=True)
    archive = data_dir.parent / "ml-latest-small.zip"
    partial_archive = archive.with_suffix(archive.suffix + ".part")
    try:
        request = urllib.request.Request(MOVIELENS_URL, headers={"User-Agent": "movieguide/0.1"})
        with urllib.request.urlopen(request, context=_https_context(), timeout=60) as response, partial_archive.open("wb") as target:
            shutil.copyfileobj(response, target)
        partial_archive.replace(archive)
    except urllib.error.URLError as exc:
        partial_archive.unlink(missing_ok=True)
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(reason):
            message = (
                "MovieLens download failed certificate verification. Install/update certifi "
                "(`python -m pip install --upgrade certifi`) or set SSL_CERT_FILE to your "
                "trusted PEM CA bundle. You can also download ml-latest-small.zip from "
                "https://grouplens.org/datasets/movielens/latest/ and extract ratings.csv "
                f"and movies.csv into {data_dir}. Original error: {exc}"
            )
        else:
            message = f"Could not download MovieLens from {MOVIELENS_URL}. Check network access and retry. Original error: {exc}"
        raise RuntimeError(message) from exc
    except ssl.SSLCertVerificationError as exc:
        partial_archive.unlink(missing_ok=True)
        raise RuntimeError(
            "MovieLens download failed certificate verification. Install/update certifi "
            "or set SSL_CERT_FILE to your trusted PEM CA bundle."
        ) from exc
    except Exception:
        partial_archive.unlink(missing_ok=True)
        raise
    data_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for name in ("ml-latest-small/ratings.csv", "ml-latest-small/movies.csv"):
            with zf.open(name) as source, (data_dir / Path(name).name).open("wb") as target:
                shutil.copyfileobj(source, target)
    return data_dir / "ratings.csv", data_dir / "movies.csv"

def load_movielens(ratings_path: Path, movies_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    ratings, movies = pd.read_csv(ratings_path), pd.read_csv(movies_path)
    missing = set(RATING_COLUMNS) - set(ratings.columns)
    if missing:
        raise ValueError(f"ratings.csv is missing required columns: {sorted(missing)}")
    if not {"movieId", "title", "genres"}.issubset(movies.columns):
        raise ValueError("movies.csv must contain movieId, title and genres")
    ratings = ratings[RATING_COLUMNS].copy()
    for col in RATING_COLUMNS:
        ratings[col] = pd.to_numeric(ratings[col], errors="coerce")
    ratings = ratings.dropna(subset=RATING_COLUMNS)
    valid_ids = ((ratings.userId > 0) & (ratings.movieId > 0) & (ratings.timestamp >= 0) &
                 np.isclose(ratings.userId % 1, 0) & np.isclose(ratings.movieId % 1, 0) &
                 np.isclose(ratings.timestamp % 1, 0))
    ratings = ratings[valid_ids & ratings.rating.between(0.5, 5.0)]
    ratings[["userId", "movieId", "timestamp"]] = ratings[["userId", "movieId", "timestamp"]].astype("int64")
    # For duplicate pairs, the latest timestamp wins; original order resolves timestamp ties.
    ratings["_row"] = np.arange(len(ratings))
    ratings = (ratings.sort_values(["timestamp", "_row"])
               .drop_duplicates(["userId", "movieId"], keep="last")
               .drop(columns="_row").reset_index(drop=True))
    movies = movies[["movieId", "title", "genres"]].drop_duplicates("movieId", keep="last").copy()
    movies["movieId"] = pd.to_numeric(movies.movieId, errors="coerce")
    movies = movies.dropna(subset=["movieId"])
    movies = movies[(movies.movieId > 0) & np.isclose(movies.movieId % 1, 0)]
    movies["movieId"] = movies.movieId.astype("int64")
    movies["title"] = movies.title.fillna("Untitled")
    movies["genres"] = movies.genres.fillna("")
    return ratings, movies

def chronological_split(ratings: pd.DataFrame):
    """Per user: latest rating is test, prior rating validation (when available)."""
    train_parts, validation_parts, test_parts = [], [], []
    ordered = ratings.sort_values(["userId", "timestamp", "movieId"], kind="mergesort")
    for _, group in ordered.groupby("userId", sort=False):
        group = group.reset_index(drop=True)
        if len(group) >= 3:
            train_parts.append(group.iloc[:-2])
            validation_parts.append(group.iloc[[-2]])
            test_parts.append(group.iloc[[-1]])
        elif len(group) == 2:
            train_parts.append(group.iloc[:1])
            test_parts.append(group.iloc[1:])
        else:
            train_parts.append(group)
    empty = ratings.iloc[:0].copy()
    combine = lambda parts: pd.concat(parts, ignore_index=True) if parts else empty.copy()
    return combine(train_parts), combine(validation_parts), combine(test_parts)

def build_bundle(ratings: pd.DataFrame, movies: pd.DataFrame) -> DatasetBundle:
    train, validation, test = chronological_split(ratings)
    users = sorted(ratings.userId.astype(str).unique())
    items = sorted(set(ratings.movieId.astype(str)) | set(movies.movieId.astype(str)))
    user_map, item_map = ({key: i for i, key in enumerate(keys)} for keys in (users, items))
    def mapped(frame):
        result = frame.copy()
        result["userIndex"] = result.userId.astype(str).map(user_map).astype("int32")
        result["movieIndex"] = result.movieId.astype(str).map(item_map).astype("int32")
        return result
    return DatasetBundle(ratings, movies, mapped(train), mapped(validation), mapped(test), user_map, item_map)

def save_mappings(bundle: DatasetBundle, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "mappings.json").write_text(json.dumps({
        "user_to_index": bundle.user_to_index, "movie_to_index": bundle.movie_to_index
    }, indent=2), encoding="utf-8")
