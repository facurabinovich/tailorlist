import os
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
from db.queries import load_cluster_data, get_tracks, load_unmatched_tracks, _add_artist_display
from datetime import datetime
from spotify_client import render_export_to_spotify
from utils import inject_global_css, inject_sidebar_nav, check_collection_mode, spotify_icon_html, page_brand_html

# Functions in this module are imported by _Cluster_Results.py
# Do not remove helper functions even if they appear unused here

inject_global_css()
inject_sidebar_nav("My Clusters")

if st.session_state.pop("_start_fresh", False):
    for _key in [
        "clustering_results", "clusters_pl_filter_fc", "clusters_pl_filter_yc",
        "clusters_decade_filter_fc", "clusters_decade_filter_yc",
        "clusters_genre_filter_fc", "clusters_genre_filter_yc",
        "selected_genres", "_prev_genre_families", "_prev_sgl_families", "cluster_descriptions",
        "grouping_mode", "k_mode", "k_manual_slider",
        "group_by_decade", "group_by_genre", "keep_visible",
        "specific_cluster_genres", "specific_genre_decade", "grouping_dim_choice",
        "_unmatched_done_ids", "_total_assigned_count",
    ]:
        st.session_state.pop(_key, None)
from db.queries import load_cluster_progress, save_cluster_progress, reset_cluster_progress
user_key = (
    st.session_state.get("uc_session_id", "anonymous")
    if st.session_state.get("mode") == "🔗 Your Collection"
    else "facu"
)

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

GENRE_FAMILIES = {
    # Checked in order — first matching family wins.
    # Keywords are matched as substrings of the full genre string (case-insensitive).
    "Rock":       ["rock", "punk", "metal", "grunge", "hardcore", "emo", "shoegaze"],
    "Pop":        ["pop"],  # "pop" alone covers baroque pop, indie pop, synth-pop, afropop, etc.
    "Hip-Hop":    ["hip hop", "rap", "trap", "drill", "r&b", "soul", "grime"],
    "Electronic": ["electronic", "edm", "house", "techno", "trance", "ambient", "synthwave",
                   "disco", "new wave", "dubstep", "drum and bass", "electro", "downtempo",
                   "chillwave", "darkwave", "cold wave", "eurodance", "italo"],
    "Jazz":       ["jazz", "bebop", "swing", "blues", "big band", "boogie"],
    "Classical":  ["classical", "opera", "orchestra", "chamber"],
    "Folk":       ["folk", "acoustic", "singer-songwriter", "country", "americana", "bluegrass",
                   "newgrass", "honky tonk"],
    "Latin":      ["latin", "reggaeton", "salsa", "cumbia", "bossa nova", "bachata", "tango",
                   "bolero", "merengue", "mariachi", "ranchera", "mpb", "trova", "soca",
                   "calypso", "folklore", "folclor", "candombe", "murga", "villancico"],
    "Reggae":     ["reggae", "dancehall", "ska", "ragga", "riddim", "dub"],
}

def _assign_family(genre_str: str) -> list[str]:
    """Map a raw genre string to one or more family labels. Unmatched → Other."""
    if not genre_str or pd.isna(genre_str) or str(genre_str).strip() == "":
        return ["Other"]
    genres_lower = genre_str.lower()
    matched = [
        family for family, keywords in GENRE_FAMILIES.items()
        if any(kw in genres_lower for kw in keywords)
    ]
    return matched if matched else ["Other"]


def _track_matches_families(genre_str: str, selected_fams: list) -> bool:
    """
    Returns True if ANY of the track's raw genre tags match ANY selected family's keywords.
    Tracks with NO genre data always pass — they don't belong to any family so the
    family filter cannot exclude them (they surface in the unmatched section instead).
    """
    if not genre_str or pd.isna(genre_str) or str(genre_str).strip() == "":
        return True  # genre-less tracks are never filtered out by family selection
    genres_lower = genre_str.lower()
    for fam in selected_fams:
        if fam == "Other":
            continue
        keywords = GENRE_FAMILIES.get(fam, [])
        if any(kw in genres_lower for kw in keywords):
            return True
    # No family matched — check if Other is selected (catches unrecognized genres)
    all_known_keywords = [kw for kws in GENRE_FAMILIES.values() for kw in kws]
    is_unrecognized = not any(kw in genres_lower for kw in all_known_keywords)
    if is_unrecognized and "Other" in selected_fams:
        return True
    return False


def _preview_filter(
    df: pd.DataFrame,
    playlists: list,
    decades: list,
    families: list,
    raw_genres: list,
    all_families_available: list | None = None,
) -> int:
    """Return track count after applying all filters. Zero-cost preview."""
    out = df[df["playlist_name"].isin(playlists)].copy() if playlists else df.copy()
    if decades and "decade" in out.columns:
        out = out[out["decade"].astype("Int64").astype(str).isin(decades)]
    if "artist_genres" in out.columns:
        if raw_genres:
            out = out[out["artist_genres"].apply(
                lambda g: any(rg in (g or "") for rg in raw_genres)
            )]
        elif all_families_available is not None and set(families) != set(all_families_available):
            out = out[out["artist_genres"].apply(
                lambda g: _track_matches_families(g, families)
            )]
    return len(out)

_BASE_LAYOUT = dict(
    plot_bgcolor="#121212",
    paper_bgcolor="#121212",
    font_color="#B3B3B3",
    margin=dict(t=20, b=20, l=10, r=10),
)

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


def cluster_card(rank: int, name: str, count: int, total: int,
                 energy: float, valence: float, danceability: float,
                 color: str, desc: str = "", feature_line: str = "") -> str:
    pct = count / total * 100 if total else 0
    badge = str(rank).zfill(2)
    desc_html = (
        f"<div style='color:#B3B3B3;font-size:0.78rem;margin-top:2px;'>{desc}</div>"
    ) if desc else ""
    return "".join([
        "<div style='background:#282828;border-radius:12px;padding:14px 18px;",
        "border:1px solid #333;margin-bottom:10px;'>",
        "<div style='display:flex;justify-content:space-between;align-items:center;'>",
        "<span style='color:#B3B3B3;font-size:0.85rem;font-weight:700;margin-right:10px;'>",
        badge + "</span>",
        "<span style='color:#FFFFFF;font-weight:700;font-size:0.95rem;flex:1;'>",
        name + "</span>",
        "<span style='color:" + color + ";font-weight:800;font-size:0.95rem;'>",
        str(count) + " tracks</span>",
        "</div>",
        desc_html,
        "<div style='margin-top:8px;background:#333;border-radius:4px;height:4px;'>",
        "<div style='width:" + f"{pct:.1f}" + "%;background:" + color,
        ";height:4px;border-radius:4px;'></div>",
        "</div>",
        "<div style='margin-top:6px;color:#B3B3B3;font-size:0.75rem;'>",
        feature_line if feature_line else f"Energy {energy:.2f} · Valence {valence:.2f} · Danceability {danceability:.2f} · {pct:.1f}% of selection",
        "</div>",
        "</div>",
    ])


def info_box(left_title: str, left_body: str,
             right_title: str = "", right_body: str = "") -> str:
    right = ""
    if right_title:
        right = "".join([
            "<div style='flex:1;min-width:200px;'>",
            "<span style='color:#B3B3B3;font-size:0.78rem;text-transform:uppercase;",
            "letter-spacing:0.06em;'>" + right_title + "</span>",
            "<p style='color:#FFFFFF;font-size:0.82rem;margin:4px 0 0;'>",
            right_body + "</p></div>",
        ])
    return "".join([
        "<div style='background:#1a1a1a;border:1px solid #333;border-radius:10px;",
        "padding:12px 16px;margin-bottom:16px;'>",
        "<div style='display:flex;gap:32px;flex-wrap:wrap;'>",
        "<div style='flex:1;min-width:200px;'>",
        "<span style='color:#B3B3B3;font-size:0.78rem;text-transform:uppercase;",
        "letter-spacing:0.06em;'>" + left_title + "</span>",
        "<p style='color:#FFFFFF;font-size:0.82rem;margin:4px 0 0;'>",
        left_body + "</p></div>",
        right,
        "</div></div>",
    ])


def hr(top: int = 24, bottom: int = 24) -> None:
    st.markdown(
        f"<hr style='border-color:#333;margin-top:{top}px;margin-bottom:{bottom}px;'>",
        unsafe_allow_html=True,
    )


def section_title(title: str, desc: str = "") -> None:
    st.markdown("## " + title)
    if desc:
        st.markdown(
            "<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>"
            + desc + "</p>",
            unsafe_allow_html=True,
        )


# ── Data & model loading ──────────────────────────────────────────────────────
@st.cache_data(show_spinner="Loading tracks...", ttl=300)
def load_data_fc() -> pd.DataFrame:
    return load_cluster_data().drop_duplicates(subset="track_id")

@st.cache_data(show_spinner=False, ttl=300)
def load_all_grouping_fc() -> pd.DataFrame:
    """All personal tracks regardless of audio features — cached for preview use."""
    from db.queries import load_all_tracks_for_grouping
    return load_all_tracks_for_grouping()

def load_data(mode: str = "") -> pd.DataFrame:
    if mode != "🔗 Your Collection":
        return load_data_fc()
    else:
        df = get_tracks()
        base_cols = [
            "track_id", "track_name", "artist_name", "artist_display", "playlist_name",
            "speechiness", "artist_genres", "decade", "release_year"
        ]
        feature_cols = [f for f in CLUSTER_FEATURES if f != "speechiness_log"]
        cols = base_cols + feature_cols
        available = [c for c in cols if c in df.columns]
        return df[available].drop_duplicates(subset="track_id")


_current_mode = st.session_state.get("mode", "🎵 Demo Collection")

# Clear stale playlist selection when mode switches
if st.session_state.get("_clusters_mode") != _current_mode:
    st.session_state["_clusters_mode"] = _current_mode
    st.session_state.pop("clusters_pl_filter_fc", None)
    st.session_state.pop("clusters_pl_filter_yc", None)
    st.session_state.pop("clustering_results", None)
    st.session_state.pop("selected_genres", None)
    st.session_state.pop("phase1", None)
    st.session_state.pop("clusters_decade_filter_fc", None)
    st.session_state.pop("clusters_decade_filter_yc", None)
    st.session_state.pop("clusters_genre_filter_fc", None)
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
    # load_cluster_progress running before this mode-switch clear.
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

df_all = load_data(mode=_current_mode)

# Build full YC pool (enriched + non-enriched) inline — _load_unmatched isn't defined yet.
# FC mode: _df_all_full == df_all (non-enriched tracks are handled by load_all_grouping_fc at each site).
def _rd_to_decade(rd: str) -> "int | None":
    """Derive decade (e.g. 2000) from a Spotify release_date string."""
    if not rd:
        return None
    try:
        y = int(str(rd)[:4])
        return y // 10 * 10 if 1900 < y < 2100 else None
    except (ValueError, TypeError):
        return None

if _current_mode == "🔗 Your Collection":
    _yc_ne_rows = [
        {
            "track_id":      t.get("id", ""),
            "track_name":    t.get("name", ""),
            "artist_name":   ", ".join(t.get("artists", [])) if isinstance(t.get("artists"), list) else t.get("artists", ""),
            "release_year":  t.get("release_date", "")[:4] if t.get("release_date") else "",
            "decade":        _rd_to_decade(t.get("release_date", "") or ""),
            "artist_genres": t.get("artist_genres", ""),
            "playlist_name": t.get("playlist_name", ""),
        }
        for t in st.session_state.get("uc_skipped", []) + st.session_state.get("uc_failed", [])
    ]
    _yc_ne = pd.DataFrame(_yc_ne_rows) if _yc_ne_rows else pd.DataFrame(
        columns=["track_id", "track_name", "artist_name", "release_year", "decade", "artist_genres", "playlist_name"]
    )
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
else:
    _df_all_full = df_all
    _yc_cross_dupes_total       = 0
    _yc_enriched_cross_dupes    = 0
    _yc_unenriched_cross_dupes  = 0

# Compute active (non-done) pools for filter options
_done_set_for_opts = st.session_state.get("done_tracks", set())
if _done_set_for_opts:
    # For playlists use the full track pool so a playlist with only non-enriched tracks
    # isn't prematurely hidden after some of its enriched tracks get marked done
    if _current_mode != "🔗 Your Collection":
        _pool_pl = load_all_grouping_fc()
        _pool_pl = _pool_pl[~_pool_pl["track_id"].isin(_done_set_for_opts)]
    else:
        _pool_pl = _df_all_full[~_df_all_full["track_id"].isin(_done_set_for_opts)]
    _df_for_opts = df_all[~df_all["track_id"].isin(_done_set_for_opts)]
else:
    _pool_pl = _df_all_full  # YC: all playlists visible; FC: same as df_all
    _df_for_opts = df_all

all_playlists = sorted(_pool_pl["playlist_name"].unique().tolist())

# Compute total collection size once — used by progress bar and no-features note
try:
    if _current_mode != "🔗 Your Collection":
        from db.queries import load_all_tracks
        _total_collection_size = len(load_all_tracks().drop_duplicates("track_id"))
    else:
        # Use unique track count (not raw list lengths) so cross-playlist duplicates
        # don't inflate the denominator and prevent reaching 100%.
        _total_collection_size = _n_unique_all
except Exception:
    _total_collection_size = len(df_all)

_pl_key = "clusters_pl_filter_fc" if _current_mode != "🔗 Your Collection" else "clusters_pl_filter_yc"
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

# ── KMeans runner ─────────────────────────────────────────────────────────────
def _make_names(centroids_raw: pd.DataFrame, k: int) -> dict:
    """
    Names clusters using energy tier as the fixed primary axis, then picks the
    single most z-score-distinctive non-energy feature as a differentiator.
    This avoids "Happy · Danceable" vs "Danceable · Happy" order collisions.
    k ≤ 5: named. k > 5: numbered with audio subtitles.
    """
    global_mean = centroids_raw.mean()
    global_std  = centroids_raw.std().replace(0, 1)
    z_scores    = (centroids_raw - global_mean) / global_std

    def _energy_tier(val: float) -> str:
        if val > 0.65: return "high"
        if val < 0.45: return "low"
        return "mid"

    # Human-readable names keyed by (energy_tier, differentiator)
    _VOCAB: dict[tuple, str] = {
        ("high", "upbeat"):   "Euphoric Bangers",
        ("high", "dark"):     "Intense Drive",
        ("high", "acoustic"): "Energetic Acoustic",
        ("high", "groovy"):   "Club Anthems",
        ("high", "hip-hop"):  "Hip-Hop Hype",
        ("high", "fast"):     "Full Throttle",
        ("high", "subdued"):  "Raw Energy",
        ("high", None):       "High Energy",
        ("mid",  "upbeat"):   "Feel-Good Vibes",
        ("mid",  "dark"):     "Moody Tunes",
        ("mid",  "acoustic"): "Acoustic Sessions",
        ("mid",  "groovy"):   "Groove Mix",
        ("mid",  "hip-hop"):  "Hip-Hop Flow",
        ("mid",  "fast"):     "Mid-Tempo Rush",
        ("mid",  "subdued"):  "Understated Cool",
        ("mid",  None):       "Everyday Mix",
        ("low",  "upbeat"):   "Chill & Happy",
        ("low",  "dark"):     "Melancholic",
        ("low",  "acoustic"): "Acoustic Ballads",
        ("low",  "groovy"):   "Smooth Grooves",
        ("low",  "hip-hop"):  "Lo-Fi Hip-Hop",
        ("low",  "fast"):     "Slow Burn",
        ("low",  "subdued"):  "Introspective",
        ("low",  None):       "Mellow",
    }

    def _differentiators(i: int) -> list[str]:
        """Ordered list of differentiator keys for cluster i by |z-score| (energy excluded)."""
        row    = centroids_raw.iloc[i]
        feat_z = z_scores.iloc[i].drop("energy", errors="ignore").abs().sort_values(ascending=False)
        out: list[str] = []
        for feat in feat_z.index:
            val = float(row[feat])
            key: str | None = None
            if   feat == "valence":
                if val > 0.6:   key = "upbeat"
                elif val < 0.4: key = "dark"
            elif feat == "acousticness":
                if val > 0.5:   key = "acoustic"
            elif feat == "danceability":
                if val > 0.65:  key = "groovy"
                elif val < 0.4: key = "subdued"
            elif feat == "speechiness_log":
                if val > 0.25:  key = "hip-hop"
            elif feat == "tempo":
                if val > 130:   key = "fast"
                elif val < 90:  key = "slow"
            if key and key not in out:
                out.append(key)
        return out

    tiers = [_energy_tier(float(centroids_raw.iloc[i]["energy"])) for i in range(k)]
    diffs = [_differentiators(i) for i in range(k)]
    names = [
        _VOCAB.get((tiers[i], diffs[i][0] if diffs[i] else None),
                   _VOCAB[(tiers[i], None)])
        for i in range(k)
    ]

    # Pass 1: collision → extend with next available differentiator
    for i in range(k):
        if names.count(names[i]) > 1:
            for extra in diffs[i][1:]:
                candidate = f"{names[i]} · {extra.title()}"
                if names.count(candidate) == 0:
                    names[i] = candidate
                    break

    # Pass 2: still colliding → append energy value as numeric tiebreaker
    for i in range(k):
        if names.count(names[i]) > 1:
            names[i] = f"{names[i]} ({float(centroids_raw.iloc[i]['energy']):.2f})"

    if k <= 5:
        return {i: names[i] for i in range(k)}
    else:
        st.session_state["cluster_descriptions"] = {i: names[i] for i in range(k)}
        return {i: f"Playlist {i + 1}" for i in range(k)}


def _verbose_description(energy: float, valence: float, danceability: float,
                          acousticness: float = 0, tempo: float = 0) -> str:
    """Convert audio feature values to a human-readable sentence."""
    parts = []

    # Energy
    if energy > 0.65:
        parts.append("high energy")
    elif energy < 0.45:
        parts.append("low energy")
    else:
        parts.append("mid energy")

    # Acousticness
    if acousticness > 0.5:
        parts.append("acoustic")
    else:
        parts.append("electric")

    # Valence
    if valence > 0.6:
        parts.append("happy and uplifting")
    elif valence < 0.4:
        parts.append("dark and melancholic")
    else:
        parts.append("emotionally neutral")

    # Danceability
    if danceability > 0.65:
        parts.append("very danceable")
    elif danceability < 0.4:
        parts.append("not particularly danceable")

    # Tempo
    if tempo > 130:
        parts.append("fast tempo")
    elif tempo < 90:
        parts.append("slow tempo")

    if not parts:
        return "Mixed audio profile."

    # Build sentence
    return "Songs that are " + ", ".join(parts[:-1]) + (
        f" and {parts[-1]}." if len(parts) > 1 else f"{parts[0]}."
    )


@st.cache_data(show_spinner=False)
def run_kmeans(track_ids_tuple: tuple, k: int):
    """
    Returns:
        df_clust        — tracks with cluster, cluster_name, PC1, PC2
        name_map        — {int → str}
        centroids_norm  — DataFrame(k × radar_features), StandardScaler space
        var1, var2      — PCA variance explained (%)
    """
    df_sub   = df_all[df_all["track_id"].isin(set(track_ids_tuple))].copy()
    df_sub = df_sub.copy()
    if "speechiness" in df_sub.columns and "speechiness_log" not in df_sub.columns:
        df_sub["speechiness_log"] = np.log1p(df_sub["speechiness"])
    X        = df_sub[CLUSTER_FEATURES].values
    scaler   = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    km                = KMeans(n_clusters=k, random_state=42, n_init=10)
    df_sub["cluster"] = km.fit_predict(X_scaled)

    # PCA for visualization (always 2 components)
    pca        = PCA(n_components=2, random_state=42)
    coords     = pca.fit_transform(X_scaled)
    # Flip axes so the dominant feature always loads positively — makes labels intuitive
    if pca.components_[0][np.abs(pca.components_[0]).argmax()] < 0:
        coords[:, 0] *= -1
    if pca.components_[1][np.abs(pca.components_[1]).argmax()] < 0:
        coords[:, 1] *= -1
    df_sub["PC1"] = coords[:, 0]
    df_sub["PC2"] = coords[:, 1]
    var1 = float(pca.explained_variance_ratio_[0] * 100)
    var2 = float(pca.explained_variance_ratio_[1] * 100)
    label1 = CLUSTER_FEATURES[int(np.abs(pca.components_[0]).argmax())]
    label2 = CLUSTER_FEATURES[int(np.abs(pca.components_[1]).argmax())]

    # Inverse-transform ALL features back to original space for accurate naming
    centroids_raw = pd.DataFrame(
        scaler.inverse_transform(km.cluster_centers_),
        columns=CLUSTER_FEATURES,
    )

    name_map = _make_names(centroids_raw, k)
    df_sub["cluster_name"] = df_sub["cluster"].map(name_map)

    # Centroids in StandardScaler space (for radar — radar features only)
    centroids_scaled = pd.DataFrame(km.cluster_centers_, columns=CLUSTER_FEATURES)

    return df_sub, name_map, centroids_scaled, var1, var2, scaler, label1, label2


def run_category_grouping(
    df: pd.DataFrame,
    group_by_decade: bool,
    group_by_genre: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Groups tracks by genre family and/or decade. Returns (df_clustered, df_unmatched).
    Tracks missing any required grouping dimension go to df_unmatched for manual assignment."""
    df = df.copy()
    if "release_year" not in df.columns:
        df["release_year"] = ""
    if "artist_display" not in df.columns:
        df["artist_display"] = df.get("artist_name", "")
    for _audio_col in ["energy", "valence", "danceability", "acousticness", "tempo", "speechiness"]:
        if _audio_col not in df.columns:
            df[_audio_col] = float("nan")

    if group_by_genre and "artist_genres" in df.columns:
        df["_genre_group"] = df["artist_genres"].apply(
            lambda g: "Unknown Genre" if (not g or pd.isna(g) or str(g).strip() == "")
            else _assign_family(g)[0]
        )
    else:
        df["_genre_group"] = None

    if group_by_decade and "decade" in df.columns:
        df["_decade_group"] = df["decade"].apply(
            lambda d: f"{int(d)}s" if pd.notna(d) else "Unknown Decade"
        )
    else:
        df["_decade_group"] = None

    # Tracks missing any required grouping field go to manual assignment
    _unmatched_mask = pd.Series(False, index=df.index)
    if group_by_genre:
        _unmatched_mask |= (df["_genre_group"] == "Unknown Genre")
    if group_by_decade:
        _unmatched_mask |= (df["_decade_group"] == "Unknown Decade")

    df_unmatched = df[_unmatched_mask].copy()
    df = df[~_unmatched_mask].copy()

    def _build_name(row):
        parts = []
        if group_by_genre and row["_genre_group"]:
            parts.append(row["_genre_group"])
        if group_by_decade and row["_decade_group"]:
            parts.append(row["_decade_group"])
        return " · ".join(parts) if parts else "Ungrouped"

    df["cluster_name"] = df.apply(_build_name, axis=1)
    unique_names = sorted(df["cluster_name"].unique())
    name_to_idx = {n: i for i, n in enumerate(unique_names)}
    df["cluster"] = df["cluster_name"].map(name_to_idx)
    df["PC1"] = 0.0
    df["PC2"] = 0.0
    return df, df_unmatched


def run_specific_genre_grouping(
    df: pd.DataFrame,
    selected_genres: list,
    group_by_decade: bool,
) -> pd.DataFrame:
    """One cluster per selected genre. A track appears in every cluster whose genre tag it carries.
    Tracks matching no selected genre are silently excluded — no unmatched section."""
    df = df.copy()
    if "release_year" not in df.columns:
        df["release_year"] = ""
    if "artist_display" not in df.columns:
        df["artist_display"] = df.get("artist_name", "")
    for _audio_col in ["energy", "valence", "danceability", "acousticness", "tempo", "speechiness"]:
        if _audio_col not in df.columns:
            df[_audio_col] = float("nan")

    chunks = []
    for genre in selected_genres:
        matching = df[df["artist_genres"].apply(
            lambda g: genre in {t.strip() for t in (g or "").split(",")}
        )].copy()
        if matching.empty:
            continue
        if group_by_decade and "decade" in matching.columns:
            matching["cluster_name"] = genre + " · " + matching["decade"].apply(
                lambda d: f"{int(d)}s" if pd.notna(d) else "Unknown"
            )
        else:
            matching["cluster_name"] = genre
        chunks.append(matching)

    if not chunks:
        df_clust = pd.DataFrame()
    else:
        df_clust = pd.concat(chunks, ignore_index=True)
        unique_names = sorted(df_clust["cluster_name"].unique())
        name_to_idx = {n: i for i, n in enumerate(unique_names)}
        df_clust["cluster"] = df_clust["cluster_name"].map(name_to_idx)
        df_clust["PC1"] = 0.0
        df_clust["PC2"] = 0.0
    return df_clust


@st.cache_data(show_spinner=False)
def compute_k_metrics(track_ids_tuple: tuple) -> pd.DataFrame:
    from sklearn.metrics import silhouette_score
    df_sub = df_all[df_all["track_id"].isin(set(track_ids_tuple))].copy()
    if "speechiness" in df_sub.columns and "speechiness_log" not in df_sub.columns:
        df_sub["speechiness_log"] = np.log1p(df_sub["speechiness"])
    X = df_sub[CLUSTER_FEATURES].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    rows = []
    k_range = range(2, min(11, len(df_sub)))
    for k_i in k_range:
        km_i = KMeans(n_clusters=k_i, random_state=42, n_init=10)
        labels = km_i.fit_predict(X_scaled)
        sil = silhouette_score(X_scaled, labels) if k_i > 1 else 0.0
        rows.append({"k": k_i, "inertia": km_i.inertia_, "silhouette": sil})
    return pd.DataFrame(rows)


def _best_k(metrics_df: pd.DataFrame) -> tuple[int, int]:
    """Returns (best_k_silhouette, best_k_elbow)."""
    best_sil = int(metrics_df.loc[metrics_df["silhouette"].idxmax(), "k"])

    # Elbow: largest second derivative of inertia
    # Requires at least 4 points (k=2..5) to compute second derivative
    inertias = metrics_df["inertia"].values
    if len(inertias) >= 4:
        deltas = np.diff(inertias)
        second_deltas = np.diff(deltas)
        best_elbow = int(metrics_df["k"].iloc[second_deltas.argmin() + 2])
    else:
        best_elbow = best_sil  # fall back to silhouette when not enough points

    return best_sil, best_elbow


@st.cache_data(show_spinner=False)
def _load_unmatched_fc() -> pd.DataFrame:
    return load_unmatched_tracks()

def _load_unmatched(mode: str) -> pd.DataFrame:
    if mode != "🔗 Your Collection":
        return _load_unmatched_fc()
    else:
        skipped = st.session_state.get("uc_skipped", [])
        failed  = st.session_state.get("uc_failed", [])
        rows = []
        for t in skipped + failed:
            rows.append({
                "track_id":      t.get("id", ""),
                "track_name":    t.get("name", ""),
                "artist_name":   ", ".join(t.get("artists", [])) if isinstance(t.get("artists"), list) else t.get("artists", ""),
                "release_year":  t.get("release_date", "")[:4] if t.get("release_date") else "",
                "artist_genres": t.get("artist_genres", ""),
                "playlist_name": t.get("playlist_name", ""),
            })
        df = pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["track_id", "track_name", "artist_name", "release_year", "artist_genres", "playlist_name"]
        )
        return _add_artist_display(df)


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
if _current_mode == "🔗 Your Collection":
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
                _all_pool_ids = (
                    set(load_all_grouping_fc()["track_id"])
                    if _current_mode != "🔗 Your Collection"
                    else set(_df_all_full["track_id"])
                )
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
        if _current_mode == "🔗 Your Collection":
            _skip_note = (
                f"ℹ️ {_remaining:,} track(s) have no audio features and couldn't be clustered — "
                f"use the Unmatched Tracks section after running to assign them manually, "
                f"or skip them with the button above."
            )
        else:
            _skip_note = (
                f"ℹ️ {_remaining:,} track(s) were never clustered — they were excluded by filters "
                f"(genre family, decade, or playlist) in all previous runs. "
                f"Adjust filters to cluster them, or skip them with the button above."
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

if _current_mode != "🔗 Your Collection":
    if st.button("🔄 Refresh track library", key="refresh_library", help="Reload tracks from DB — use after adding new playlists"):
        load_data_fc.clear()
        load_all_grouping_fc.clear()
        st.rerun()

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
        _decade_key = "clusters_decade_filter_fc" if _current_mode != "🔗 Your Collection" else "clusters_decade_filter_yc"
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
        _genre_key = "clusters_genre_filter_fc" if _current_mode != "🔗 Your Collection" else "clusters_genre_filter_yc"
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
    if _current_mode != "🔗 Your Collection":
        _ginfo_pool = load_all_grouping_fc()
        _ginfo_pool = _ginfo_pool[_ginfo_pool["playlist_name"].isin(_info_pl_now)]
    else:
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
    if _current_mode != "🔗 Your Collection":
        _sgl_pool = load_all_grouping_fc()
        _sgl_pool = _sgl_pool[_sgl_pool["playlist_name"].isin(_sgl_pl)]
    else:
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
elif _grouping_mode_current == "🗂️ By category" and _current_mode != "🔗 Your Collection":
    # Category mode — use full track pool including unmatched
    _cat_df = load_all_grouping_fc()
    _cat_pl = st.session_state.get(_pl_key, all_playlists)
    _cat_filtered = _cat_df[_cat_df["playlist_name"].isin(_cat_pl)].copy()
    # Apply decade filter
    if selected_decades and "decade" in _cat_filtered.columns:
        _cat_filtered = _cat_filtered[
            _cat_filtered["decade"].astype("Int64").astype(str).isin(selected_decades)
        ]
    # Apply genre filter — empty list means "no families selected → 0 tracks"
    if "artist_genres" in _cat_filtered.columns and set(selected_families) != set(all_families_available):
        _cat_filtered = _cat_filtered[
            _cat_filtered["artist_genres"].apply(
                lambda g: _track_matches_families(g, selected_families)
            )
        ]
    # Exclude done tracks
    _done_set = st.session_state.get("done_tracks", set())
    if _done_set:
        _cat_filtered = _cat_filtered[~_cat_filtered["track_id"].isin(_done_set)]
    # Tracks that will go to unmatched in run_category_grouping (mirrors its logic exactly)
    _cat_um_mask = pd.Series(False, index=_cat_filtered.index)
    if group_by_genre and "artist_genres" in _cat_filtered.columns:
        _cat_um_mask |= (_cat_filtered["artist_genres"].isna() | (_cat_filtered["artist_genres"].str.strip() == ""))
    if group_by_decade and "decade" in _cat_filtered.columns:
        _cat_um_mask |= _cat_filtered["decade"].isna()
    _n_unmatched_cat = int(_cat_filtered[_cat_um_mask]["track_id"].nunique())
    _n_no_af_cat     = int(_cat_filtered[~_cat_filtered["track_id"].isin(set(df_all["track_id"]))]["track_id"].nunique())
    _prev_count      = _cat_filtered["track_id"].nunique() - _n_unmatched_cat

elif _grouping_mode_current == "🗂️ By category" and _current_mode == "🔗 Your Collection":
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
        if _current_mode != "🔗 Your Collection":
            _sgl_preview_pool = load_all_grouping_fc()
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
    if _current_mode != "🔗 Your Collection":
        _unmatched_preview = _load_unmatched_fc()
        _unmatched_preview = _unmatched_preview[
            _unmatched_preview["playlist_name"].isin(_pl_now)
        ].drop_duplicates(subset="track_id")
        # load_unmatched_tracks() returns release_year, not decade — derive it
        if selected_decades and "release_year" in _unmatched_preview.columns:
            _unmatched_preview["_d"] = (
                pd.to_numeric(_unmatched_preview["release_year"], errors="coerce")
                .dropna().astype(int) // 10 * 10
            ).astype("Int64").astype(str)
            _unmatched_preview = _unmatched_preview[
                _unmatched_preview["_d"].isin(selected_decades)
            ].drop(columns=["_d"])
        if "artist_genres" in _unmatched_preview.columns and set(selected_families) != set(all_families_available):
            _unmatched_preview = _unmatched_preview[_unmatched_preview["artist_genres"].apply(
                lambda g: _track_matches_families(g, selected_families)
            )]
        if _manual_assigned_ids:
            _unmatched_preview = _unmatched_preview[
                ~_unmatched_preview["track_id"].isin(_manual_assigned_ids)
            ]
        _n_unmatched_preview = len(_unmatched_preview)
    else:
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

        if _current_mode != "🔗 Your Collection":
            from db.queries import load_all_tracks_for_grouping
            df_all_for_grouping = load_all_tracks_for_grouping()
            df_for_grouping = df_all_for_grouping[
                df_all_for_grouping["playlist_name"].isin(selected_playlists)
            ].copy()
            if selected_decades and "decade" in df_for_grouping.columns:
                df_for_grouping = df_for_grouping[
                    df_for_grouping["decade"].astype("Int64").astype(str).isin(selected_decades)
                ]
            if "artist_genres" in df_for_grouping.columns and set(selected_families) != set(all_families_available):
                df_for_grouping = df_for_grouping[df_for_grouping["artist_genres"].apply(
                    lambda g: _track_matches_families(g, selected_families)
                )]
        else:
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
        st.session_state.pop("cluster_descriptions", None)
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
        if os.getenv("DEV_MODE") != "1":
            try:
                from db.queries import track_event as _te
                _cr = st.session_state["clustering_results"]
                _te("clustering_run", page="My Clusters",
                    session_id=st.session_state.get("uc_session_id", "fc_user"),
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

        if _current_mode != "🔗 Your Collection":
            from db.queries import load_all_tracks_for_grouping
            df_for_sgl = load_all_tracks_for_grouping()
            df_for_sgl = df_for_sgl[df_for_sgl["playlist_name"].isin(selected_playlists)].copy()
        else:
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
        st.session_state.pop("cluster_descriptions", None)
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
        if os.getenv("DEV_MODE") != "1":
            try:
                from db.queries import track_event as _te
                _cr = st.session_state["clustering_results"]
                _te("clustering_run", page="My Clusters",
                    session_id=st.session_state.get("uc_session_id", "fc_user"),
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
        _unmatched_pre = _load_unmatched(_current_mode)
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
            metrics_df = compute_k_metrics(track_ids)
        best_k_sil, best_k_elbow = _best_k(metrics_df)

        if k_mode == "Manual" and k_manual is not None:
            optimal_k  = k_manual
            fc_override = False
        else:
            optimal_k  = best_k_sil
            fc_override = False

        with st.spinner("Clustering..."):
            results = run_kmeans(track_ids, optimal_k)

        st.session_state.pop("unmatched_assignments", None)
        st.session_state.pop("unmatched_save_status", None)
        st.session_state.pop("cluster_descriptions", None)
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
        if os.getenv("DEV_MODE") != "1":
            try:
                from db.queries import track_event as _te
                _cr = st.session_state["clustering_results"]
                _te("clustering_run", page="My Clusters",
                    session_id=st.session_state.get("uc_session_id", "fc_user"),
                    visitor_id=st.session_state.get("visitor_id"),
                    properties={"mode": "KMeans", "k": _cr["k"],
                                "n_tracks": _cr["n_tracks"],
                                "n_playlists": len(_cr["selected_playlists"])})
            except Exception:
                pass
        st.switch_page("pages/_Cluster_Results.py")

