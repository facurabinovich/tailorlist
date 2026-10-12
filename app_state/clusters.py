"""Streamlit-cached wrappers around core.clustering (KMeans runs and k scoring).

Cache keying (H1 resolved): the frame ``df_all`` is a regular (non-underscore) parameter, so
Streamlit hashes it into the cache key together with the track ids and k. Changing the
data for the same ids and k therefore recomputes instead of returning a stale result.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app_state import collection as _collection
from config import CLUSTER_FEATURES
from core.clustering import k_metrics, kmeans_cluster
from core.tracks import cluster_pool_frame, yc_unmatched_frame


@st.cache_data(show_spinner=False)
def run_kmeans(df_all: pd.DataFrame, track_ids_tuple: tuple, k: int):
    """
    Returns:
        df_clust        — tracks with cluster, cluster_name, PC1, PC2
        name_map        — {int → str}
        centroids_norm  — DataFrame(k × radar_features), StandardScaler space
        var1, var2      — PCA variance explained (%)
        scaler, label1, label2
        descriptions    — {int → descriptive name} when k > 5 (clusters are numbered), else {}
    """
    df_sub = df_all[df_all["track_id"].isin(set(track_ids_tuple))].copy()
    res = kmeans_cluster(df_sub, k)
    return (res.df_clust, res.name_map, res.centroids_scaled, res.var1, res.var2,
            res.scaler, res.label1, res.label2, res.descriptions)


@st.cache_data(show_spinner=False)
def compute_k_metrics(df_all: pd.DataFrame, track_ids_tuple: tuple) -> pd.DataFrame:
    """Cached k_metrics over the tracks in track_ids_tuple (see module note on keying)."""
    df_sub = df_all[df_all["track_id"].isin(set(track_ids_tuple))].copy()
    return k_metrics(df_sub)


# ── Track loading for My Clusters / Cluster Results ──────────────────────────
# Moved from pages/6_My_Clusters.py and pages/_Cluster_Results.py (T18). Both read the
# user's collection from the session (Your Collection); nothing here touches the DB.

def load_data() -> pd.DataFrame:
    """Tracks with audio features to cluster, from the user's collection in the session."""
    # Looked up on the module so patches of app_state.collection.get_tracks apply.
    return cluster_pool_frame(_collection.get_tracks(), CLUSTER_FEATURES)


def _load_unmatched(include_decade: bool = False) -> pd.DataFrame:
    """Tracks without audio features: the skipped + failed ones in the session."""
    return yc_unmatched_frame(
        st.session_state.get("uc_skipped", []),
        st.session_state.get("uc_failed", []),
        include_decade=include_decade,
    )
