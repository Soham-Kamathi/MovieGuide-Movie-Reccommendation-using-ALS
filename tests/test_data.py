import pandas as pd
import pytest
import ssl
import urllib.error
from movie_recommender import data as movie_data
from movie_recommender.data import build_bundle, chronological_split, load_movielens

def test_duplicate_rating_uses_latest_and_invalid_rating_is_removed(tmp_path):
    ratings=pd.DataFrame([
        {"userId":1,"movieId":10,"rating":3.0,"timestamp":1},
        {"userId":1,"movieId":10,"rating":4.5,"timestamp":2},
        {"userId":1,"movieId":11,"rating":9.0,"timestamp":3},
        {"userId":None,"movieId":12,"rating":4.0,"timestamp":4},
        {"userId":1.5,"movieId":13,"rating":4.0,"timestamp":5},
    ])
    movies=pd.DataFrame([{"movieId":10,"title":"A","genres":"Drama"},{"movieId":11,"title":"B","genres":None}])
    rp,mp=tmp_path/"ratings.csv",tmp_path/"movies.csv"
    ratings.to_csv(rp,index=False); movies.to_csv(mp,index=False)
    clean,movie_data=load_movielens(rp,mp)
    assert len(clean)==1
    assert clean.iloc[0].rating==4.5
    assert movie_data.loc[movie_data.movieId==11,"genres"].iloc[0]==""

def test_chronological_split_is_repeatable_and_keeps_short_users_in_train():
    ratings=pd.DataFrame([
        {"userId":1,"movieId":i,"rating":float(i),"timestamp":i} for i in range(1,5)
    ]+[{"userId":2,"movieId":9,"rating":4.,"timestamp":1}])
    train,val,test=chronological_split(ratings)
    assert train[train.userId==1].movieId.tolist()==[1,2]
    assert val["movieId"].tolist()==[3]
    assert test.sort_values("userId").movieId.tolist()==[4]

def test_build_bundle_mapping_round_trips_external_ids():
    ratings=pd.DataFrame([{"userId":5,"movieId":12,"rating":4.,"timestamp":1}])
    movies=pd.DataFrame([{"movieId":12,"title":"Movie","genres":"Drama"},{"movieId":20,"title":"Other","genres":"Comedy"}])
    bundle=build_bundle(ratings,movies)
    assert bundle.user_to_index["5"]==int(bundle.train.iloc[0].userIndex)
    assert bundle.movie_to_index["12"]==int(bundle.train.iloc[0].movieIndex)
    assert "20" in bundle.movie_to_index

def test_bundle_frames_have_no_recursive_pandas_attrs():
    ratings=pd.DataFrame([
        {"userId":1,"movieId":1,"rating":4.,"timestamp":1},
        {"userId":1,"movieId":2,"rating":5.,"timestamp":2},
        {"userId":1,"movieId":3,"rating":3.,"timestamp":3},
    ])
    movies=pd.DataFrame([{"movieId":i,"title":str(i),"genres":"Drama"} for i in [1,2,3]])
    bundle=build_bundle(ratings,movies)
    assert bundle.train.attrs=={}
    merged=pd.concat([bundle.train,bundle.validation],ignore_index=True)
    assert len(merged)==2

def test_missing_required_columns_raise_value_error(tmp_path):
    rp,mp=tmp_path/"r.csv",tmp_path/"m.csv"
    pd.DataFrame({"userId":[1]}).to_csv(rp,index=False)
    pd.DataFrame({"movieId":[1],"title":["A"],"genres":["Drama"]}).to_csv(mp,index=False)
    with pytest.raises(ValueError,match="missing required columns"):
        load_movielens(rp,mp)

def test_download_reports_certificate_error_and_keeps_verification_enabled(tmp_path,monkeypatch):
    def fail(*args,**kwargs):
        raise urllib.error.URLError(ssl.SSLCertVerificationError("untrusted issuer"))
    monkeypatch.setattr(movie_data.urllib.request,"urlopen",fail)
    context=movie_data._https_context()
    assert context.verify_mode==ssl.CERT_REQUIRED
    with pytest.raises(RuntimeError,match="failed certificate verification"):
        movie_data.download_movielens(tmp_path/"ml-latest-small")
