from dataclasses import dataclass
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

@dataclass(frozen=True)
class Settings:
    data_dir: Path = ROOT / "data" / "raw" / "ml-latest-small"
    artifact_dir: Path = ROOT / "artifacts"
    database_path: Path = ROOT / "data" / "recommendations.sqlite3"
    seed: int = 42
    rank: int = 4
    max_iter: int = 2
    reg_param: float = 0.1
    relevance_threshold: float = 4.0
    recommendation_count: int = 10
    als_weight: float = 0.70
    content_weight: float = 0.20
    popularity_weight: float = 0.10

    @classmethod
    def from_env(cls):
        defaults = cls()
        return cls(
            data_dir=Path(os.getenv("MOVIE_DATA_DIR", str(defaults.data_dir))),
            artifact_dir=Path(os.getenv("MOVIE_ARTIFACT_DIR", str(defaults.artifact_dir))),
            database_path=Path(os.getenv("MOVIE_DATABASE", str(defaults.database_path))),
            seed=int(os.getenv("ALS_SEED", defaults.seed)),
            rank=int(os.getenv("ALS_RANK", defaults.rank)),
            max_iter=int(os.getenv("ALS_MAX_ITER", defaults.max_iter)),
            reg_param=float(os.getenv("ALS_REG_PARAM", defaults.reg_param)),
            relevance_threshold=float(os.getenv("RELEVANCE_THRESHOLD", defaults.relevance_threshold)),
            recommendation_count=int(os.getenv("RECOMMENDATION_COUNT", defaults.recommendation_count)),
            als_weight=float(os.getenv("ALS_WEIGHT", defaults.als_weight)),
            content_weight=float(os.getenv("CONTENT_WEIGHT", defaults.content_weight)),
            popularity_weight=float(os.getenv("POPULARITY_WEIGHT", defaults.popularity_weight)),
        )

    @property
    def ratings_path(self) -> Path:
        return self.data_dir / "ratings.csv"

    @property
    def movies_path(self) -> Path:
        return self.data_dir / "movies.csv"
