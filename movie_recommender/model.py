"""Pure-Python explicit-rating ALS and portable model artifact I/O."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from threadpoolctl import threadpool_limits

from .data import DatasetBundle, save_mappings
from .evaluation import error_metrics


class ExplicitALSModel:
    """Small CPU ALS model with regularized global, user and item biases."""

    def __init__(self, user_factors, item_factors, global_mean, user_bias, item_bias):
        self.user_factors = np.asarray(user_factors, dtype=np.float64)
        self.item_factors = np.asarray(item_factors, dtype=np.float64)
        self.global_mean = float(global_mean)
        self.user_bias = np.asarray(user_bias, dtype=np.float64)
        self.item_bias = np.asarray(item_bias, dtype=np.float64)

    def predict(self, user: int, item: int) -> float:
        estimate = self.global_mean
        if 0 <= user < len(self.user_bias):
            estimate += self.user_bias[user]
        if 0 <= item < len(self.item_bias):
            estimate += self.item_bias[item]
        if (0 <= user < len(self.user_factors) and 0 <= item < len(self.item_factors)):
            estimate += float(self.user_factors[user] @ self.item_factors[item])
        return float(np.clip(estimate, 0.5, 5.0))

    def predict_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        result = frame[["userIndex", "movieIndex", "rating"]].copy()
        result["prediction"] = [self.predict(int(u), int(i)) for u, i in
                                result[["userIndex", "movieIndex"]].itertuples(index=False, name=None)]
        return result

    def recommend_for_user(self, user: int, n: int = 200) -> list[tuple[int, float]]:
        if user < 0 or user >= len(self.user_factors) or n <= 0:
            return []
        scores = self.global_mean + self.user_bias[user] + self.item_bias
        scores = scores + self.item_factors @ self.user_factors[user]
        if len(scores) <= n:
            indexes = np.argsort(-scores, kind="stable")
        else:
            subset = np.argpartition(-scores, n - 1)[:n]
            indexes = subset[np.argsort(-scores[subset], kind="stable")]
        return [(int(i), float(np.clip(scores[i], 0.5, 5.0))) for i in indexes]

    def recommend_for_ratings(self, ratings: dict[int, float], n: int = 500,
                              regularization: float = 0.1) -> list[tuple[int, float]]:
        """Infer a current profile factor from its latest ratings and fixed item factors."""
        observed = [(int(item), float(value)) for item, value in ratings.items()
                    if 0 <= int(item) < len(self.item_factors)]
        if not observed or n <= 0:
            return []
        items = np.asarray([item for item, _ in observed], dtype=np.int64)
        values = np.asarray([value for _, value in observed], dtype=np.float64)
        factors = self.item_factors[items]
        targets = values - self.global_mean - self.item_bias[items]
        identity = np.eye(self.item_factors.shape[1], dtype=np.float64)
        with threadpool_limits(limits=1):
            profile_factor = np.linalg.solve(
                factors.T @ factors + regularization * identity,
                factors.T @ targets,
            )
        scores = self.global_mean + self.item_bias + self.item_factors @ profile_factor
        scores[items] = -np.inf
        eligible = np.flatnonzero(np.isfinite(scores))
        if not len(eligible):
            return []
        take = min(n, len(eligible))
        candidates = eligible[np.argpartition(-scores[eligible], take - 1)[:take]]
        candidates = candidates[np.argsort(-scores[candidates], kind="stable")]
        return [(int(item), float(np.clip(scores[item], 0.5, 5.0))) for item in candidates]

    def save(self, path: Path):
        np.savez_compressed(path, user_factors=self.user_factors, item_factors=self.item_factors,
                            global_mean=self.global_mean, user_bias=self.user_bias, item_bias=self.item_bias)

    @classmethod
    def load(cls, path: Path):
        with np.load(path, allow_pickle=False) as data:
            return cls(data["user_factors"], data["item_factors"], data["global_mean"],
                       data["user_bias"], data["item_bias"])


def _fit_als(frame: pd.DataFrame, n_users: int, n_items: int, rank: int,
             max_iter: int, reg_param: float, seed: int) -> ExplicitALSModel:
    if frame.empty:
        raise ValueError("No valid training ratings remain after preprocessing")
    users = frame.userIndex.to_numpy(dtype=np.int64)
    items = frame.movieIndex.to_numpy(dtype=np.int64)
    values = frame.rating.to_numpy(dtype=np.float64)
    global_mean = float(values.mean())
    user_bias = np.zeros(n_users, dtype=np.float64)
    item_bias = np.zeros(n_items, dtype=np.float64)
    user_counts = np.bincount(users, minlength=n_users)
    item_counts = np.bincount(items, minlength=n_items)
    # A few regularized baseline passes improve explicit-rating estimates.
    for _ in range(5):
        user_residual = values - global_mean - item_bias[items]
        user_sums = np.bincount(users, weights=user_residual, minlength=n_users)
        user_bias = user_sums / (user_counts + reg_param * 10)
        item_residual = values - global_mean - user_bias[users]
        item_sums = np.bincount(items, weights=item_residual, minlength=n_items)
        item_bias = item_sums / (item_counts + reg_param * 10)
    residuals = values - global_mean - user_bias[users] - item_bias[items]
    matrix = coo_matrix((residuals, (users, items)), shape=(n_users, n_items)).tocsr()
    by_item = matrix.tocsc()
    rng = np.random.default_rng(seed)
    scale = 0.01
    user_factors = rng.normal(0, scale, (n_users, rank))
    item_factors = rng.normal(0, scale, (n_items, rank))
    identity = np.eye(rank, dtype=np.float64)

    # Tiny per-user/item systems are much faster without launching a large
    # OpenBLAS worker pool for each individual solve on typical Windows PCs.
    with threadpool_limits(limits=1):
        for _ in range(max_iter):
            for user in range(n_users):
                start, end = matrix.indptr[user:user + 2]
                indexes = matrix.indices[start:end]
                if not len(indexes):
                    user_factors[user] = 0
                    continue
                factors = item_factors[indexes]
                user_factors[user] = np.linalg.solve(
                    factors.T @ factors + reg_param * identity,
                    factors.T @ matrix.data[start:end],
                )
            for item in range(n_items):
                start, end = by_item.indptr[item:item + 2]
                indexes = by_item.indices[start:end]
                if not len(indexes):
                    item_factors[item] = 0
                    continue
                factors = user_factors[indexes]
                item_factors[item] = np.linalg.solve(
                    factors.T @ factors + reg_param * identity,
                    factors.T @ by_item.data[start:end],
                )
    return ExplicitALSModel(user_factors, item_factors, global_mean, user_bias, item_bias)


def train_als(train: pd.DataFrame, validation: pd.DataFrame, settings, output_dir: Path,
              bundle: DatasetBundle | None = None):
    """Tune CPU ALS on validation, then refit on train plus validation."""
    if train.empty:
        raise ValueError("No valid training ratings remain after preprocessing")
    n_users = int(max(train.userIndex.max(), validation.userIndex.max() if len(validation) else 0)) + 1
    n_items = int(max(train.movieIndex.max(), validation.movieIndex.max() if len(validation) else 0)) + 1
    candidates = list(dict.fromkeys([
        (settings.rank, settings.reg_param),
        (settings.rank, settings.reg_param * 2),
    ])) if len(validation) else [(settings.rank, settings.reg_param)]
    best = None
    for rank, reg in candidates:
        candidate = _fit_als(train, n_users, n_items, rank, settings.max_iter, reg, settings.seed)
        predictions = candidate.predict_frame(validation) if len(validation) else None
        score = (error_metrics(predictions.rating, predictions.prediction)["rmse"]
                 if predictions is not None else float("inf"))
        if best is None or score < best[0]:
            best = (score, rank, reg, candidate)
    score, rank, reg, selected_model = best
    chosen_weights = (settings.als_weight, settings.content_weight, settings.popularity_weight)
    if bundle is not None and len(bundle.validation):
        from .evaluation import evaluate_recommendation_sources
        inverse = {int(index): int(movie_id) for movie_id, index in bundle.movie_to_index.items()}
        users = sorted(bundle.validation.loc[
            bundle.validation.rating >= settings.relevance_threshold, "userIndex"
        ].astype(int).unique().tolist())[:25]
        tuning_rows = bundle.validation[bundle.validation.userIndex.isin(users)]
        candidate_map = {int(user): {inverse[item]: score for item, score in
                         selected_model.recommend_for_user(int(user), 200) if item in inverse}
                         for user in users}
        weight_grid = [(.7,.2,.1),(.5,.4,.1),(.5,.2,.3)]
        evaluations = [(evaluate_recommendation_sources(bundle, bundle.movies, candidate_map,
                        settings.relevance_threshold, 10, weights, tuning_rows)["hybrid"]["ndcg_at_k"], weights)
                       for weights in weight_grid]
        if evaluations:
            chosen_weights = max(evaluations, key=lambda item: item[0])[1]
    final_train = pd.concat([train, validation], ignore_index=True) if len(validation) else train
    model = (selected_model if not len(validation) else
             _fit_als(final_train, n_users, n_items, rank, settings.max_iter, reg, settings.seed))
    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = Path(output_dir) / version
    artifact_dir.mkdir(parents=True, exist_ok=True)
    model.save(artifact_dir / "als_model.npz")
    config = {"algorithm": "explicit_als_numpy", "rank": rank, "reg_param": reg,
              "max_iter": settings.max_iter, "seed": settings.seed,
              "explicit_ratings": True, "als_weight": chosen_weights[0],
              "content_weight": chosen_weights[1], "popularity_weight": chosen_weights[2]}
    (artifact_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    if bundle:
        save_mappings(bundle, artifact_dir)
    return artifact_dir, version, model, config, score


def load_als_model(artifact_dir: Path):
    return ExplicitALSModel.load(Path(artifact_dir) / "als_model.npz")
