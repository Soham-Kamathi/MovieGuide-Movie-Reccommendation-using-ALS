"""Rating prediction and top-K offline evaluation helpers."""
from __future__ import annotations
import math
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def error_metrics(actual, predicted) -> dict[str, float]:
    pairs = [(float(a), float(p)) for a, p in zip(actual, predicted)
             if pd.notna(a) and pd.notna(p) and math.isfinite(float(p))]
    if not pairs:
        return {"rmse": float("nan"), "mae": float("nan")}
    errors = np.asarray([p-a for a,p in pairs])
    return {"rmse": float(np.sqrt(np.mean(errors**2))), "mae": float(np.mean(np.abs(errors)))}

def ranking_metrics(recommendations: dict, relevant: dict, k: int, catalog_ids: set[int]) -> dict[str, float]:
    precision, recall, ndcg, catalog = [], [], [], set()
    for user, truth in relevant.items():
        if not truth:
            continue
        items = list(recommendations.get(user, []))[:k]
        hits = [int(item in truth) for item in items]
        precision.append(sum(hits) / k)
        recall.append(sum(hits) / len(truth))
        dcg = sum(hit / math.log2(pos+2) for pos,hit in enumerate(hits))
        ideal = sum(1 / math.log2(pos+2) for pos in range(min(len(truth),k)))
        ndcg.append(dcg / ideal if ideal else 0.0)
        catalog.update(items)
    return {"precision_at_k": float(np.mean(precision)) if precision else 0.0,
            "recall_at_k": float(np.mean(recall)) if recall else 0.0,
            "ndcg_at_k": float(np.mean(ndcg)) if ndcg else 0.0,
            "catalog_coverage": len(catalog & catalog_ids)/len(catalog_ids) if catalog_ids else 0.0,
            "users_evaluated": len(precision)}

def relevant_items(test: pd.DataFrame, threshold: float) -> dict[int, set[int]]:
    selected = test[test.rating >= threshold]
    return {int(user): set(group.movieId.astype(int)) for user,group in selected.groupby("userIndex")}

def evaluate_recommendation_sources(bundle, movies: pd.DataFrame, als_candidates: dict[int, dict[int, float]],
                                    threshold: float, k: int=10,
                                    weights: tuple[float,float,float]=(.70,.20,.10),
                                    evaluation_data: pd.DataFrame | None=None) -> dict:
    """Compare popularity, ALS and normalized hybrid ranking on the same test users."""
    evaluating_validation=evaluation_data is not None
    fitting_data=bundle.train if evaluating_validation else pd.concat([bundle.train,bundle.validation],ignore_index=True)
    truth=relevant_items(evaluation_data if evaluating_validation else bundle.test,threshold)
    train_seen={int(user):set(group.movieId.astype(int)) for user,group in fitting_data.groupby("userIndex")}
    train_stats=fitting_data.groupby("movieId").rating.agg(["count","mean"])
    prior=float(train_stats["mean"].mean()) if len(train_stats) else 0.0
    pop=((train_stats["count"]*train_stats["mean"]+20*prior)/(train_stats["count"]+20)).to_dict()
    popularity={int(movie):float(score) for movie,score in pop.items()}
    catalog=movies.movieId.astype(int).tolist()
    movie_rows={movie:i for i,movie in enumerate(catalog)}
    genre_text=movies.genres.fillna("").str.replace("|"," ",regex=False)
    try:
        vectors=CountVectorizer(token_pattern=r"(?u)\b\w+\b").fit_transform(genre_text)
    except ValueError:
        vectors=None
    raw_als, raw_content, raw_pop, hybrid={}, {}, {}, {}
    for user in truth:
        seen=train_seen.get(user,set())
        als={int(movie):float(score) for movie,score in als_candidates.get(user,{}).items() if int(movie) not in seen}
        user_train=fitting_data[fitting_data.userIndex==user]
        liked=[movie_rows[int(row.movieId)] for row in user_train.itertuples() if row.rating>=4 and int(row.movieId) in movie_rows]
        if not liked: liked=[movie_rows[int(movie)] for movie in seen if int(movie) in movie_rows]
        if liked and vectors is not None:
            vector=np.asarray(vectors[liked].mean(axis=0))
            similarity=cosine_similarity(vector,vectors).ravel()
            content={movie:float(similarity[row]) for row,movie in enumerate(catalog) if movie not in seen}
        else: content={}
        popularity_user={movie:score for movie,score in popularity.items() if movie not in seen}
        raw_als[user]=als; raw_content[user]=content; raw_pop[user]=popularity_user
        normalized=[]
        for source in (als,content,popularity_user):
            if not source: normalized.append({}); continue
            low,high=min(source.values()),max(source.values())
            normalized.append({movie:(1.0 if high==low else (score-low)/(high-low)) for movie,score in source.items()})
        ids=set().union(*(set(source) for source in normalized))
        total=sum(weights) or 1.0
        blend={movie:sum(weights[i]/total*normalized[i].get(movie,0) for i in range(3)) for movie in ids}
        hybrid[user]=blend
    def top(source):
        return {user:[movie for movie,_ in sorted(scores.items(),key=lambda pair:(-pair[1],pair[0]))[:k]] for user,scores in source.items()}
    catalog_set=set(catalog)
    return {"popularity":ranking_metrics(top(raw_pop),truth,k,catalog_set),
            "als_only":ranking_metrics(top(raw_als),truth,k,catalog_set),
            "hybrid":ranking_metrics(top(hybrid),truth,k,catalog_set)}
