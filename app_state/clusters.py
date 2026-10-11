"""Streamlit-cached wrappers around core.clustering (KMeans runs and k scoring).

Cache keying (H1 resolved): the frame ``df_all`` is a regular (non-underscore) parameter, so
Streamlit hashes it into the cache key together with the track ids and k. Changing the
data for the same ids and k therefore recomputes instead of returning a stale result.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.clustering import k_metrics, kmeans_cluster


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
