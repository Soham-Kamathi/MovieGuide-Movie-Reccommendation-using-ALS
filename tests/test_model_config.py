import pandas as pd

def test_native_als_model_round_trip_and_prediction(tmp_path):
    from movie_recommender.model import _fit_als, load_als_model

    frame = pd.DataFrame({
        "userIndex": [0, 0, 1, 1, 2, 2],
        "movieIndex": [0, 1, 1, 2, 0, 2],
        "rating": [4., 3., 5., 2., 4., 3.],
    })
    model = _fit_als(frame, 3, 3, rank=2, max_iter=3, reg_param=.1, seed=42)
    path = tmp_path / "als_model.npz"
    model.save(path)
    loaded = load_als_model(tmp_path)

    assert loaded.predict(0, 0) == model.predict(0, 0)
    assert len(loaded.recommend_for_user(0, 3)) == 3
    assert all(.5 <= score <= 5.0 for _, score in loaded.recommend_for_user(0, 3))

def test_current_ratings_change_inferred_als_recommendations():
    import numpy as np
    from movie_recommender.model import ExplicitALSModel

    model=ExplicitALSModel(
        user_factors=np.zeros((1,1)),
        item_factors=np.array([[1.],[1.],[-1.]]),
        global_mean=3.,user_bias=np.zeros(1),item_bias=np.zeros(3),
    )
    liked=model.recommend_for_ratings({0:5.},n=2)
    disliked=model.recommend_for_ratings({0:1.},n=2)

    assert liked[0][0]==1
    assert disliked[0][0]==2
