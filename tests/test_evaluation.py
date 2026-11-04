import pandas as pd
from movie_recommender.evaluation import error_metrics, ranking_metrics

def test_error_metrics_ignore_nan_predictions():
    metrics=error_metrics([3,4,2],[2,float("nan"),3])
    assert metrics["mae"]==1.0
    assert metrics["rmse"]==1.0

def test_ranking_metrics_and_catalog_coverage():
    result=ranking_metrics({1:[10,11]},{1:{11}},2,{10,11,12})
    assert result["precision_at_k"]==0.5
    assert result["recall_at_k"]==1.0
    assert result["catalog_coverage"]==2/3
