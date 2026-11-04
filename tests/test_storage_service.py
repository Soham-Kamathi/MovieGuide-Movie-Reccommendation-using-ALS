import pandas as pd
import pytest
from movie_recommender.service import RecommendationService
from movie_recommender.storage import RatingStore

def test_profile_rating_validation_and_upsert(tmp_path):
    store=RatingStore(tmp_path/"ratings.db")
    profile=store.create_profile("Test")
    store.rate(profile,1,3.5); store.rate(profile,1,4.5)
    assert store.ratings_for_profile(profile).iloc[0].rating==4.5
    assert store.all_feedback().iloc[0].rating==4.5
    with pytest.raises(ValueError): store.rate(profile,2,5.5)

def test_new_profile_gets_popularity(tmp_path):
    store=RatingStore(tmp_path/"ratings.db")
    profile=store.create_profile("New")
    movies=pd.DataFrame([
        {"movieId":1,"title":"Drama One","genres":"Drama"},
        {"movieId":2,"title":"Drama Two","genres":"Drama"},
        {"movieId":3,"title":"Comedy","genres":"Comedy"},
    ])
    ratings=pd.DataFrame([
        {"userId":1,"movieId":1,"rating":5.,"timestamp":1},
        {"userId":2,"movieId":2,"rating":4.,"timestamp":2},
        {"userId":3,"movieId":3,"rating":1.,"timestamp":3},
    ])
    service=RecommendationService(movies,ratings,store)
    results=service.recommend(profile,10)
    assert results
    assert all(row["source"]=="popularity" for row in results)
    assert results[0]["source"]=="popularity"
    assert [row["score"] for row in results]==sorted([row["score"] for row in results],reverse=True)

def test_already_rated_items_are_excluded(tmp_path):
    store=RatingStore(tmp_path/"ratings.db"); profile=store.create_profile("Rated")
    movies=pd.DataFrame([{"movieId":1,"title":"A","genres":"Drama"},{"movieId":2,"title":"B","genres":"Drama"}])
    ratings=pd.DataFrame([{"userId":1,"movieId":1,"rating":5.,"timestamp":1},{"userId":2,"movieId":2,"rating":4.,"timestamp":2}])
    store.rate(profile,1,5.)
    result=RecommendationService(movies,ratings,store).recommend(profile,10)
    assert all(row["movie_id"]!=1 for row in result)

def test_untrained_rated_profile_uses_content_source(tmp_path):
    store=RatingStore(tmp_path/"ratings.db"); profile=store.create_profile("Known locally")
    movies=pd.DataFrame([
        {"movieId":1,"title":"Drama One","genres":"Drama"},
        {"movieId":2,"title":"Drama Two","genres":"Drama"},
        {"movieId":3,"title":"Comedy","genres":"Comedy"},
    ])
    ratings=pd.DataFrame([{"userId":1,"movieId":1,"rating":5.,"timestamp":1}])
    store.rate(profile,1,5.)
    result=RecommendationService(movies,ratings,store).recommend(profile,2)
    assert result[0]["movie_id"]==2
    assert "content" in result[0]["source"]

def test_recommend_count_nonpositive_returns_empty(tmp_path):
    store=RatingStore(tmp_path/"ratings.db"); profile=store.create_profile("Empty")
    movies=pd.DataFrame([{"movieId":1,"title":"A","genres":"Drama"}])
    service=RecommendationService(movies,pd.DataFrame(columns=["movieId","rating"]),store)
    assert service.recommend(profile,0)==[]

def test_latest_saved_rating_is_used_to_refresh_als_candidates(tmp_path):
    store=RatingStore(tmp_path/"ratings.db"); profile=store.create_profile("Dynamic")
    movies=pd.DataFrame([
        {"movieId":1,"title":"Rated drama","genres":"Drama"},
        {"movieId":2,"title":"Drama pick","genres":"Drama"},
        {"movieId":3,"title":"Comedy pick","genres":"Comedy"},
    ])
    class RatingAwareModel:
        def __init__(self): self.seen=[]
        def recommend_for_ratings(self,ratings,n):
            value=ratings[0]
            self.seen.append(value)
            return [(1,value),(2,6-value)]
    model=RatingAwareModel()
    service=RecommendationService(movies,pd.DataFrame(columns=["movieId","rating"]),store,
        model=model,movie_to_index={1:0,2:1,3:2})

    store.rate(profile,1,5.)
    first=service.recommend(profile,2)
    store.rate(profile,1,1.)
    refreshed=service.recommend(profile,2)

    assert model.seen==[5.,1.]
    assert first[0]["movie_id"]==2
    assert refreshed[0]["movie_id"]==3
