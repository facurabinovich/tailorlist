import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import pickle
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from config import (
    KMEANS_PATH, KMEANS_SCALER_PATH,
    CLUSTER_NAMES, CLUSTER_COLORS, CLUSTER_FEATURES,
)
from app_state.clusters import run_kmeans, compute_k_metrics, load_data, _load_unmatched
from core.clustering import (
    verbose_description as _verbose_description,
    best_k as _best_k,
)
from core.grouping import (
    group_by_category as run_category_grouping,
    group_by_specific_genres as run_specific_genre_grouping,
)
from config import is_dev_mode
from datetime import datetime
from ui.components import section_title
from ui.export import render_export_to_spotify
from ui.theme import inject_global_css, spotify_icon_html, page_brand_html
from ui.nav import inject_sidebar_nav, check_collection_mode
from ui.components import cluster_card, info_box, hr

# Pages never import each other: logic shared with _Cluster_Results.py lives in core/ and app_state/.
# (Cluster Results does not import from this page.)

inject_global_css()
inject_sidebar_nav("My Clusters")

if st.session_state.pop("_start_fresh", False):
    for _key in [
        "clustering_results", "clusters_pl_filter_yc",
        "clusters_decade_filter_yc",
        "clusters_genre_filter_yc",
        "selected_genres", "_prev_genre_families", "_prev_sgl_families",
        "grouping_mode", "k_mode", "k_manual_slider",
        "group_by_decade", "group_by_genre", "keep_visible",
        "specific_cluster_genres", "specific_genre_decade", "grouping_dim_choice",
        "_unmatched_done_ids", "_total_assigned_count",
    ]:
        st.session_state.pop(_key, None)
from app_state.progress import load_cluster_progress, save_cluster_progress, reset_cluster_progress
user_key = st.session_state.get("uc_session_id", "anonymous")

_progress = {}
try:
    _progress = load_cluster_progress(user_key)
    # If the user explicitly reset YC progress, treat DB as empty regardless of
    # what it says — the DB DELETE may have failed silently, but we honour the reset.
    if user_key != "facu" and st.session_state.get("_uc_progress_cleared"):
        _progress = {}
    if "done_tracks" not in st.session_state:
        st.session_state["done_tracks"] = {
            tid for tid, p in _progress.items() if p["status"] == "done"
        }
    if "unmatched_assignments" not in st.session_state:
        st.session_state["unmatched_assignments"] = {
            tid: p["cluster_name"]
            for tid, p in _progress.items()
            if p["status"] == "manual" and p["cluster_name"]
        }
    if "_unmatched_done_ids" not in st.session_state:
        st.session_state["_unmatched_done_ids"] = {
            tid for tid, p in _progress.items()
            if p["status"] == "manual" and p["cluster_name"]
        }
except Exception:
    if "done_tracks" not in st.session_state:
        st.session_state["done_tracks"] = set()
    if "unmatched_assignments" not in st.session_state:
        st.session_state["unmatched_assignments"] = {}
    if "_unmatched_done_ids" not in st.session_state:
        st.session_state["_unmatched_done_ids"] = set()

if not check_collection_mode():
    st.stop()

# ── Constants ─────────────────────────────────────────────────────────────────
# High-contrast palette for dynamic k — index maps to cluster int
_DYN_PALETTE = [
    "#1DB954",  # 0 green
    "#E8534A",  # 1 coral
    "#4A90D9",  # 2 blue
    "#F5A623",  # 3 amber
    "#B97FE8",  # 4 purple
    "#E8D44A",  # 5 yellow
    "#4AE8D4",  # 6 teal
    "#E84A90",  # 7 pink
    "#A8E84A",  # 8 lime
    "#E8934A",  # 9 orange
]

# Features to use in the radar — exclude tempo (BPM scale distorts radar)
_RADAR_FEATURES = [f for f in CLUSTER_FEATURES if f != "tempo"]

from core.genres import (
    GENRE_FAMILIES,
    assign_family as _assign_family,
    track_matches_families as _track_matches_families,
    preview_filter as _preview_filter,
)

from ui.charts import BASE_LAYOUT as _BASE_LAYOUT

# ── HTML helpers ──────────────────────────────────────────────────────────────
def kpi_card(icon: str, label: str, value: str, sub: str = "") -> str:
    sub_html = (
        "<div style='color:#B3B3B3;font-size:0.78rem;margin-top:4px;'>"
        + sub + "</div>"
    ) if sub else ""
    return "".join([
        "<div style='background:#282828;border-radius:14px;padding:22px 24px;",
        "border:1px solid #333;height:100%;'>",
        "<div style='font-size:1.6rem;margin-bottom:8px;'>" + icon + "</div>",
        "<div style='color:#B3B3B3;font-size:0.78rem;letter-spacing:0.04em;'>" + label + "</div>",
        "<div style='color:#FFFFFF;font-size:1.5rem;font-weight:800;margin-top:4px;'>",
        value + "</div>",
        sub_html,
        "</div>",
    ])


# ── Data & model loading ──────────────────────────────────────────────────────
# Clear stale playlist selection on the first visit of the session
if not st.session_state.get("_clusters_initialized"):
    st.session_state["_clusters_initialized"] = True
    st.session_state.pop("clusters_pl_filter_yc", None)
    st.session_state.pop("clustering_results", None)
    st.session_state.pop("selected_genres", None)
    st.session_state.pop("phase1", None)
    st.session_state.pop("clusters_decade_filter_yc", None)
    st.session_state.pop("clusters_genre_filter_yc", None)
    st.session_state.pop("_prev_genre_families", None)
    st.session_state.pop("_prev_sgl_families", None)
    st.session_state.pop("k_mode", None)
    st.session_state.pop("k_manual_slider", None)
    st.session_state.pop("run_clustering_btn", None)
    st.session_state.pop("unmatched_assignments", None)
    st.session_state.pop("unmatched_save_status", None)
    st.session_state.pop("_unmatched_done_ids", None)
    st.session_state.pop("_total_assigned_count", None)
    st.session_state.pop("group_by_decade", None)
    st.session_state.pop("group_by_genre", None)
    st.session_state.pop("specific_cluster_genres", None)
    st.session_state.pop("specific_genre_decade", None)
    st.session_state.pop("grouping_dim_choice", None)
    # Reload progress fresh — avoids first-visit count discrepancy caused by
    # load_cluster_progress running before this first-visit clear.
    # Exception: if the user just reset progress for this user_key, keep it empty
    # regardless of what the DB says (DELETE may have failed silently).
    # _progress is already empty if _uc_progress_cleared is set (see above)
    st.session_state.pop("done_tracks", None)
    st.session_state["done_tracks"] = {
        tid for tid, p in _progress.items() if p["status"] == "done"
    }
    _manual_ids_fresh = {
        tid for tid, p in _progress.items()
        if p["status"] == "manual" and p["cluster_name"]
    }
    st.session_state["unmatched_assignments"] = {
        tid: p["cluster_name"] for tid, p in _progress.items()
        if p["status"] == "manual" and p["cluster_name"]
    }
    st.session_state["_unmatched_done_ids"] = _manual_ids_fresh

df_all = load_data()

# Full YC pool = enriched (df_all) + non-enriched; decade feeds the category grouping.
_yc_ne = _load_unmatched(include_decade=True)
# Remove tracks that succeeded enrichment in another playlist — they're already
# in df_all and will be clustered; showing them in Unmatched too would be confusing.
if not _yc_ne.empty and not df_all.empty:
    _yc_ne = _yc_ne[~_yc_ne["track_id"].isin(set(df_all["track_id"]))]
_df_all_full = (
    pd.concat([df_all, _yc_ne], ignore_index=True).drop_duplicates(subset="track_id")
    if not _yc_ne.empty else df_all
)
# Total cross-playlist duplicates = raw processed entries minus unique real track_ids
_n_unique_all = _df_all_full["track_id"].nunique()
_yc_cross_dupes_total = max(0, (len(st.session_state.get("uc_enriched", [])) +
                                len(st.session_state.get("uc_skipped", [])) +
                                len(st.session_state.get("uc_failed", []))) - _n_unique_all)
# Keep per-pool counts for the unmatched note
_yc_enriched_cross_dupes   = max(0, len(st.session_state.get("uc_enriched", [])) - df_all["track_id"].nunique())
_yc_unenriched_cross_dupes = max(0, _yc_cross_dupes_total - _yc_enriched_cross_dupes)

# Compute active (non-done) pools for filter options
_done_set_for_opts = st.session_state.get("done_tracks", set())
if _done_set_for_opts:
    # For playlists use the full track pool so a playlist with only non-enriched tracks
    # isn't prematurely hidden after some of its enriched tracks get marked done
    _pool_pl = _df_all_full[~_df_all_full["track_id"].isin(_done_set_for_opts)]
    _df_for_opts = df_all[~df_all["track_id"].isin(_done_set_for_opts)]
else:
    _pool_pl = _df_all_full  # all playlists visible
    _df_for_opts = df_all

all_playlists = sorted(_pool_pl["playlist_name"].unique().tolist())

# Compute total collection size once — used by progress bar and no-features note
try:
    # Use unique track count (not raw list lengths) so cross-playlist duplicates
    # don't inflate the denominator and prevent reaching 100%.
    _total_collection_size = _n_unique_all
except Exception:
    _total_collection_size = len(df_all)

_pl_key = "clusters_pl_filter_yc"
_stored_playlists = st.session_state.get(_pl_key, [])
if any(p not in all_playlists for p in _stored_playlists):
    st.session_state.pop(_pl_key, None)
    st.session_state.pop("clustering_results", None)

# Pre-populate from last run if available
_last_results = st.session_state.get("clustering_results", {})
_last_playlists = _last_results.get("selected_playlists", all_playlists)
_last_decades = _last_results.get("selected_decades", [])
_last_families = _last_results.get("selected_families", [])
_last_grouping = _last_results.get("grouping_mode", "🔬 By audio similarity (KMeans)")
_last_group_by_decade = _last_results.get("group_by_decade", True)
_last_group_by_genre = _last_results.get("group_by_genre", True)
_last_k_mode = _last_results.get("k_mode", "Auto")
_last_k = _last_results.get("optimal_k", 4)

# ════════════════════════════════════════════════════════════════════════════
# HEADER
# ════════════════════════════════════════════════════════════════════════════
st.markdown(page_brand_html(), unsafe_allow_html=True)
st.markdown(
    f"<div style='display:flex;align-items:center;gap:14px;margin-bottom:4px;'>"
    f"{spotify_icon_html(36)}"
    f"<h1 style='margin:0;'>My Clusters</h1>"
    f"</div>"
    f"<p style='color:#B3B3B3;font-size:0.9rem;margin-top:4px;margin-bottom:0;'>"
    f"Explore how your music groups by audio fingerprint. "
    f"Adjust playlists and K — charts update in real time."
    f"</p>",
    unsafe_allow_html=True,
)
hr(top=16, bottom=20)

# ════════════════════════════════════════════════════════════════════════════
# Active collection banner
# ════════════════════════════════════════════════════════════════════════════
_intra_dupes = 0  # intra-playlist duplicates dropped by enrichment pipeline
uc_enriched = st.session_state.get("uc_enriched", [])
n_with_features = len(uc_enriched)
n_missing = (
    len(st.session_state.get("uc_skipped", []))
    + len(st.session_state.get("uc_failed", []))
)
n_total = n_with_features + n_missing
n_playlists = df_all["playlist_name"].nunique() if not df_all.empty else 0

# Total raw Spotify entries (sum of playlist track_counts) — may exceed n_total
# when a track appears twice in the same playlist (intra-playlist duplicate),
# which the enrichment pipeline deduplicates silently.
_uc_playlists = st.session_state.get("uc_playlists", [])
_spotify_total = sum(pl.get("track_count", 0) for pl in _uc_playlists)
_intra_dupes = max(0, _spotify_total - n_total)

_n_unique_enriched    = df_all["track_id"].nunique()
_n_unique_unenriched  = _n_unique_all - _n_unique_enriched

# Build combined dupe note covering both intra- and cross-playlist duplicates
_dupe_parts = []
if _yc_cross_dupes_total > 0:
    _dupe_parts.append(f"{_yc_cross_dupes_total} across multiple playlists")
if _intra_dupes > 0:
    _dupe_parts.append(f"{_intra_dupes} within the same playlist")
_total_banner_dupes = _yc_cross_dupes_total + _intra_dupes
_dupe_note = (
    f" · {_total_banner_dupes} duplicate(s) not counted ({' · '.join(_dupe_parts)})"
    if _dupe_parts else ""
)

if n_missing > 0:
    st.warning(
        f"🎵 **Your Collection** — your {_spotify_total:,} tracks across {n_playlists} playlist(s): "
        f"**{_n_unique_enriched} unique** have audio features and will appear in the clusters · "
        f"**{_n_unique_unenriched} unique could not be enriched** (API lookup failed or track not found) "
        f"and are excluded from clustering — you can manually assign these below."
        + (_dupe_note and f" **{_dupe_note.lstrip(' · ')}.**")
    )
else:
    st.info(
        f"🎵 **Your Collection** — {_spotify_total:,} tracks across {n_playlists} playlist(s) · "
        f"all {_n_unique_enriched} unique successfully enriched."
        + _dupe_note
    )
st.markdown(
    "<div style='display:flex;gap:0;margin-bottom:8px;'>"
    + "".join([
        f"<div style='flex:1;background:#1a1a1a;border:1px solid #333;"
        f"border-radius:{'10px 0 0 10px' if i==0 else ('0 10px 10px 0' if i==3 else '0')};"
        f"padding:10px 16px;text-align:center;'>"
        f"<span style='color:#1DB954;font-weight:800;font-size:1rem;'>{'①②③④'[i]}</span>"
        f"<span style='color:#B3B3B3;font-size:0.82rem;margin-left:8px;'>{label}</span>"
        f"</div>"
        for i, label in enumerate([
            "Filter playlists, decades & genres",
            "Run Clustering",
            "Explore & refine genres",
            "Export clusters to Spotify",
        ])
    ])
    + "</div>",
    unsafe_allow_html=True,
)

# ════════════════════════════════════════════════════════════════════════════
# CONFIGURE
# ════════════════════════════════════════════════════════════════════════════
_done_tracks = st.session_state.get("done_tracks", set())
# Supplement session state with DB — session state can be incomplete after navigation
_done_tracks = _done_tracks | {tid for tid, p in _progress.items() if p["status"] == "done"}
# Manually assigned unmatched tracks (status="manual") are also "handled" — include in progress
_manual_assigned_ids = (
    (
        st.session_state.get("_unmatched_done_ids", set())
        | {tid for tid, p in _progress.items() if p["status"] == "manual" and p["cluster_name"]}
    ) or {
        tid for tid, cname in st.session_state.get("unmatched_assignments", {}).items()
        if cname and cname != "— unassigned —"
    }
)
_handled_ids = _done_tracks | _manual_assigned_ids
if _done_tracks:
    _n_done = min(len(_handled_ids), _total_collection_size)
    _total_tracks = _total_collection_size

    _pct = _n_done / _total_tracks * 100 if _total_tracks else 0
    _remaining = max(0, _total_tracks - _n_done)

    if _remaining == 0:
        st.markdown(
            "<div style='background:#1a2e1a;border:2px solid #1DB954;border-radius:20px;"
            "padding:48px 32px;margin-bottom:24px;text-align:center;'>"
            "<div style='font-size:4rem;margin-bottom:16px;'>🎉</div>"
            "<p style='color:#1DB954;font-weight:800;font-size:1.7rem;margin:0 0 12px;'>"
            "Congratulations!</p>"
            "<p style='color:#FFFFFF;font-size:1.1rem;font-weight:600;margin:0 0 10px;'>"
            "You've reorganized your whole collection.</p>"
            f"<p style='color:#B3B3B3;font-size:0.92rem;margin:0;'>"
            f"{_total_tracks - st.session_state.get('_skipped_count', 0):,} tracks exported across all clusters"
            + (f" · {st.session_state.get('_skipped_count', 0):,} skipped" if st.session_state.get("_skipped_count", 0) > 0 else "")
            + "</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        if st.button(
            "🔄 Reset all progress",
            key="restore_done_progress",
            help="Clears all exported and manually assigned tracks — brings everything back into future clustering runs",
            type="secondary",
            use_container_width=True,
        ):
            if not reset_cluster_progress(user_key):
                st.toast("⚠️ Could not fully clear DB progress — reset saved as timestamp.", icon="🚨")
            st.session_state["done_tracks"] = set()
            st.session_state["unmatched_assignments"] = {}
            st.session_state.pop("_unmatched_done_ids", None)
            st.session_state.pop("_skipped_count", None)
            st.session_state["_uc_progress_cleared"] = True
            st.rerun()
        st.stop()

    st.markdown(
        f"<div style='background:#1a1a1a;border:1px solid #1DB954;border-radius:12px;"
        f"padding:16px 20px;margin-bottom:20px;'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;"
        f"margin-bottom:10px;'>"
        f"<span style='color:#FFFFFF;font-weight:700;font-size:0.95rem;'>"
        f"📦 Export Progress</span>"
        f"<span style='color:#B3B3B3;font-size:0.82rem;'>"
        f"{_n_done:,} of {_total_tracks:,} tracks exported · {_remaining:,} remaining</span>"
        f"</div>"
        f"<div style='background:#333;border-radius:6px;height:8px;width:100%;'>"
        f"<div style='background:#1DB954;border-radius:6px;height:8px;"
        f"width:{min(_pct, 100):.1f}%;transition:width 0.3s;'></div>"
        f"</div>"
        f"<div style='display:flex;justify-content:space-between;margin-top:6px;'>"
        f"<span style='color:#1DB954;font-size:0.78rem;font-weight:700;'>"
        f"{_pct:.1f}% complete</span>"
        f"<span style='color:#B3B3B3;font-size:0.78rem;'>"
        f"Mark clusters as done after exporting to track progress</span>"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    _btn_col1, _btn_col2 = st.columns(2)
    with _btn_col1:
        if st.button(
            "🔄 Reset all progress",
            key="restore_done_progress",
            help="Clears all exported and manually assigned tracks — brings everything back into future clustering runs",
            type="secondary",
            use_container_width=True,
        ):
            if not reset_cluster_progress(user_key):
                st.toast("⚠️ Could not fully clear DB progress — reset saved as timestamp.", icon="🚨")
            st.session_state["done_tracks"] = set()
            st.session_state["unmatched_assignments"] = {}
            st.session_state.pop("_unmatched_done_ids", None)
            st.session_state.pop("_skipped_count", None)
            st.session_state["_uc_progress_cleared"] = True
            st.rerun()

    if _remaining > 0:
        with _btn_col2:
            if st.button(
                f"⏭️ Skip {_remaining:,} remaining tracks",
                key="skip_remaining",
                help="Marks all tracks not yet exported as done — use if they were excluded by filters in all previous runs",
                type="secondary",
                use_container_width=True,
            ):
                _all_pool_ids = set(_df_all_full["track_id"])
                _to_skip = _all_pool_ids - _handled_ids
                for _skip_tid in _to_skip:
                    try:
                        save_cluster_progress(user_key, _skip_tid, status="done")
                    except Exception:
                        pass
                st.session_state["done_tracks"].update(_to_skip)
                st.session_state["_skipped_count"] = (
                    st.session_state.get("_skipped_count", 0) + len(_to_skip)
                )
                st.rerun()
        _skip_note = (
            f"ℹ️ {_remaining:,} track(s) have no audio features and couldn't be clustered — "
            f"use the Unmatched Tracks section after running to assign them manually, "
            f"or skip them with the button above."
        )
        st.markdown(
            f"<p style='color:#B3B3B3;font-size:0.75rem;margin-top:4px;'>{_skip_note}</p>",
            unsafe_allow_html=True,
        )

    hr(top=12, bottom=20)

section_title("🎛️ Configure", "Set all filters and K — then hit Run.")

# ── Playlists ────────────────────────────────────────────────────────────────
selected_playlists = st.multiselect(
    "Playlists to include",
    options=all_playlists,
    default=[
        p for p in st.session_state.get(_pl_key, _last_playlists)
        if p in all_playlists
    ] or all_playlists,
    key=_pl_key,
)


# ── Optional filters — reactive, outside form ────────────────────────────────
st.markdown(
    "<p style='color:#B3B3B3;font-size:0.82rem;margin-bottom:8px;margin-top:12px;'>"
    "Optional filters — selecting all families is the same as no filter. "
    "A track is included if it matches <b style='color:#FFFFFF;'>any</b> of the selected genre families — "
    "e.g. a Rock/Rap crossover track stays in as long as either Rock or Hip-Hop is selected. "
    "Clearing all families will select 0 tracks.</p>",
    unsafe_allow_html=True,
)

filter_left, filter_right = st.columns(2)

with filter_left:
    if "decade" in df_all.columns:
        _pl_now = st.session_state.get(_pl_key, all_playlists)
        available_decades = sorted(
            _df_for_opts[_df_for_opts["playlist_name"].isin(_pl_now)]["decade"]
            .dropna().astype("Int64").unique().tolist()
        )
        decade_options = [str(d) for d in available_decades]
        _decade_key = "clusters_decade_filter_yc"
        selected_decades = st.multiselect(
            "Decades to include",
            options=decade_options,
            default=[
                d for d in (st.session_state.get(_decade_key, _last_decades) or decade_options)
                if d in decade_options
            ] or decade_options,
            key=_decade_key,
        )
    else:
        selected_decades = []
        decade_options = []

with filter_right:
    if "artist_genres" in df_all.columns:
        _pl_now = st.session_state.get(_pl_key, all_playlists)
        all_families_available = sorted(set(
            fam
            for g in _df_for_opts[_df_for_opts["playlist_name"].isin(_pl_now)]["artist_genres"].dropna()
            for fam in _assign_family(g)
            if fam != "Other"
        )) + ["Other"]
        _genre_key = "clusters_genre_filter_yc"
        selected_families = st.multiselect(
            "Genre families to include",
            options=all_families_available,
            default=[
                f for f in (st.session_state.get(_genre_key, _last_families) or all_families_available)
                if f in all_families_available
            ] or all_families_available,
            key=_genre_key,
        )
    else:
        selected_families = []
        all_families_available = []

st.session_state["selected_genres"] = set()

# ── Grouping mode selector ───────────────────────────────────────────────────
hr(top=16, bottom=16)
st.markdown(
    "<p style='color:#B3B3B3;font-size:0.85rem;font-weight:700;margin-bottom:8px;'>"
    "Grouping method</p>",
    unsafe_allow_html=True,
)
grouping_mode = st.radio(
    "Grouping method",
    options=["🔬 By audio similarity (KMeans)", "🗂️ By category", "🏷️ By specific genre"],
    index=(
        0 if _last_grouping == "🔬 By audio similarity (KMeans)"
        else 2 if _last_grouping == "🏷️ By specific genre"
        else 1
    ),
    horizontal=True,
    key="grouping_mode",
    label_visibility="collapsed",
)

_sgl_checked_genres: set = set()  # populated below in the By specific genre branch

if grouping_mode == "🔬 By audio similarity (KMeans)":
    group_by_decade = True
    group_by_genre = True
    st.markdown(
        "<p style='color:#B3B3B3;font-size:0.78rem;margin-top:4px;'>"
        "ℹ️ Your playlist, decade and genre filters above narrow the track pool before clustering.</p>",
        unsafe_allow_html=True,
    )

elif grouping_mode == "🗂️ By category":
    _dim_default = (
        "📅🎸 Both" if (_last_group_by_decade and _last_group_by_genre)
        else ("📅 Decade only" if _last_group_by_decade else "🎸 Genre family only")
    )
    _dim_choice = st.radio(
        "Group by:",
        options=["📅 Decade only", "🎸 Genre family only", "📅🎸 Both"],
        index=["📅 Decade only", "🎸 Genre family only", "📅🎸 Both"].index(_dim_default),
        horizontal=True,
        key="grouping_dim_choice",
    )
    group_by_decade = _dim_choice in ("📅 Decade only", "📅🎸 Both")
    group_by_genre = _dim_choice in ("🎸 Genre family only", "📅🎸 Both")

    st.markdown(
        "<p style='color:#B3B3B3;font-size:0.78rem;margin-top:4px;'>"
        "ℹ️ Your playlist filter above narrows which playlists are included. "
        "Decade and genre filters narrow the pool further if you don't want all "
        "decades/genres as groups.</p>",
        unsafe_allow_html=True,
    )
    _info_pl_now = st.session_state.get(_pl_key, all_playlists)
    _ginfo_pool = _df_all_full[_df_all_full["playlist_name"].isin(_info_pl_now)]
    # Count "no decade" BEFORE the filter removes NaN-decade rows — those tracks
    # will always go to unmatched regardless of which decades are selected.
    _n_no_decade = 0
    if group_by_decade and "decade" in _ginfo_pool.columns:
        _n_no_decade = int(_ginfo_pool[_ginfo_pool["decade"].isna()]["track_id"].nunique())

    if selected_decades and "decade" in _ginfo_pool.columns:
        _ginfo_pool = _ginfo_pool[
            _ginfo_pool["decade"].astype("Int64").astype(str).isin(selected_decades)
        ]
    if "artist_genres" in _ginfo_pool.columns and set(selected_families) != set(all_families_available):
        _ginfo_pool = _ginfo_pool[_ginfo_pool["artist_genres"].apply(
            lambda g: _track_matches_families(g, selected_families)
        )]
    _done_for_info = st.session_state.get("done_tracks", set())
    if _done_for_info:
        _ginfo_pool = _ginfo_pool[~_ginfo_pool["track_id"].isin(_done_for_info)]
    if group_by_genre and "artist_genres" in _ginfo_pool.columns:
        _n_no_genre = int(
            _ginfo_pool[
                _ginfo_pool["artist_genres"].isna() | (_ginfo_pool["artist_genres"].str.strip() == "")
            ]["track_id"].nunique()
        )

else:
    # ── 🏷️ By specific genre ──────────────────────────────────────────────────
    group_by_genre = False
    group_by_decade = st.checkbox(
        "📅 Also group by decade (e.g. 'baroque pop · 1980s')",
        value=st.session_state.get("specific_genre_decade", False),
        key="specific_genre_decade",
    )

    st.markdown(
        "<p style='color:#B3B3B3;font-size:0.78rem;margin-top:6px;'>"
        "ℹ️ Each checked genre becomes its own cluster. A track tagged with multiple selected "
        "genres appears in <b style='color:#FFFFFF;'>all</b> of them. "
        "Tracks whose genre tags don't match any selection are silently excluded.</p>",
        unsafe_allow_html=True,
    )

    # Build raw genre pool from all tracks in selected playlists
    _sgl_pl = st.session_state.get(_pl_key, all_playlists)
    _sgl_pool = _df_all_full[_df_all_full["playlist_name"].isin(_sgl_pl)]
    _done_sgl = st.session_state.get("done_tracks", set())
    if _done_sgl:
        _sgl_pool = _sgl_pool[~_sgl_pool["track_id"].isin(_done_sgl)]

    _sgl_all_raw = sorted(set(
        g.strip()
        for gs in _sgl_pool["artist_genres"].dropna()
        for g in gs.split(",")
        if g.strip()
    ))

    # Group raw genres under families for display
    _sgl_fam_map: dict = {fam: [] for fam in all_families_available}
    for g in _sgl_all_raw:
        matched = [
            fam for fam in all_families_available
            if fam != "Other" and any(kw in g.lower() for kw in GENRE_FAMILIES.get(fam, []))
        ]
        _sgl_fam_map[matched[0] if matched else "Other"].append(g)

    _sgl_key = "specific_cluster_genres"

    # Default: pre-select genres whose assigned family (per _sgl_fam_map) is in selected_families.
    # This ensures genres in the Folk section stay unchecked when Folk is removed — even if the
    # genre string happens to contain a keyword from another family (e.g. "folk rock" has "rock").
    _sgl_default = set()
    for _dfam, _dgenres in _sgl_fam_map.items():
        if _dfam in selected_families:
            _sgl_default.update(_dgenres)

    # Reset genre selection when families change or on first entry into this mode.
    # Explicitly SET each checkbox key (not pop) so Streamlit picks up the new value immediately.
    _prev_sgl_fams = st.session_state.get("_prev_sgl_families")
    _cur_sgl_fams = tuple(sorted(selected_families))
    if _prev_sgl_fams != _cur_sgl_fams:
        for _dfam, _dgenres in _sgl_fam_map.items():
            _fam_on = _dfam in selected_families
            for _g in _dgenres:
                st.session_state[f"sgl_cb_{_g}"] = _fam_on
        st.session_state[_sgl_key] = _sgl_default
        st.session_state["_prev_sgl_families"] = _cur_sgl_fams

    _sgl_selected: set = st.session_state.get(_sgl_key, _sgl_default)

    # Precompute token sets and selected-genre intersections once for the whole pool.
    # Used to compute per-genre exclusive counts (tracks that would disappear from the
    # unique total if that genre were unchecked — i.e. no other selected genre covers them).
    _pool_tokens_ser = _sgl_pool["artist_genres"].apply(
        lambda g: frozenset(t.strip() for t in (g or "").split(","))
    )
    _pool_sel_intersect = _pool_tokens_ser.apply(lambda ts: ts & _sgl_selected)

    with st.expander(
        f"🏷️ Pick genres to cluster — {len(_sgl_selected)} selected",
        expanded=True,
    ):
        st.markdown(
            "<p style='color:#B3B3B3;font-size:0.78rem;margin-bottom:8px;'>"
            "Genres matching your family filter above are pre-selected. "
            "Uncheck any you don't want — each checked genre becomes one Spotify playlist.</p>",
            unsafe_allow_html=True,
        )
        _sgl_new: set = set()
        for _sfam, _sgenres in _sgl_fam_map.items():
            if not _sgenres:
                continue
            _sfam_checked = sum(1 for g in _sgenres if st.session_state.get(f"sgl_cb_{g}", g in _sgl_selected))
            with st.expander(f"{_sfam} — {_sfam_checked}/{len(_sgenres)} selected", expanded=(_sfam_checked > 0)):
                _sb1, _sb2, _ = st.columns([1, 1, 4])
                with _sb1:
                    if st.button("✓ All", key=f"sgl_all_{_sfam}", use_container_width=True, type="primary"):
                        for g in _sgenres:
                            st.session_state[f"sgl_cb_{g}"] = True
                        st.session_state[_sgl_key] = _sgl_selected | set(_sgenres)
                        st.rerun()
                with _sb2:
                    if st.button("✗ None", key=f"sgl_none_{_sfam}", use_container_width=True):
                        for g in _sgenres:
                            st.session_state[f"sgl_cb_{g}"] = False
                        st.session_state[_sgl_key] = _sgl_selected - set(_sgenres)
                        st.rerun()
                _sgl_cols = st.columns(3)
                for _sidx, _sg in enumerate(sorted(_sgenres)):
                    with _sgl_cols[_sidx % 3]:
                        _stc = int(_pool_tokens_ser.apply(lambda ts: _sg in ts).sum())
                        _excl = int((_pool_sel_intersect == frozenset({_sg})).sum())
                        _cb_label = (
                            f"{_sg} ({_stc})"
                            if _excl == _stc
                            else f"{_sg} ({_stc} · {_excl} excl.)"
                        )
                        _schecked = st.checkbox(
                            _cb_label,
                            value=_sg in _sgl_selected,
                            key=f"sgl_cb_{_sg}",
                        )
                        if _schecked:
                            _sgl_new.add(_sg)
        st.session_state[_sgl_key] = _sgl_new
        _sgl_checked_genres = _sgl_new

# ── K selector (KMeans only) ─────────────────────────────────────────────────
if grouping_mode == "🔬 By audio similarity (KMeans)":
    hr(top=16, bottom=16)
    k_left, k_right = st.columns([1, 3])
    with k_left:
        k_mode = st.radio(
            "K selection (how many clusters/playlists?)",
            options=["Auto", "Manual"],
            index=0 if _last_k_mode == "Auto" else 1,
            horizontal=True,
            key="k_mode",
        )
    with k_right:
        if k_mode == "Manual":
            k_manual = st.slider(
                "K (clusters)",
                min_value=2, max_value=10, value=4,
                key="k_manual_slider",
            )
        else:
            st.markdown(
                "<p style='color:#B3B3B3;font-size:0.85rem;margin-top:8px;'>"
                "Optimal k will be computed automatically using silhouette score.</p>",
                unsafe_allow_html=True,
            )
            k_manual = None
else:
    k_mode = "Auto"
    k_manual = None

# ── Live preview ──────────────────────────────────────────────────────────────
hr(top=16, bottom=12)
_pl_now = st.session_state.get(_pl_key, all_playlists)
_sg = st.session_state.get("selected_genres", set())
_grouping_mode_current = st.session_state.get("grouping_mode", "🔬 By audio similarity (KMeans)")

# Evaluated first — before any expensive IO — so the render is immediate
_n_unmatched_preview = 0  # KMeans: tracks without audio features (secondary note)
_n_unmatched_cat     = 0  # By category: tracks missing genre/decade (secondary note)
_n_no_af_cat         = 0  # By category / SGL: tracks without audio features (tertiary note)
_n_genreless_sgl     = 0  # SGL: genre-less tracks that will go to unmatched (secondary note)
_no_grouping_dim = (
    grouping_mode == "🗂️ By category"
    and not group_by_decade
    and not group_by_genre
)

if _no_grouping_dim:
    _prev_count = 0

elif _grouping_mode_current == "🗂️ By category":
    _cat_filtered = _df_all_full[
        _df_all_full["playlist_name"].isin(st.session_state.get(_pl_key, all_playlists))
    ].copy()
    if selected_decades and "decade" in _cat_filtered.columns:
        _cat_filtered = _cat_filtered[
            _cat_filtered["decade"].astype("Int64").astype(str).isin(selected_decades)
        ]
    if "artist_genres" in _cat_filtered.columns and set(selected_families) != set(all_families_available):
        _cat_filtered = _cat_filtered[
            _cat_filtered["artist_genres"].apply(
                lambda g: _track_matches_families(g, selected_families)
            )
        ]
    _done_set = st.session_state.get("done_tracks", set())
    if _done_set:
        _cat_filtered = _cat_filtered[~_cat_filtered["track_id"].isin(_done_set)]
    _cat_um_mask = pd.Series(False, index=_cat_filtered.index)
    if group_by_genre and "artist_genres" in _cat_filtered.columns:
        _cat_um_mask |= (_cat_filtered["artist_genres"].isna() | (_cat_filtered["artist_genres"].str.strip() == ""))
    if group_by_decade and "decade" in _cat_filtered.columns:
        _cat_um_mask |= _cat_filtered["decade"].isna()
    _n_unmatched_cat = int(_cat_filtered[_cat_um_mask]["track_id"].nunique())
    _n_no_af_cat     = int(_cat_filtered[~_cat_filtered["track_id"].isin(set(df_all["track_id"]))]["track_id"].nunique())
    _prev_count      = _cat_filtered["track_id"].nunique() - _n_unmatched_cat

elif _grouping_mode_current == "🏷️ By specific genre":
    _sgl_preview_genres = _sgl_checked_genres
    if not _sgl_preview_genres:
        _prev_count = 0
        _sgl_pool_total = 0
    else:
        _sgl_preview_pool = _df_all_full
        _sgl_preview_pool = _sgl_preview_pool[_sgl_preview_pool["playlist_name"].isin(_pl_now)]
        _done_set = st.session_state.get("done_tracks", set())
        if _done_set:
            _sgl_preview_pool = _sgl_preview_pool[~_sgl_preview_pool["track_id"].isin(_done_set)]
        # Scope the disclaimer to tracks that belong to any selected genre family;
        # tracks outside selected families are intentionally excluded (not "unmatched").
        if selected_families and set(selected_families) != set(all_families_available):
            _sgl_family_pool = _sgl_preview_pool[_sgl_preview_pool["artist_genres"].apply(
                lambda g: _track_matches_families(g, selected_families)
            )]
        else:
            _sgl_family_pool = _sgl_preview_pool
        _sgl_pool_total  = _sgl_family_pool["track_id"].nunique()
        _prev_count      = int(_sgl_family_pool[
            _sgl_family_pool["artist_genres"].apply(
                lambda g: bool({t.strip() for t in (g or "").split(",")} & _sgl_preview_genres)
            )
        ]["track_id"].nunique())
        # Genre-less tracks in pool → will go to unmatched (secondary note)
        _n_genreless_sgl = int(_sgl_family_pool[
            _sgl_family_pool["artist_genres"].isna() | (_sgl_family_pool["artist_genres"].str.strip() == "")
        ]["track_id"].nunique())
        # No-AF tracks in pool (tertiary note — shared variable with By category)
        _n_no_af_cat     = int(_sgl_family_pool[
            ~_sgl_family_pool["track_id"].isin(set(df_all["track_id"]))
        ]["track_id"].nunique())

else:
    # KMeans mode — count only audio-feature tracks; unmatched shown in disclaimer below
    _done_set = st.session_state.get("done_tracks", set())
    _prev_clusterable = _preview_filter(
        df_all, _pl_now, selected_decades, selected_families, [], all_families_available
    )
    _done_set_normalized = {tid.strip() for tid in _done_set}
    _done_df = df_all[df_all["track_id"].str.strip().isin(_done_set_normalized)]
    _done_in_pool = _preview_filter(
        _done_df, _pl_now, selected_decades, selected_families, [], all_families_available
    ) if _done_set else 0
    _prev_clusterable -= _done_in_pool
    _yc_unmatched_preview = _yc_ne[_yc_ne["playlist_name"].isin(_pl_now)].drop_duplicates(subset="track_id")
    if selected_decades and "release_year" in _yc_unmatched_preview.columns:
        _yc_unmatched_preview["_decade"] = (
            pd.to_numeric(_yc_unmatched_preview["release_year"], errors="coerce")
            .dropna().astype(int) // 10 * 10
        ).astype("Int64").astype(str)
        _yc_unmatched_preview = _yc_unmatched_preview[
            _yc_unmatched_preview["_decade"].isin(selected_decades)
        ].drop(columns=["_decade"])
    if "artist_genres" in _yc_unmatched_preview.columns \
            and set(selected_families) != set(all_families_available):
        _yc_unmatched_preview = _yc_unmatched_preview[
            _yc_unmatched_preview["artist_genres"].apply(
                lambda g: _track_matches_families(g, selected_families)
            )
        ]
    if _manual_assigned_ids:
        _yc_unmatched_preview = _yc_unmatched_preview[
            ~_yc_unmatched_preview["track_id"].isin(_manual_assigned_ids)
        ]
    _n_unmatched_preview = len(_yc_unmatched_preview)
    _prev_count = _prev_clusterable

if _grouping_mode_current == "🗂️ By category":
    _k_label = "by category"
elif _grouping_mode_current == "🏷️ By specific genre":
    _k_label = "by specific genre"
elif k_mode == "Manual":
    _k_label = f"k={k_manual} (manual)"
else:
    _k_label = "k=auto"

if _no_grouping_dim:
    st.warning("⚠️ Select at least one grouping dimension — check **Decade**, **Genre family**, or both.")
elif _prev_count == 0 and _n_unmatched_cat > 0:
    st.warning(
        f"⚠️ All {_n_unmatched_cat:,} tracks in your selection are missing genre/decade data — "
        f"they'll all go to Unmatched for manual assignment. No clusters will be created automatically."
    )
elif _prev_count == 0:
    st.error("⚠️ No tracks match current filters — adjust before running.")
elif _grouping_mode_current == "🔬 By audio similarity (KMeans)" and _prev_count < 4:
    st.warning(f"⚠️ Only {_prev_count} tracks selected — need at least 4 to cluster.")
else:
    _n_done = len(st.session_state.get("done_tracks", set()))
    _done_label = ""
    _count_verb = (
        "will be grouped" if _grouping_mode_current in ("🗂️ By category", "🏷️ By specific genre")
        else "selected"
    )
    st.markdown(
        f"<div style='background:#1a1a1a;border:1px solid #333;border-radius:10px;"
        f"padding:10px 18px;margin-bottom:8px;'>"
        f"<span style='color:#1DB954;font-weight:800;font-size:1rem;'>🎯 {_prev_count:,} "
        f"tracks</span>"
        f"<span style='color:#B3B3B3;font-size:0.88rem;'> {_count_verb} · {_k_label}{_done_label}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    # ── Secondary note: what goes to Unmatched Tracks ────────────────────────
    if _grouping_mode_current == "🔬 By audio similarity (KMeans)" and _n_unmatched_preview > 0:
        # KMeans: no audio features = unmatched
        st.markdown(
            f"<p style='color:#B3B3B3;font-size:0.75rem;margin-top:-4px;'>"
            f"ℹ️ + {_n_unmatched_preview:,} tracks without audio features will appear in "
            f"Unmatched Tracks after running for manual assignment.</p>",
            unsafe_allow_html=True,
        )
    elif _grouping_mode_current == "🗂️ By category" and _n_unmatched_cat > 0:
        # By category: missing genre/decade = unmatched
        _cat_um_reasons = []
        if group_by_genre:
            _cat_um_reasons.append("no genre data")
        if group_by_decade:
            _cat_um_reasons.append("no release decade")
        _cat_um_str = " or ".join(_cat_um_reasons) or "missing data"
        st.markdown(
            f"<p style='color:#B3B3B3;font-size:0.75rem;margin-top:-4px;'>"
            f"ℹ️ + {_n_unmatched_cat:,} tracks have {_cat_um_str} → will appear in "
            f"Unmatched Tracks after running for manual assignment.</p>",
            unsafe_allow_html=True,
        )
    elif _grouping_mode_current == "🏷️ By specific genre" and _n_genreless_sgl > 0:
        # SGL: no genre data = unmatched
        st.markdown(
            f"<p style='color:#B3B3B3;font-size:0.75rem;margin-top:-4px;'>"
            f"ℹ️ + {_n_genreless_sgl:,} tracks have no genre data → will appear in "
            f"Unmatched Tracks after running for manual assignment.</p>",
            unsafe_allow_html=True,
        )
    # ── Tertiary note: no-audio-features tracks (By category and SGL only) ──
    if _grouping_mode_current in ("🗂️ By category", "🏷️ By specific genre") and _n_no_af_cat > 0:
        st.markdown(
            f"<p style='color:#B3B3B3;font-size:0.75rem;margin-top:-4px;'>"
            f"ℹ️ + {_n_no_af_cat:,} tracks without audio features are included — "
            f"they'll be grouped like all others (clusters if they have genre/decade data, "
            f"Unmatched if not).</p>",
            unsafe_allow_html=True,
        )
    # ── Duplicate note (KMeans only) ──────────────────────────────────────────
    _total_dupes = _yc_cross_dupes_total + _intra_dupes
    if _total_dupes > 0 and _grouping_mode_current == "🔬 By audio similarity (KMeans)":
        _dupe_parts = []
        if _yc_cross_dupes_total > 0:
            _dupe_parts.append(f"{_yc_cross_dupes_total} across multiple playlists")
        if _intra_dupes > 0:
            _dupe_parts.append(f"{_intra_dupes} twice in the same playlist")
        st.markdown(
            f"<p style='color:#B3B3B3;font-size:0.75rem;margin-top:-4px;'>"
            f"ℹ️ {_total_dupes} duplicate(s) counted once ({' · '.join(_dupe_parts)}) — no tracks are lost. "
            f"If Playlist Comparison shows one more, it's likely the same song in two different versions "
            f"(e.g. studio vs live recording) with different Spotify IDs — counted as separate tracks here.</p>",
            unsafe_allow_html=True,
        )
    if _prev_count < 100:
        st.markdown(
            "<div style='background:#1a1a1a;border:1px solid #F5A623;border-radius:10px;"
            "padding:12px 18px;margin-top:8px;'>"
            "<span style='color:#F5A623;font-weight:700;'>💡 Tip — </span>"
            "<span style='color:#FFFFFF;font-size:0.88rem;'>"
            "My Clusters works best with <b>200+ tracks across multiple playlists</b>. "
            "With fewer tracks, clusters may be too broad or overlap heavily. "
            "Try adding more playlists to get richer, more meaningful groupings.</span>"
            "</div>",
            unsafe_allow_html=True,
        )
    elif _prev_count < 200:
        st.markdown(
            "<div style='background:#1a1a1a;border:1px solid #333;border-radius:10px;"
            "padding:12px 18px;margin-top:8px;'>"
            "<span style='color:#B3B3B3;font-size:0.85rem;'>"
            "💡 <b style='color:#FFFFFF;'>Getting better results:</b> "
            "adding more playlists gives the model more variety to work with — "
            "try including playlists from different genres or eras.</span>"
            "</div>",
            unsafe_allow_html=True,
        )

hr(top=12, bottom=12)
_btn_label = "▶ Run Clustering" if grouping_mode == "🔬 By audio similarity (KMeans)" else "▶ Group Tracks"
submitted = st.button(
    _btn_label,
    use_container_width=True,
    type="primary",
    key="run_clustering_btn",
    disabled=_no_grouping_dim or _prev_count == 0,
)

if not submitted and "clustering_results" not in st.session_state:
    _action_label = "▶ Group Tracks" if grouping_mode == "🗂️ By category" else "▶ Run Clustering"
    st.markdown(
        "<div style='background:#1a1a1a;border:1px solid #333;border-radius:10px;"
        "padding:20px;text-align:center;color:#B3B3B3;font-size:0.9rem;'>"
        f"Configure your filters above and click <b style='color:#1DB954;'>{_action_label}</b> to begin."
        "</div>",
        unsafe_allow_html=True,
    )
    st.stop()

if submitted:
    st.session_state.pop("_uc_progress_cleared", None)
    if not selected_playlists:
        st.warning("Select at least one playlist.")
        st.stop()

    _grouping_mode_submit = st.session_state.get("grouping_mode", "🔬 By audio similarity (KMeans)")

    if _grouping_mode_submit == "🗂️ By category":
        _dim_choice_submit = st.session_state.get("grouping_dim_choice", "📅🎸 Both")
        _group_by_decade = _dim_choice_submit in ("📅 Decade only", "📅🎸 Both")
        _group_by_genre  = _dim_choice_submit in ("🎸 Genre family only", "📅🎸 Both")

        df_for_grouping = _df_all_full[_df_all_full["playlist_name"].isin(selected_playlists)].copy()
        if selected_decades and "decade" in df_for_grouping.columns:
            df_for_grouping = df_for_grouping[
                df_for_grouping["decade"].astype("Int64").astype(str).isin(selected_decades)
            ]
        if "artist_genres" in df_for_grouping.columns and set(selected_families) != set(all_families_available):
            df_for_grouping = df_for_grouping[df_for_grouping["artist_genres"].apply(
                lambda g: _track_matches_families(g, selected_families)
            )]

        _done = st.session_state.get("done_tracks", set())
        if _done:
            df_for_grouping = df_for_grouping[~df_for_grouping["track_id"].isin(_done)]

        n_tracks = len(df_for_grouping)
        if n_tracks < 2:
            st.warning("Not enough tracks after filtering — adjust your filters.")
            st.stop()

        with st.spinner("Grouping tracks..."):
            df_clust_cat, df_unmatched_cat = run_category_grouping(df_for_grouping, _group_by_decade, _group_by_genre)

        if len(df_clust_cat) < 2:
            st.warning("Not enough tracks can be grouped — too many are missing genre/decade data. Adjust your filters or grouping options.")
            st.stop()

        _k_cat = df_clust_cat["cluster"].nunique()
        _name_map_cat = {
            int(row["cluster"]): row["cluster_name"]
            for _, row in df_clust_cat[["cluster", "cluster_name"]].drop_duplicates().iterrows()
        }

        st.session_state.pop("unmatched_assignments", None)
        st.session_state.pop("unmatched_save_status", None)
        st.session_state.pop("keep_visible", None)
        st.session_state.pop("_unmatched_done_ids", None)
        st.session_state["clustering_results"] = {
            "df_clust":          df_clust_cat,
            "name_map":          _name_map_cat,
            "centroids_scaled":  None,
            "var1":              0.0,
            "var2":              0.0,
            "scaler_used":       None,
            "pc1_label":         "",
            "pc2_label":         "",
            "metrics_df":        None,
            "best_k_sil":        None,
            "best_k_elbow":      None,
            "optimal_k":         _k_cat,
            "fc_override":       False,
            "n_tracks":          df_clust_cat["track_id"].nunique(),
            "selected_playlists": selected_playlists,
            "k":                 _k_cat,
            "k_mode":            "Manual",
            "selected_decades":  selected_decades,
            "selected_families": selected_families,
            "decade_options":    decade_options,
            "track_ids":         tuple(sorted(df_clust_cat["track_id"].tolist())),
            "grouping_mode":     _grouping_mode_submit,
            "group_by_decade":   _group_by_decade,
            "group_by_genre":    _group_by_genre,
            "df_unmatched_cat":  df_unmatched_cat,
            "total_playlists":   len(all_playlists),
        }
        if not is_dev_mode():
            try:
                from app_state.analytics import track_event as _te
                _cr = st.session_state["clustering_results"]
                _te("clustering_run", page="My Clusters",
                    session_id=st.session_state.get("uc_session_id", "anonymous"),
                    visitor_id=st.session_state.get("visitor_id"),
                    properties={"mode": "By category", "k": _cr["k"],
                                "n_tracks": _cr["n_tracks"],
                                "n_playlists": len(_cr["selected_playlists"])})
            except Exception:
                pass
        st.switch_page("pages/_Cluster_Results.py")

    elif _grouping_mode_submit == "🏷️ By specific genre":
        # ── By specific genre branch ──────────────────────────────────────────
        _sgl_selected_submit = st.session_state.get("specific_cluster_genres", set())

        if not _sgl_selected_submit:
            st.warning("Select at least one genre to cluster by.")
            st.stop()

        df_for_sgl = _df_all_full[_df_all_full["playlist_name"].isin(selected_playlists)].copy()

        _done = st.session_state.get("done_tracks", set())
        if _done:
            df_for_sgl = df_for_sgl[~df_for_sgl["track_id"].isin(_done)]

        # Decade is a pre-filter in SGL mode (same as all other modes)
        if selected_decades and "decade" in df_for_sgl.columns:
            df_for_sgl = df_for_sgl[
                df_for_sgl["decade"].astype("Int64").astype(str).isin(selected_decades)
            ]

        _group_by_decade_sgl = st.session_state.get("specific_genre_decade", False)

        with st.spinner("Grouping tracks by genre..."):
            df_clust_sgl = run_specific_genre_grouping(df_for_sgl, list(_sgl_selected_submit), _group_by_decade_sgl)

        if df_clust_sgl.empty:
            st.warning("No tracks matched the selected genres. Try selecting different genres.")
            st.stop()

        # SGL unmatched = tracks with NO genre data (they can't match any specific genre).
        # Tracks WITH genre data that don't match any selected genre are silently excluded.
        _matched_sgl_ids = set(df_clust_sgl["track_id"])
        _df_unmatched_sgl = df_for_sgl[
            (~df_for_sgl["track_id"].isin(_matched_sgl_ids))
            & (df_for_sgl["artist_genres"].isna() | (df_for_sgl["artist_genres"].str.strip() == ""))
        ].drop_duplicates(subset="track_id").copy()

        _k_sgl = df_clust_sgl["cluster"].nunique()
        _name_map_sgl = {
            int(row["cluster"]): row["cluster_name"]
            for _, row in df_clust_sgl[["cluster", "cluster_name"]].drop_duplicates().iterrows()
        }

        st.session_state.pop("unmatched_assignments", None)
        st.session_state.pop("unmatched_save_status", None)
        st.session_state.pop("keep_visible", None)
        st.session_state.pop("_unmatched_done_ids", None)
        st.session_state["clustering_results"] = {
            "df_clust":           df_clust_sgl,
            "name_map":           _name_map_sgl,
            "centroids_scaled":   None,
            "var1":               0.0,
            "var2":               0.0,
            "scaler_used":        None,
            "pc1_label":          "",
            "pc2_label":          "",
            "metrics_df":         None,
            "best_k_sil":         None,
            "best_k_elbow":       None,
            "optimal_k":          _k_sgl,
            "fc_override":        False,
            "n_tracks":           df_clust_sgl["track_id"].nunique(),
            "selected_playlists": selected_playlists,
            "k":                  _k_sgl,
            "k_mode":             "Manual",
            "selected_decades":   selected_decades,
            "selected_families":  selected_families,
            "decade_options":     decade_options,
            "track_ids":          tuple(sorted(df_clust_sgl["track_id"].tolist())),
            "grouping_mode":      _grouping_mode_submit,
            "group_by_decade":    _group_by_decade_sgl,
            "group_by_genre":     False,
            "df_unmatched_cat":   _df_unmatched_sgl,
            "total_playlists":    len(all_playlists),
        }
        if not is_dev_mode():
            try:
                from app_state.analytics import track_event as _te
                _cr = st.session_state["clustering_results"]
                _te("clustering_run", page="My Clusters",
                    session_id=st.session_state.get("uc_session_id", "anonymous"),
                    visitor_id=st.session_state.get("visitor_id"),
                    properties={"mode": "By specific genre", "k": _cr["k"],
                                "n_tracks": _cr["n_tracks"],
                                "n_playlists": len(_cr["selected_playlists"])})
            except Exception:
                pass
        st.switch_page("pages/_Cluster_Results.py")

    else:
        # ── KMeans branch ────────────────────────────────────────────────────
        df_filtered = df_all[df_all["playlist_name"].isin(selected_playlists)].copy()

        _done = st.session_state.get("done_tracks", set())
        if _done:
            df_filtered = df_filtered[~df_filtered["track_id"].isin(_done)]

        if selected_decades and "decade" in df_filtered.columns:
            df_filtered = df_filtered[
                df_filtered["decade"].astype("Int64").astype(str).isin(selected_decades)
            ]

        if "artist_genres" in df_filtered.columns:
            _sg_submit = st.session_state.get("selected_genres", set())
            if _sg_submit:
                df_filtered = df_filtered[df_filtered["artist_genres"].apply(
                    lambda g: (not g or pd.isna(g) or str(g).strip() == "")
                              or any(rg in (g or "") for rg in _sg_submit)
                )]
            elif set(selected_families) != set(all_families_available):
                df_filtered = df_filtered[df_filtered["artist_genres"].apply(
                    lambda g: _track_matches_families(g, selected_families)
                )]
        else:
            _sg_submit = set()

        n_tracks = len(df_filtered)
        if n_tracks < 4:
            st.warning(f"Only {n_tracks} tracks after filtering — need at least 4 to cluster. Adjust your filters.")
            st.stop()

        track_ids = tuple(sorted(df_filtered["track_id"].tolist()))

        # Pre-build filtered unmatched DF — same playlist/decade/family filters as the
        # clustering pool so that _Cluster_Results.py never shows out-of-scope tracks.
        _unmatched_pre = _load_unmatched()
        if not _unmatched_pre.empty:
            _unmatched_pre = _unmatched_pre[
                _unmatched_pre["playlist_name"].isin(selected_playlists)
            ].drop_duplicates(subset="track_id")
            if selected_decades and "release_year" in _unmatched_pre.columns:
                _unmatched_pre["_d"] = (
                    pd.to_numeric(_unmatched_pre["release_year"], errors="coerce")
                    .dropna().astype(int) // 10 * 10
                ).astype("Int64").astype(str)
                _unmatched_pre = _unmatched_pre[
                    _unmatched_pre["_d"].isin(selected_decades)
                ].drop(columns=["_d"])
            if "artist_genres" in _unmatched_pre.columns and set(selected_families) != set(all_families_available):
                _unmatched_pre = _unmatched_pre[_unmatched_pre["artist_genres"].apply(
                    lambda g: _track_matches_families(g, selected_families)
                )]
            _done_unm = st.session_state.get("done_tracks", set())
            if _done_unm:
                _unmatched_pre = _unmatched_pre[~_unmatched_pre["track_id"].isin(_done_unm)]
        else:
            _unmatched_pre = pd.DataFrame()

        _k_spinner = "Finding optimal k…" if k_mode != "Manual" else "Analyzing clusters…"
        with st.spinner(_k_spinner):
            metrics_df = compute_k_metrics(df_all, track_ids)
        best_k_sil, best_k_elbow = _best_k(metrics_df)

        if k_mode == "Manual" and k_manual is not None:
            optimal_k  = k_manual
            fc_override = False
        else:
            optimal_k  = best_k_sil
            fc_override = False

        with st.spinner("Clustering..."):
            results = run_kmeans(df_all, track_ids, optimal_k)

        st.session_state.pop("unmatched_assignments", None)
        st.session_state.pop("unmatched_save_status", None)
        st.session_state.pop("keep_visible", None)
        st.session_state.pop("_unmatched_done_ids", None)
        st.session_state["clustering_results"] = {
            "df_clust":          results[0],
            "name_map":          results[1],
            "centroids_scaled":  results[2],
            "var1":              results[3],
            "var2":              results[4],
            "scaler_used":       results[5],
            "pc1_label":         results[6],
            "pc2_label":         results[7],
            "cluster_descriptions": results[8],
            "metrics_df":        metrics_df,
            "best_k_sil":        best_k_sil,
            "best_k_elbow":      best_k_elbow,
            "optimal_k":         optimal_k,
            "fc_override":       fc_override,
            "n_tracks":          n_tracks,
            "selected_playlists": selected_playlists,
            "k":                 optimal_k,
            "k_mode":            k_mode,
            "selected_decades":  selected_decades,
            "selected_families": selected_families,
            "decade_options":    decade_options,
            "track_ids":         track_ids,
            "grouping_mode":     _grouping_mode_submit,
            "total_playlists":   len(all_playlists),
            "df_unmatched_cat":  _unmatched_pre,
        }
        if not is_dev_mode():
            try:
                from app_state.analytics import track_event as _te
                _cr = st.session_state["clustering_results"]
                _te("clustering_run", page="My Clusters",
                    session_id=st.session_state.get("uc_session_id", "anonymous"),
                    visitor_id=st.session_state.get("visitor_id"),
                    properties={"mode": "KMeans", "k": _cr["k"],
                                "n_tracks": _cr["n_tracks"],
                                "n_playlists": len(_cr["selected_playlists"])})
            except Exception:
                pass
        st.switch_page("pages/_Cluster_Results.py")

