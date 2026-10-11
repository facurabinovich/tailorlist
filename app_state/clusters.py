"""Streamlit-cached wrappers around core.clustering (KMeans runs and k scoring).

Cache keying (H1 resolved): the frame ``df_all`` is a regular (non-underscore) parameter, so
Streamlit hashes it into the cache key together with the track ids and k. Changing the
data for the same ids and k therefore recomputes instead of returning a stale result.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app_state import collection as _collection
from app_state.session import MODE_YC
from config import CLUSTER_FEATURES
from core.clustering import k_metrics, kmeans_cluster
from core.tracks import cluster_pool_frame, yc_unmatched_frame
from db.tracks import load_cluster_data, load_unmatched_tracks, load_all_tracks_for_grouping


@st.cache_data(show_spinner=False)
def run_kmeans(df_all: pd.DataFrame, track_ids_tuple: tuple, k: int):
    """
    Returns:
        df_clust        — tracks with cluster, cluster_name, PC1, PC2
        name_map        — {int → str}
        centroids_norm  — DataFrame(k × radar_features), StandardScaler space
        var1, var2      — PCA variance explained (%)
        scaler, label1, label2
    """
    df_sub = df_all[df_all["track_id"].isin(set(track_ids_tuple))].copy()
    res = kmeans_cluster(df_sub, k)
    if res.descriptions:
        # k > 5: clusters are numbered; keep the descriptive names for the results page.
        # Runs on cache miss only, exactly as when this lived inside _make_names.
        st.session_state["cluster_descriptions"] = res.descriptions
    return (res.df_clust, res.name_map, res.centroids_scaled, res.var1, res.var2,
            res.scaler, res.label1, res.label2)


@st.cache_data(show_spinner=False)
def compute_k_metrics(df_all: pd.DataFrame, track_ids_tuple: tuple) -> pd.DataFrame:
    """Cached k_metrics over the tracks in track_ids_tuple (see module note on keying)."""
    df_sub = df_all[df_all["track_id"].isin(set(track_ids_tuple))].copy()
    return k_metrics(df_sub)


# ── Track loading for My Clusters / Cluster Results ──────────────────────────
# Moved from pages/6_My_Clusters.py and pages/_Cluster_Results.py (T18). The Refresh
# button in My Clusters calls .clear() on load_data_fc and load_all_grouping_fc, so those
# two cached objects must stay importable under these names.

@st.cache_data(show_spinner="Loading tracks...", ttl=300)
def load_data_fc() -> pd.DataFrame:
    return load_cluster_data().drop_duplicates(subset="track_id")


@st.cache_data(show_spinner=False, ttl=300)
def load_all_grouping_fc() -> pd.DataFrame:
    """All personal tracks regardless of audio features — cached for preview use."""
    return load_all_tracks_for_grouping()


def load_data(mode: str = "") -> pd.DataFrame:
    """Tracks with audio features to cluster: DB (cached) in Demo mode, session in YC."""
    if mode != MODE_YC:
        return load_data_fc()
    # Looked up on the module so patches of app_state.collection.get_tracks apply.
    return cluster_pool_frame(_collection.get_tracks(), CLUSTER_FEATURES)


@st.cache_data(show_spinner=False)
def _load_unmatched_fc() -> pd.DataFrame:
    return load_unmatched_tracks()


def _load_unmatched(mode: str) -> pd.DataFrame:
    """Tracks without audio features: DB (cached) in Demo mode, skipped + failed in YC."""
    if mode != MODE_YC:
        return _load_unmatched_fc()
    return yc_unmatched_frame(
        st.session_state.get("uc_skipped", []),
        st.session_state.get("uc_failed", []),
    )
