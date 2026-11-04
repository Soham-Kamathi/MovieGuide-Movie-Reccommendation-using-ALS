"""Framework-independent retrieval, fallback and candidate ranking."""
from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity

class RecommendationService:
    def __init__(self, movies, ratings, store, model=None, user_to_index=None, movie_to_index=None,
                 als_weight=.70, content_weight=.20, popularity_weight=.10):
        self.movies, self.ratings, self.store, self.model = movies.copy(), ratings.copy(), store, model
        self.user_to_index, self.movie_to_index = user_to_index or {}, movie_to_index or {}
        weights = np.asarray([als_weight,content_weight,popularity_weight],dtype=float)
        self.weights = weights/weights.sum() if weights.sum() else np.ones(3)/3
        self.movie_ids = self.movies.movieId.astype(int).tolist()
        self.movie_row = {movie_id:i for i,movie_id in enumerate(self.movie_ids)}
        genres = self.movies.genres.fillna("").str.replace("|"," ",regex=False)
        try:
            self.movie_vectors = CountVectorizer(token_pattern=r"(?u)\b\w+\b").fit_transform(genres) if len(genres) else None
        except ValueError:
            self.movie_vectors = None
        stats = self.ratings.groupby("movieId").rating.agg(["count","mean"])
        prior = float(stats["mean"].mean()) if len(stats) else 0.0
        scores = (stats["count"]*stats["mean"]+20*prior)/(stats["count"]+20) if len(stats) else stats["mean"]
        self.popularity = {int(k):float(v) for k,v in scores.items()}

    @staticmethod
    def _normalize(scores):
        if not scores: return {}
        values=np.asarray(list(scores.values()),dtype=float); low,high=np.nanmin(values),np.nanmax(values)
        if not np.isfinite(low) or not np.isfinite(high): return {}
        if high==low: return {int(k):1.0 for k in scores}
        return {int(k):float((v-low)/(high-low)) for k,v in scores.items() if np.isfinite(v)}

    def _profile_ratings(self, profile_id):
        frame=self.store.ratings_for_profile(profile_id)
        return {int(r.movieId):float(r.rating) for r in frame.itertuples()}

    def _profile_user_index(self, profile_id):
        if self.store is None: return None
        profile = next((p for p in self.store.list_profiles() if p["profile_id"]==profile_id),None)
        key = str(profile["dataset_user_id"]) if profile and profile.get("dataset_user_id") is not None else profile_id
        return self.user_to_index.get(key)

    def _als_scores(self, profile_id, profile_ratings):
        user = self._profile_user_index(profile_id)
        if self.model is None: return {}
        movie_to_index={int(movie_id):int(index) for movie_id,index in self.movie_to_index.items()}
        index_to_movie = {index: movie_id for movie_id,index in movie_to_index.items()}
        if profile_ratings:
            ratings_by_index={movie_to_index[movie_id]:rating
                              for movie_id,rating in profile_ratings.items()
                              if movie_id in movie_to_index}
            candidates=self.model.recommend_for_ratings(ratings_by_index,500)
        elif user is not None:
            candidates=self.model.recommend_for_user(int(user),500)
        else:
            return {}
        return {index_to_movie[int(item)]: float(score)
                for item, score in candidates
                if int(item) in index_to_movie}

    def _content_scores(self, profile_ratings):
        if self.movie_vectors is None or not profile_ratings: return {}
        liked=[self.movie_row[mid] for mid,rating in profile_ratings.items() if rating>=4 and mid in self.movie_row]
        if not liked: liked=[self.movie_row[mid] for mid in profile_ratings if mid in self.movie_row]
        if not liked: return {}
        vector=np.asarray(self.movie_vectors[liked].mean(axis=0))
        sims=cosine_similarity(vector,self.movie_vectors).ravel()
        return {movie_id:float(sims[row]) for row,movie_id in enumerate(self.movie_ids)}

    def recommend(self, profile_id: str, n: int=10) -> list[dict]:
        if n<=0: return []
        profile_ratings=self._profile_ratings(profile_id); rated=set(profile_ratings)
        als=self._als_scores(profile_id,profile_ratings); content=self._content_scores(profile_ratings); popularity=self.popularity
        weights=(np.array([0.,0.,1.]) if not profile_ratings else
                 np.array([0.,.7,.3]) if not als else self.weights)
        sources=[self._normalize(als),self._normalize(content),self._normalize(popularity)]
        all_ids=set().union(*(set(source) for source in sources))-rated
        title_map=self.movies.assign(movieId=self.movies.movieId.astype(int)).set_index("movieId").title.to_dict()
        results=[]
        for movie_id in sorted(all_ids,key=lambda mid:(-sum(weights[i]*sources[i].get(mid,0.) for i in range(3)),mid)):
            if movie_id not in title_map: continue
            used=[name for i,(name,source) in enumerate(zip(("als","content","popularity"),sources)) if movie_id in source and weights[i]>0]
            results.append({"movie_id":int(movie_id),"title":str(title_map[movie_id]),
                            "score":float(sum(weights[i]*sources[i].get(movie_id,0.) for i in range(3))),
                            "source":"+".join(used) or "fallback"})
            if len(results)>=n: break
        return results
