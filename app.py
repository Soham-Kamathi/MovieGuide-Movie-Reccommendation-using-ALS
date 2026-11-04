from __future__ import annotations
import json
from pathlib import Path
from urllib.parse import quote_plus
import pandas as pd
import streamlit as st
from movie_recommender.config import Settings
from movie_recommender.data import load_movielens
from movie_recommender.service import RecommendationService
from movie_recommender.storage import RatingStore

st.set_page_config(page_title="MovieGuide", page_icon="🎬", layout="wide")
settings=Settings.from_env()
store=RatingStore(settings.database_path)

def movie_links(title: str) -> tuple[str, str]:
    imdb_query=quote_plus(f"{title} movie")
    trailer_query=quote_plus(f"{title} movie trailer")
    return (f"https://www.imdb.com/find/?q={imdb_query}",
            f"https://www.youtube.com/results?search_query={trailer_query}")

@st.cache_data(show_spinner=False)
def load_catalog(ratings_path,movies_path):
    return load_movielens(Path(ratings_path),Path(movies_path))

st.title("🎬 MovieGuide")
st.caption("A personal movie discovery prototype powered by collaborative filtering")
if not settings.ratings_path.exists() or not settings.movies_path.exists():
    st.warning("MovieLens data is not prepared. From the project folder, run `python -m movie_recommender.cli prepare`.")
    st.stop()
ratings,movies=load_catalog(str(settings.ratings_path),str(settings.movies_path))
profiles=store.list_profiles()
with st.sidebar:
    st.header("Your profile")
    selected_id=st.selectbox("Choose a local profile",[p["profile_id"] for p in profiles],
        format_func=lambda pid:next(p["display_name"] for p in profiles if p["profile_id"]==pid)) if profiles else None
    with st.form("create_profile"):
        profile_name=st.text_input("Create a pseudonymous profile",placeholder="e.g. Movie fan")
        seed_user=st.checkbox("Start with a sample MovieLens user's ratings")
        sample_user=st.selectbox("Sample profile",sorted(ratings.userId.unique())[:30],disabled=not seed_user)
        create=st.form_submit_button("Create profile",use_container_width=True)
    if create:
        try:
            store.create_profile(profile_name,int(sample_user) if seed_user else None)
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    if selected_id:
        st.caption(f"{len(store.rated_movie_ids(selected_id))} movies rated")

if not profiles or selected_id is None:
    st.info("Create a local profile to start rating movies and building recommendations.")
    st.stop()

artifact=store.latest_model(); model=None; user_mapping={}; movie_mapping={}
active_weights=(settings.als_weight,settings.content_weight,settings.popularity_weight)
if artifact:
    try:
        from movie_recommender.model import load_als_model
        model=load_als_model(Path(artifact["artifact_path"]))
        mapping_path=Path(artifact["artifact_path"])/"mappings.json"
        if mapping_path.exists():
            mappings=json.loads(mapping_path.read_text(encoding="utf-8"))
            user_mapping=mappings.get("user_to_index",{}); movie_mapping=mappings.get("movie_to_index",{})
        model_config=json.loads((Path(artifact["artifact_path"])/"config.json").read_text(encoding="utf-8"))
        active_weights=(model_config.get("als_weight",active_weights[0]),
                        model_config.get("content_weight",active_weights[1]),
                        model_config.get("popularity_weight",active_weights[2]))
    except Exception as exc:
        st.sidebar.warning(f"Saved ALS model is unavailable: {exc}")

service=RecommendationService(movies,ratings,store,model,user_mapping,movie_mapping,
    *active_weights)
tab_recs,tab_browse,tab_about=st.tabs(["For you","Browse and rate","Model notes"])
with tab_recs:
    col_a,col_b,col_c=st.columns([3,1,1.5])
    with col_a: st.subheader("Picked for your next movie night")
    with col_b: count=st.selectbox("Show",[5,10,15,20],index=1)
    with col_c:
        refresh_requested=st.button("Refresh recommendations",use_container_width=True)
    recommendations=service.recommend(selected_id,count)
    if refresh_requested: st.toast("Recommendations updated from your saved ratings.")
    if not store.rated_movie_ids(selected_id):
        st.info("Showing popular picks. Rate movies to get recommendations shaped by your taste.")
    elif not model:
        st.info("Using genre similarity and popularity until the next ALS batch training run.")
    if recommendations:
        for start in range(0,len(recommendations),2):
            columns=st.columns(2)
            for col,item in zip(columns,recommendations[start:start+2]):
                with col:
                    imdb_url,trailer_url=movie_links(item["title"])
                    movie=movies[movies.movieId==item["movie_id"]].iloc[0]
                    with st.container(border=True):
                        st.markdown(f"### [{item['title']}]({imdb_url})")
                        genres=str(movie.genres).replace("|", " / ")
                        st.caption(genres or "Genres unavailable")
                        st.markdown(f"[IMDb]({imdb_url})  |  [YouTube trailer]({trailer_url})")
                        st.caption(f"{item['source']} recommendation  |  Match {item['score']:.2f}")
    else: st.info("No eligible recommendations are available yet.")

with tab_browse:
    st.subheader("Find a movie and save your rating")
    browse=movies.copy()
    browse["_year"]=pd.to_numeric(browse.title.str.extract(r"\((\d{4})\)\s*$",expand=False),errors="coerce")
    browse["_genres"]=browse.genres.fillna("").map(lambda value:[g for g in str(value).split("|") if g and g!="(no genres listed)"])
    popularity=ratings.groupby("movieId").size()
    browse["_rating_count"]=browse.movieId.map(popularity).fillna(0).astype(int)
    profile_ratings=store.ratings_for_profile(selected_id)
    rated_ids=set(profile_ratings.movieId.astype(int))
    all_genres=sorted({genre for values in browse["_genres"] for genre in values})
    years=browse["_year"].dropna().astype(int)

    query=st.text_input("Search movies",placeholder="Try a title, genre, or year (e.g. Toy Story, Comedy, 1995)",
                        help="Search matches movie titles, genres, and release years.")
    filter_cols=st.columns([2,2,2,1])
    with filter_cols[0]: selected_genres=st.multiselect("Genres",all_genres,placeholder="Any genre")
    with filter_cols[1]:
        if len(years):
            year_range=st.slider("Release year",int(years.min()),int(years.max()),
                                 (int(years.min()),int(years.max())))
        else: year_range=None
    with filter_cols[2]: rating_filter=st.selectbox("Your ratings",["All movies","Not rated yet","Already rated"])
    with filter_cols[3]: page_size=st.selectbox("Per page",[10,20,40],index=1)
    include_unknown_year=st.checkbox("Include movies with unknown year",value=True)

    subset=browse
    if query.strip():
        terms=[term.casefold() for term in query.split() if term]
        searchable=(browse.title.fillna("").astype(str)+" "+browse.genres.fillna("").astype(str)+" "+
                    browse["_year"].fillna("").astype(str)).str.casefold()
        matches=pd.Series(True,index=browse.index)
        for term in terms: matches &= searchable.str.contains(term,regex=False)
        subset=subset[matches]
    if selected_genres:
        selected=set(selected_genres)
        subset=subset[subset["_genres"].map(lambda values:bool(selected.intersection(values)))]
    if year_range is not None:
        year_mask=subset["_year"].between(year_range[0],year_range[1])
        if include_unknown_year: year_mask |= subset["_year"].isna()
        subset=subset[year_mask]
    if rating_filter=="Not rated yet": subset=subset[~subset.movieId.astype(int).isin(rated_ids)]
    elif rating_filter=="Already rated": subset=subset[subset.movieId.astype(int).isin(rated_ids)]

    sort_options=["Best match","Most rated","Title A-Z","Newest first"]
    sort_default=0 if query.strip() else 1
    sort_by=st.selectbox("Sort results",sort_options,index=sort_default)
    if sort_by=="Best match" and query.strip():
        normalized=query.strip().casefold()
        title=subset.title.fillna("").astype(str).str.casefold()
        subset=subset.assign(_match=0)
        subset.loc[title!=normalized,"_match"]=1
        subset.loc[~title.str.startswith(normalized),"_match"]=2
        subset=subset.sort_values(["_match","_rating_count","title"],ascending=[True,False,True],kind="stable")
    elif sort_by=="Title A-Z": subset=subset.sort_values("title",kind="stable")
    elif sort_by=="Newest first": subset=subset.sort_values(["_year","title"],ascending=[False,True],na_position="last",kind="stable")
    else: subset=subset.sort_values(["_rating_count","title"],ascending=[False,True],kind="stable")

    result_count=len(subset)
    total_pages=max(1,(result_count+page_size-1)//page_size)
    if st.session_state.get("movie_browser_page",1)>total_pages: st.session_state.movie_browser_page=1
    page=st.number_input("Page",min_value=1,max_value=total_pages,step=1,key="movie_browser_page",
                         help=f"Page 1 of {total_pages}")
    start=(int(page)-1)*page_size
    visible=subset.iloc[start:start+page_size]
    visible_records=list(visible.iterrows())
    st.caption(f"Showing {start+1 if result_count else 0}-{min(start+page_size,result_count)} of {result_count:,} matching movies")
    if visible.empty:
        st.info("No movies match these filters. Try a broader search or clear a filter.")

    profile_rating_map={int(row.movieId):float(row.rating) for row in profile_ratings.itertuples()}
    for _,movie in visible_records:
        with st.container(border=True):
            c1,c2,c3=st.columns([5,3,2])
            with c1:
                year=f" ({int(movie['_year'])})" if pd.notna(movie["_year"]) else ""
                votes=f" | {int(movie['_rating_count']):,} MovieLens ratings" if movie["_rating_count"] else ""
                imdb_url,trailer_url=movie_links(str(movie.title))
                st.markdown(f"#### [{movie.title}{year}]({imdb_url})")
                st.caption(f"{str(movie.genres).replace('|',' / ')}{votes}")
                st.markdown(f"[IMDb]({imdb_url})  |  [YouTube trailer]({trailer_url})")
            default=profile_rating_map.get(int(movie.movieId),3.0)
            with c2:
                value=st.select_slider(f"Rating for {movie.title}",options=[.5,1.,1.5,2.,2.5,3.,3.5,4.,4.5,5.],value=default,key=f"rating-{movie.movieId}",label_visibility="collapsed")
            with c3:
                if st.button("Save rating",key=f"save-{movie.movieId}"):
                    store.rate(selected_id,int(movie.movieId),value); st.success("Rating saved"); st.rerun()

with tab_about:
    st.subheader("How recommendations work")
    st.markdown("""
    - **ALS** learns user and movie factors from explicit MovieLens ratings.
    - **Genre similarity** helps profiles that have ratings but no trained ALS factors.
    - **Popularity** gives new profiles a useful starting list.
    - Ratings are stored locally in SQLite. ALS retraining is a batch operation.
    """)
    st.write("Active saved model:",artifact["model_version"] if artifact else "No trained model")
    if artifact: st.json(json.loads(artifact["metrics_json"]))
    st.code("python -m movie_recommender.cli train\nstreamlit run app.py",language="powershell")



