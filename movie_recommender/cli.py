"""Command-line data preparation, ALS training and offline evaluation."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd
from .config import Settings
from .data import build_bundle, download_movielens, load_movielens
from .storage import RatingStore
from .evaluation import error_metrics, evaluate_recommendation_sources

def prepare(settings: Settings):
    if not settings.ratings_path.exists() or not settings.movies_path.exists():
        ratings_path,movies_path=download_movielens(settings.data_dir)
    else:
        ratings_path,movies_path=settings.ratings_path,settings.movies_path
    ratings,movies=load_movielens(ratings_path,movies_path)
    store=RatingStore(settings.database_path)
    store.import_dataset(ratings)
    feedback=store.all_feedback()
    if len(feedback):
        ratings=pd.concat([ratings,feedback],ignore_index=True)
        ratings["userId"]=ratings.userId.astype(str)
        ratings=ratings.sort_values(["timestamp"]).drop_duplicates(["userId","movieId"],keep="last").reset_index(drop=True)
    bundle=build_bundle(ratings,movies)
    settings.artifact_dir.mkdir(parents=True,exist_ok=True)
    for name,frame in (("train",bundle.train),("validation",bundle.validation),("test",bundle.test)):
        frame.to_csv(settings.artifact_dir/f"{name}.csv",index=False)
    ratings.to_csv(settings.artifact_dir/"ratings_clean.csv",index=False)
    movies.to_csv(settings.artifact_dir/"movies.csv",index=False)
    return ratings,movies,bundle,store

def main():
    parser=argparse.ArgumentParser(description="ALS movie recommender pipeline")
    parser.add_argument("command",choices=["prepare","train","evaluate"])
    defaults=Settings.from_env()
    parser.add_argument("--rank",type=int,default=defaults.rank)
    parser.add_argument("--max-iter",type=int,default=defaults.max_iter)
    parser.add_argument("--reg-param",type=float,default=defaults.reg_param)
    parser.add_argument("--seed",type=int,default=defaults.seed)
    parser.add_argument("--relevance-threshold",type=float,default=defaults.relevance_threshold)
    parser.add_argument("--als-weight",type=float,default=defaults.als_weight)
    parser.add_argument("--content-weight",type=float,default=defaults.content_weight)
    parser.add_argument("--popularity-weight",type=float,default=defaults.popularity_weight)
    parser.add_argument("--data-dir",type=Path,default=defaults.data_dir)
    parser.add_argument("--artifact-dir",type=Path,default=defaults.artifact_dir)
    parser.add_argument("--database",type=Path,default=defaults.database_path)
    args=parser.parse_args()
    settings=Settings(data_dir=args.data_dir,artifact_dir=args.artifact_dir,database_path=args.database,
        rank=args.rank,max_iter=args.max_iter,reg_param=args.reg_param,seed=args.seed,
        relevance_threshold=args.relevance_threshold,als_weight=args.als_weight,
        content_weight=args.content_weight,popularity_weight=args.popularity_weight)
    ratings,movies,bundle,store=prepare(settings)
    if args.command=="prepare":
        print(f"Prepared {len(ratings):,} ratings and {len(movies):,} movies")
        return
    from .model import train_als, load_als_model
    bundle_path=settings.artifact_dir/"models"
    artifact,version,_,config,val_rmse=train_als(bundle.train,bundle.validation,settings,bundle_path,bundle)
    metrics={"validation_rmse":val_rmse,"relevance_threshold":settings.relevance_threshold}
    # Rating errors are computed once using a freshly loaded model on held-out test data.
    if args.command=="evaluate" and len(bundle.test):
        model=load_als_model(artifact)
        prediction=model.predict_frame(bundle.test)
        metrics.update({f"test_{k}":v for k,v in error_metrics(prediction.rating,prediction.prediction).items()})
        user_ids=sorted(bundle.test.loc[bundle.test.rating>=settings.relevance_threshold,"userIndex"].astype(int).unique().tolist())
        index_to_movie={int(index):int(movie_id) for movie_id,index in bundle.movie_to_index.items()}
        als_candidates={int(user):{index_to_movie[int(item)]:float(score)
            for item,score in model.recommend_for_user(int(user),200) if int(item) in index_to_movie}
            for user in user_ids}
        eval_weights=(config["als_weight"],config["content_weight"],config["popularity_weight"])
        metrics["ranking_at_10"]=evaluate_recommendation_sources(bundle,movies,als_candidates,
            settings.relevance_threshold,10,eval_weights)
    metrics["ranking_note"]="Held-out test relevance uses the configured rating threshold; ranking metrics are reported at K=10."
    (artifact/"metrics.json").write_text(json.dumps(metrics,indent=2,allow_nan=True),encoding="utf-8")
    store.record_model(version,str(artifact),metrics,config)
    print(json.dumps({"version":version,"artifact_dir":str(artifact),"metrics":metrics},indent=2,allow_nan=True))

if __name__=="__main__":
    main()
