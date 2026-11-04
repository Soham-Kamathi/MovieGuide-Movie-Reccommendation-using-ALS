"""SQLite persistence for local profiles, ratings and model registry metadata."""
from __future__ import annotations
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

class RatingStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def initialize(self):
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS profiles(profile_id TEXT PRIMARY KEY, display_name TEXT NOT NULL, dataset_user_id INTEGER, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS ratings(profile_id TEXT NOT NULL REFERENCES profiles(profile_id), movie_id INTEGER NOT NULL, rating REAL NOT NULL CHECK(rating >= 0.5 AND rating <= 5.0), timestamp INTEGER NOT NULL, PRIMARY KEY(profile_id,movie_id));
                CREATE TABLE IF NOT EXISTS model_registry(model_version TEXT PRIMARY KEY, trained_at TEXT NOT NULL, artifact_path TEXT NOT NULL, metrics_json TEXT NOT NULL, config_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS imported_ratings(userId INTEGER, movieId INTEGER, rating REAL, timestamp INTEGER, PRIMARY KEY(userId,movieId));
            """)

    def create_profile(self, display_name: str, dataset_user_id: int | None = None) -> str:
        name = display_name.strip()
        if not name:
            raise ValueError("Profile name cannot be empty")
        profile_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute("INSERT INTO profiles VALUES (?,?,?,?)", (profile_id, name, dataset_user_id, datetime.now(timezone.utc).isoformat()))
            if dataset_user_id is not None:
                db.execute("INSERT OR IGNORE INTO ratings SELECT ?,movieId,rating,timestamp FROM imported_ratings WHERE userId=?", (profile_id, int(dataset_user_id)))
        return profile_id

    def list_profiles(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM profiles ORDER BY display_name")]

    def rate(self, profile_id: str, movie_id: int, rating: float):
        if not 0.5 <= float(rating) <= 5.0:
            raise ValueError("Ratings must be between 0.5 and 5.0")
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM profiles WHERE profile_id=?", (profile_id,)).fetchone():
                raise ValueError("Unknown profile")
            db.execute("""INSERT INTO ratings VALUES (?,?,?,?) ON CONFLICT(profile_id,movie_id)
                DO UPDATE SET rating=excluded.rating,timestamp=excluded.timestamp""",
                (profile_id, int(movie_id), float(rating), int(datetime.now(timezone.utc).timestamp())))

    def ratings_for_profile(self, profile_id: str) -> pd.DataFrame:
        with self.connect() as db:
            return pd.read_sql_query("SELECT movie_id AS movieId,rating,timestamp FROM ratings WHERE profile_id=?", db, params=(profile_id,))

    def rated_movie_ids(self, profile_id: str) -> set[int]:
        return set(self.ratings_for_profile(profile_id).movieId.astype(int).tolist())

    def import_dataset(self, ratings: pd.DataFrame):
        with self.connect() as db:
            db.executemany("INSERT OR REPLACE INTO imported_ratings VALUES (?,?,?,?)",
                ratings[["userId","movieId","rating","timestamp"]].itertuples(index=False, name=None))

    def all_feedback(self) -> pd.DataFrame:
        with self.connect() as db:
            return pd.read_sql_query("SELECT COALESCE(p.dataset_user_id,p.profile_id) AS userId,r.movie_id AS movieId,r.rating,r.timestamp FROM ratings r JOIN profiles p USING(profile_id)", db)

    def record_model(self, version: str, artifact_path: str, metrics: dict, config: dict):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO model_registry VALUES (?,?,?,?,?)", (version, datetime.now(timezone.utc).isoformat(), artifact_path, json.dumps(metrics), json.dumps(config)))

    def latest_model(self):
        with self.connect() as db:
            row = db.execute("SELECT * FROM model_registry ORDER BY trained_at DESC LIMIT 1").fetchone()
            return dict(row) if row else None
