import os
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

from config import CLUSTER_FEATURES
from db.queries import (
    load_unmatched_tracks, _add_artist_display,
    load_cluster_progress, save_cluster_progress, save_cluster_progress_bulk,
)
from spotify_client import render_export_to_spotify
from utils import inject_global_css, check_collection_mode


inject_global_css()
if not check_collection_mode():
    st.stop()


# ── Constants ─────────────────────────────────────────────────────────────────
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

_RADAR_FEATURES = [f for f in CLUSTER_FEATURES if f != "tempo"]

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
        "border:1px solid #333;height:100%;margin-bottom:8px;'>",
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


def _verbose_description(energy: float, valence: float, danceability: float,
                          acousticness: float = 0, tempo: float = 0) -> str:
    parts = []
    if energy > 0.65:
        parts.append("high energy")
    elif energy < 0.45:
        parts.append("low energy")
    else:
        parts.append("mid energy")
    if acousticness > 0.5:
        parts.append("acoustic")
    else:
        parts.append("electric")
    if valence > 0.6:
        parts.append("happy and uplifting")
    elif valence < 0.4:
        parts.append("dark and melancholic")
    else:
        parts.append("emotionally neutral")
    if danceability > 0.65:
        parts.append("very danceable")
    elif danceability < 0.4:
        parts.append("not particularly danceable")
    if tempo > 130:
        parts.append("fast tempo")
    elif tempo < 90:
        parts.append("slow tempo")
    if not parts:
        return "Mixed audio profile."
    return "Songs that are " + ", ".join(parts[:-1]) + (
        f" and {parts[-1]}." if len(parts) > 1 else f"{parts[0]}."
    )


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


# ── Guard — redirect if no results ───────────────────────────────────────────
if "clustering_results" not in st.session_state:
    st.warning("No clustering results found. Run clustering first.")
    if st.button("← Go to My Clusters"):
        st.switch_page("pages/6_My_Clusters.py")
    st.stop()

# ── Unpack results ────────────────────────────────────────────────────────────
r                = st.session_state["clustering_results"]
df_clust         = r["df_clust"]
name_map         = r["name_map"]
centroids_scaled = r["centroids_scaled"]
var1             = r["var1"]
var2             = r["var2"]
scaler_used      = r["scaler_used"]
pc1_label        = r["pc1_label"]
pc2_label        = r["pc2_label"]
metrics_df       = r["metrics_df"]
best_k_sil       = r["best_k_sil"]
best_k_elbow     = r["best_k_elbow"]
optimal_k        = r["optimal_k"]
fc_override      = r["fc_override"]
n_tracks         = r["n_tracks"]
selected_playlists = r["selected_playlists"]
k                = r["k"]
k_mode           = r["k_mode"]
track_ids        = r.get("track_ids", ())
grouping_mode    = r.get("grouping_mode", "🔬 By audio similarity (KMeans)")
group_by_decade  = r.get("group_by_decade", True)
group_by_genre   = r.get("group_by_genre", True)
_is_category_mode = grouping_mode == "🗂️ By category"
_is_sgl_mode      = grouping_mode == "🏷️ By specific genre"
_current_mode    = st.session_state.get("mode", "🎵 Facu's Collection")
df_unmatched_cat = r.get("df_unmatched_cat", pd.DataFrame())

# Human-readable label for the grouping dimensions used in category mode
_grp_dim_parts = []
if _is_category_mode:
    if r.get("group_by_genre", True):
        _grp_dim_parts.append("genre")
    if r.get("group_by_decade", True):
        _grp_dim_parts.append("release decade")
_grp_dim_str = " or ".join(_grp_dim_parts) if _grp_dim_parts else "grouping data"

# ── user_key ──────────────────────────────────────────────────────────────────
user_key = (
    st.session_state.get("uc_session_id", "anonymous")
    if _current_mode == "🔗 Your Collection"
    else "facu"
)


def _track(event: str, **props):
    """Fire-and-forget analytics event — never breaks the page."""
    if os.getenv("DEV_MODE") == "1":
        return
    try:
        from db.queries import track_event
        track_event(
            event      = event,
            page       = "Cluster Results",
            session_id = user_key,
            visitor_id = st.session_state.get("visitor_id"),
            properties = props or None,
        )
    except Exception:
        pass

# ── Restore progress ──────────────────────────────────────────────────────────
try:
    _progress = load_cluster_progress(user_key)
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

# Validate assignments against current name_map — accept both plain ("Euphoric Bangers")
# and prefixed ("1. Euphoric Bangers") formats since selectbox stores the prefixed form
_valid_cluster_names = (
    set(name_map.values())
    | {f"{i+1}. {name_map[i]}" for i in range(k)}
    | {"— unassigned —"}
)
_current_assignments = st.session_state.get("unmatched_assignments", {})
_validated = {
    tid: cname if cname in _valid_cluster_names else "— unassigned —"
    for tid, cname in _current_assignments.items()
}
if _validated != _current_assignments:
    st.session_state["unmatched_assignments"] = _validated

# ── Color maps ────────────────────────────────────────────────────────────────
int_to_color  = {i: _DYN_PALETTE[i % len(_DYN_PALETTE)] for i in range(k)}
name_to_color = {name_map[i]: int_to_color[i] for i in range(k)}
pl_color_map  = {
    pl: _DYN_PALETTE[i % len(_DYN_PALETTE)]
    for i, pl in enumerate(sorted(selected_playlists))
}

# ── Completion check ──────────────────────────────────────────────────────────
_all_track_ids = set(track_ids)
_done_tracks = st.session_state.get("done_tracks", set())
_keep_visible = st.session_state.get("keep_visible", {})
_all_done = bool(_all_track_ids) and _all_track_ids.issubset(_done_tracks)

# ── HEADER ────────────────────────────────────────────────────────────────────
_method_label = (
    "By Category" if _is_category_mode
    else "By Specific Genre" if _is_sgl_mode
    else f"KMeans k={k}"
)
_filter_summary = []
_total_playlists_available = r.get("total_playlists", len(selected_playlists))
if len(selected_playlists) < _total_playlists_available:
    _filter_summary.append(f"{len(selected_playlists)} playlists")
if r.get("selected_decades") and len(r["selected_decades"]) < len(r.get("decade_options", [])):
    _filter_summary.append(f"{len(r['selected_decades'])} decades")
_filter_str = " · ".join(_filter_summary) if _filter_summary else "all tracks"

# Compute unmatched count for header — reads from pre-built filtered DF
# (same playlist/decade/family filters already applied at submission time)
_n_unmatched_hdr = 0
_um_hdr = df_unmatched_cat.copy() if not df_unmatched_cat.empty else pd.DataFrame()
if not _um_hdr.empty:
    _done_hdr = st.session_state.get("done_tracks", set())
    if _done_hdr:
        _um_hdr = _um_hdr[~_um_hdr["track_id"].isin(_done_hdr)]
    _n_unmatched_hdr = _um_hdr["track_id"].nunique()

if _n_unmatched_hdr > 0:
    if _is_sgl_mode:
        _matched_label   = f"{n_tracks:,} matched"
        _unmatched_label = f"{_n_unmatched_hdr:,} with no genre match"
    elif _is_category_mode:
        _matched_label   = f"{n_tracks:,} grouped"
        _unmatched_label = f"{_n_unmatched_hdr:,} unmatched"
    else:
        _matched_label   = f"{n_tracks:,} with audio features"
        _unmatched_label = f"{_n_unmatched_hdr:,} without"
    _tracks_label = (
        f"{_matched_label} · "
        f"<span style='color:#F5A623;'>{_unmatched_label}</span> "
        f"<span style='color:#888;font-size:0.82rem;'>(assign manually below)</span>"
        f" · {k} clusters"
    )
else:
    _tracks_label = f"{n_tracks:,} tracks · {k} clusters"

st.markdown(
    f"<div style='display:flex;align-items:center;justify-content:space-between;"
    f"margin-bottom:4px;'>"
    f"<h1 style='margin:0;'>Cluster Results</h1>"
    f"</div>"
    f"<p style='color:#B3B3B3;font-size:0.88rem;margin-top:4px;'>"
    f"{_method_label} · {_filter_str} · {_tracks_label}</p>",
    unsafe_allow_html=True,
)

if not _all_done:
    if st.button("← Reconfigure", key="back_to_configure"):
        st.switch_page("pages/6_My_Clusters.py")

hr(top=12, bottom=20)

# ── COMPLETION BANNER ─────────────────────────────────────────────────────────
if _all_done:
    st.markdown(
        "<div style='background:#1a2e1a;border:1px solid #1DB954;border-radius:12px;"
        "padding:14px 20px;margin-bottom:20px;display:flex;align-items:center;gap:12px;'>"
        "<span style='font-size:1.4rem;'>🎉</span>"
        "<span style='color:#1DB954;font-weight:800;font-size:1rem;'>"
        "All clusters marked as done — scroll down to wrap up.</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    hr(top=0, bottom=0)

# ── OPTIMAL K CALLOUT (KMeans only) ──────────────────────────────────────────
if not _is_category_mode and not _is_sgl_mode:
    _k_above_optimal = (
        k_mode == "Manual"
        and best_k_sil is not None
        and k > best_k_sil
    )

    if k_mode == "Manual":
        if _k_above_optimal:
            _callout = (
                f"Manual override: <b>k={k}</b> · "
                f"Silhouette suggests <b>k={best_k_sil}</b> — "
                f"at k={k} some clusters may sound similar or redundant. "
                f"This is expected when choosing more clusters than the data supports."
            )
        else:
            _callout = f"Manual override: <b>k={k}</b>."
    elif metrics_df is not None:
        _agree = best_k_sil == best_k_elbow
        if _agree:
            _callout = f"Both metrics agree: <b>k={best_k_sil}</b> is optimal."
        else:
            _callout = (
                f"Silhouette suggests <b>k={best_k_sil}</b> · "
                f"Elbow suggests <b>k={best_k_elbow}</b> · "
                f"Defaulting to silhouette (<b>k={best_k_sil}</b>)."
            )
    else:
        _callout = f"k={k}"

    _callout_border = "#F5A623" if _k_above_optimal else "#1DB954"
    _callout_icon   = "⚠️ Heads up" if _k_above_optimal else "🎯 Optimal k"
    st.markdown(
        f"<div style='background:#1a1a1a;border:1px solid {_callout_border};border-radius:10px;"
        f"padding:12px 18px;margin-bottom:16px;'>"
        f"<span style='color:{_callout_border};font-weight:700;'>{_callout_icon} — </span>"
        f"<span style='color:#FFFFFF;font-size:0.88rem;'>{_callout}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div style='background:#1a1a1a;border:1px solid #444;border-radius:10px;"
        "padding:11px 16px;margin-bottom:14px;display:flex;align-items:flex-start;gap:10px;'>"
        "<span style='font-size:1rem;margin-top:1px;'>ℹ️</span>"
        "<span style='color:#B3B3B3;font-size:0.83rem;line-height:1.55;'>"
        "<b style='color:#FFFFFF;'>Cluster names are approximate.</b> "
        "They're generated from audio patterns — energy, valence, danceability — "
        "not genre tags. A track can land in a cluster whose name seems off "
        "(e.g. a hard rock song in &ldquo;Hip-Hop Hype&rdquo;) if it shares a similar sonic profile. "
        "Use the name as a rough vibe, not a genre label.</span>"
        "</div>",
        unsafe_allow_html=True,
    )

    if metrics_df is not None:
        with st.expander("📊 How was optimal k chosen? — Silhouette & Elbow explained"):
            st.markdown("""
**Silhouette score** measures how well each track fits its own cluster compared to the nearest
neighbouring cluster. Score ranges from -1 to 1 — higher is better.

**Elbow method** looks at inertia (sum of squared distances from each track to its cluster
centroid). The "elbow" is where adding more clusters stops being worth it.

**Which to trust?** Silhouette is more rigorous. When they disagree, silhouette is the better guide.
            """)
            _met_left, _met_right = st.columns(2)
            with _met_left:
                _fig_sil = go.Figure()
                _fig_sil.add_trace(go.Scatter(
                    x=metrics_df["k"], y=metrics_df["silhouette"],
                    mode="lines+markers",
                    line=dict(color="#1DB954", width=2),
                    marker=dict(size=7, color=[
                        "#1DB954" if ki == best_k_sil else "#B3B3B3"
                        for ki in metrics_df["k"]
                    ]),
                    hovertemplate="k=%{x}<br>Silhouette=%{y:.3f}<extra></extra>",
                ))
                _fig_sil.add_vline(x=best_k_sil, line_dash="dot", line_color="#1DB954")
                _fig_sil.update_layout(
                    **{**_BASE_LAYOUT, "margin": dict(t=30, b=30, l=40, r=20)},
                    title=dict(text="Silhouette Score", font=dict(color="#FFFFFF", size=13)),
                    xaxis=dict(title="k", gridcolor="#282828", tickfont=dict(color="#B3B3B3")),
                    yaxis=dict(title="Score", gridcolor="#282828", tickfont=dict(color="#B3B3B3")),
                    height=280,
                )
                st.plotly_chart(_fig_sil, use_container_width=True)
            with _met_right:
                _fig_elbow = go.Figure()
                _fig_elbow.add_trace(go.Scatter(
                    x=metrics_df["k"], y=metrics_df["inertia"],
                    mode="lines+markers",
                    line=dict(color="#4A90D9", width=2),
                    marker=dict(size=7, color=[
                        "#4A90D9" if ki == best_k_elbow else "#B3B3B3"
                        for ki in metrics_df["k"]
                    ]),
                    hovertemplate="k=%{x}<br>Inertia=%{y:,.0f}<extra></extra>",
                ))
                _fig_elbow.add_vline(x=best_k_elbow, line_dash="dot", line_color="#4A90D9")
                _fig_elbow.update_layout(
                    **{**_BASE_LAYOUT, "margin": dict(t=30, b=30, l=40, r=20)},
                    title=dict(text="Elbow Curve", font=dict(color="#FFFFFF", size=13)),
                    xaxis=dict(title="k", gridcolor="#282828", tickfont=dict(color="#B3B3B3")),
                    yaxis=dict(title="Inertia", gridcolor="#282828", tickfont=dict(color="#B3B3B3")),
                    height=280,
                )
                st.plotly_chart(_fig_elbow, use_container_width=True)
    hr()

# ── CLUSTER OVERVIEW ──────────────────────────────────────────────────────────
section_title("Cluster Overview")

if k > 5 and not _is_category_mode and not _is_sgl_mode:
    st.markdown(
        "<div style='background:#1a1a1a;border:1px solid #333;border-radius:10px;"
        "padding:10px 16px;margin-bottom:16px;'>"
        "<span style='color:#B3B3B3;font-size:0.85rem;'>"
        "At k > 5 clusters are fine-grained audio sub-groups. "
        "Playlists are numbered for clarity — audio characteristics shown below each name.</span>"
        "</div>",
        unsafe_allow_html=True,
    )

# In category/SGL mode df_clust can have one row per (track, playlist) — use nunique
_count_agg = "nunique" if (_is_category_mode or _is_sgl_mode) else "count"
_sort_by_number = k > 5 and not _is_category_mode and not _is_sgl_mode
cluster_stats = (
    df_clust.groupby(["cluster", "cluster_name"])
    .agg(count=("track_id", _count_agg), energy=("energy", "mean"),
         valence=("valence", "mean"), danceability=("danceability", "mean"))
    .reset_index()
    .sort_values("cluster" if _sort_by_number else "count",
                 ascending=_sort_by_number)
    .reset_index(drop=True)
)

_ROW_SIZE = 4
for _chunk_start in range(0, len(cluster_stats), _ROW_SIZE):
    _chunk = cluster_stats.iloc[_chunk_start:_chunk_start + _ROW_SIZE]
    _cols = st.columns(len(_chunk), gap="large")
    for _col, (_, _row) in zip(_cols, _chunk.iterrows()):
        _short = (_row["cluster_name"][:18] + "…") if len(_row["cluster_name"]) > 18 else _row["cluster_name"]
        with _col:
            _kpi_sub = (
                f"E {_row['energy']:.2f} · V {_row['valence']:.2f}"
                if not _is_category_mode and pd.notna(_row.get("energy")) and pd.notna(_row.get("valence"))
                else ""
            )
            st.markdown(
                kpi_card("🎵", _short, str(int(_row["count"])), _kpi_sub),
                unsafe_allow_html=True,
            )

hr()

# ── GENRE CLUSTER BAR CHART (By specific genre only) ─────────────────────────
if _is_sgl_mode:
    section_title("Tracks per Genre Cluster", "Unique tracks matched by each selected genre")
    _bar_df = cluster_stats.sort_values("count", ascending=True).copy()
    _bar_colors = [name_to_color.get(n, "#1DB954") for n in _bar_df["cluster_name"]]
    _bar_fig = go.Figure(go.Bar(
        x=_bar_df["count"],
        y=_bar_df["cluster_name"],
        orientation="h",
        marker_color=_bar_colors,
        hovertemplate="%{y}: %{x} tracks<extra></extra>",
    ))
    _bar_fig.update_layout(
        **{**_BASE_LAYOUT, "margin": dict(t=10, b=40, l=200, r=40)},
        height=max(300, len(_bar_df) * 28),
        xaxis=dict(title="Tracks", gridcolor="#282828", tickfont=dict(color="#B3B3B3")),
        yaxis=dict(tickfont=dict(color="#FFFFFF", size=11)),
    )
    st.plotly_chart(_bar_fig, use_container_width=True)
    hr()

# ── PCA CHARTS (KMeans only) ──────────────────────────────────────────────────
if not _is_category_mode and not _is_sgl_mode:
    section_title(
        "Music Space — By Cluster",
        f"PC1 {var1:.1f}% variance · PC2 {var2:.1f}% variance",
    )
    st.markdown(
        info_box(
            "What is this chart?",
            "Each dot is one track. Tracks that sound similar sit closer together. "
            "Color shows the KMeans cluster assigned.",
            "What is PC1 / PC2?",
            f"PCA compresses {len(CLUSTER_FEATURES)} audio dimensions into 2 axes. "
            f"PC1 ({var1:.1f}%) loads on {pc1_label} — "
            f"PC2 ({var2:.1f}%) loads on {pc2_label}. "
            f"Together they explain {var1+var2:.1f}% of variance.",
        ),
        unsafe_allow_html=True,
    )
    _fig_pca = px.scatter(
        df_clust, x="PC1", y="PC2",
        color="cluster_name",
        hover_data=["track_name", "artist_name"],
        color_discrete_map=name_to_color,
        labels={
            "PC1": f"PC1 ({var1:.1f}%) — {pc1_label}",
            "PC2": f"PC2 ({var2:.1f}%) — {pc2_label}",
            "cluster_name": "Cluster",
        },
        opacity=0.75,
    )
    _fig_pca.update_traces(
        marker=dict(size=5, line=dict(width=0)),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>",
    )
    _fig_pca.update_layout(
        **_BASE_LAYOUT, height=500,
        xaxis=dict(gridcolor="#282828", tickfont=dict(color="#B3B3B3")),
        yaxis=dict(gridcolor="#282828", tickfont=dict(color="#B3B3B3")),
        legend=dict(bgcolor="#181818", font=dict(color="#B3B3B3"), title_text="",
                    orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
    )
    st.plotly_chart(_fig_pca, use_container_width=True)
    hr()

    section_title("Music Space — By Playlist", "Same PCA projection coloured by playlist")
    _fig_pl = px.scatter(
        df_clust, x="PC1", y="PC2",
        color="playlist_name",
        color_discrete_map=pl_color_map,
        hover_data=["track_name", "artist_name"],
        labels={
            "PC1": f"PC1 ({var1:.1f}%) — {pc1_label}",
            "PC2": f"PC2 ({var2:.1f}%) — {pc2_label}",
            "playlist_name": "Playlist",
        },
        opacity=0.65,
    )
    _fig_pl.update_traces(
        marker=dict(size=5, line=dict(width=0)),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>",
    )
    _fig_pl.update_layout(
        **{**_BASE_LAYOUT, "margin": dict(t=60, b=40, l=10, r=10)},
        height=500,
        xaxis=dict(gridcolor="#282828", tickfont=dict(color="#B3B3B3")),
        yaxis=dict(gridcolor="#282828", tickfont=dict(color="#B3B3B3")),
        legend=dict(bgcolor="#181818", font=dict(color="#B3B3B3"), title_text="",
                    orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
    )
    st.plotly_chart(_fig_pl, use_container_width=True)
    hr()

    # ── RADAR ─────────────────────────────────────────────────────────────────
    section_title("Cluster Audio Profiles", "Radar built on: " + ", ".join(_RADAR_FEATURES))
    _centroids_original = pd.DataFrame(
        scaler_used.inverse_transform(centroids_scaled[CLUSTER_FEATURES].values),
        columns=CLUSTER_FEATURES,
    )
    _radar_centroids = _centroids_original[_RADAR_FEATURES].clip(0, 1)
    _fig_radar = go.Figure()
    for _i in range(k):
        _color = int_to_color[_i]
        _cname = name_map[_i]
        _raw   = _radar_centroids.iloc[_i]
        _norm  = _raw.tolist()
        _vals  = _norm + [_norm[0]]
        _feats = _RADAR_FEATURES + [_RADAR_FEATURES[0]]
        _r_c, _g_c, _b_c = int(_color[1:3], 16), int(_color[3:5], 16), int(_color[5:7], 16)
        _fig_radar.add_trace(go.Scatterpolar(
            r=_vals, theta=_feats, fill="toself",
            fillcolor=f"rgba({_r_c},{_g_c},{_b_c},0.15)",
            line=dict(color=_color, width=2),
            name=_cname,
            hovertemplate="%{theta}: %{r:.2f}<extra>" + _cname + "</extra>",
        ))
    _fig_radar.update_layout(
        **{**_BASE_LAYOUT, "margin": dict(t=40, b=40, l=60, r=180)},
        polar=dict(
            bgcolor="#181818",
            radialaxis=dict(visible=True, range=[0, 1], gridcolor="#333",
                            tickfont=dict(color="#B3B3B3", size=10),
                            tickvals=[0.25, 0.5, 0.75, 1.0]),
            angularaxis=dict(gridcolor="#333", tickfont=dict(color="#FFFFFF", size=13)),
        ),
        legend=dict(bgcolor="#181818", font=dict(color="#B3B3B3"),
                    x=1.05, y=0.5, xanchor="left", yanchor="middle"),
        height=480,
    )
    st.plotly_chart(_fig_radar, use_container_width=True)
    hr()

# ── HEATMAP ───────────────────────────────────────────────────────────────────
section_title(
    "Playlist × Cluster Alignment",
    "% of each playlist's tracks that fall into each cluster",
)

_hm_data = df_clust.groupby(["playlist_name", "cluster_name"]).size().reset_index(name="count")

if _is_category_mode and k == 1:
    st.info(
        "💡 All tracks landed in a single group — the Playlist × Cluster chart needs at least "
        "two groups to be meaningful. Try adding **Genre** as a second grouping dimension "
        "or broadening your decade selection to create multiple groups."
    )
elif _hm_data.empty:
    st.info("No data to show.")
else:
    _hm_pivot = (
        _hm_data.pivot(index="playlist_name", columns="cluster_name", values="count").fillna(0)
    )
    _hm_pct    = _hm_pivot.div(_hm_pivot.sum(axis=1), axis=0) * 100
    _n_rows    = len(_hm_pct.index)
    _cell_h    = max(50, min(80, 400 // _n_rows))
    _hm_height = max(280, _n_rows * _cell_h + 80)
    _x_labels  = _hm_pct.columns.astype(str).tolist()
    _y_labels  = _hm_pct.index.astype(str).tolist()
    _n_cols    = len(_x_labels)
    _show_cell_text = _n_cols <= 15
    _tick_angle     = -45 if _n_cols > 8 else 0
    _bottom_margin  = 140 if _n_cols > 8 else 20
    _fig_heat  = go.Figure(data=go.Heatmap(
        z=_hm_pct.values, x=_x_labels, y=_y_labels,
        colorscale=[[0, "#121212"], [0.4, "#145e2a"], [1, "#1DB954"]],
        zmin=0, zmax=100,
        **(dict(text=_hm_pct.values.round(1), texttemplate="%{text}%",
                textfont=dict(color="#FFFFFF", size=11)) if _show_cell_text else {}),
        showscale=True, xgap=3, ygap=3,
        hovertemplate="%{y} · %{x}<br>%{z:.1f}%<extra></extra>",
    ))
    _fig_heat.update_layout(
        **{**_BASE_LAYOUT, "margin": dict(t=20, b=_bottom_margin, l=120, r=20)},
        xaxis=dict(type="category", tickangle=_tick_angle,
                   tickfont=dict(color="#FFFFFF", size=10), side="bottom"),
        yaxis=dict(type="category", tickfont=dict(color="#B3B3B3"),
                   categoryorder="array", categoryarray=list(reversed(_y_labels))),
        height=_hm_height,
    )
    st.plotly_chart(_fig_heat, use_container_width=True)

hr()

# ── BUILD UNMATCHED DATAFRAME ─────────────────────────────────────────────────
if _is_sgl_mode:
    df_unmatched = df_unmatched_cat.drop_duplicates(subset="track_id").copy() if not df_unmatched_cat.empty else pd.DataFrame()
    _unmatched_title = "⚠️ Tracks with no matching genre"
    _unmatched_desc  = (
        f"{len(df_unmatched)} track(s) don't match any selected genre "
        f"and were excluded from all clusters. Assign them manually below."
    )
elif _is_category_mode:
    df_unmatched = df_unmatched_cat.drop_duplicates(subset="track_id").copy() if not df_unmatched_cat.empty else pd.DataFrame()
    _unmatched_title = "⚠️ Unmatched Tracks"
    _unmatched_desc  = (
        f"{len(df_unmatched)} track(s) are missing {_grp_dim_str} data "
        f"and were excluded from grouping."
    )
else:
    # Pre-built at submission time with all filters applied (playlist, decade, family)
    df_unmatched = df_unmatched_cat.drop_duplicates(subset="track_id").copy() if not df_unmatched_cat.empty else pd.DataFrame()
    _unmatched_title = "⚠️ Unmatched Tracks"
    _unmatched_desc  = f"{len(df_unmatched)} tracks have no audio features and were excluded from clustering."

# Remove tracks already saved to a cluster — use a dedicated set to avoid aliasing issues
_already_assigned = st.session_state.get("_unmatched_done_ids", set())
if _already_assigned and not df_unmatched.empty:
    df_unmatched = df_unmatched[~df_unmatched["track_id"].isin(_already_assigned)]
    if _is_category_mode:
        _unmatched_desc = (
            f"{len(df_unmatched)} track(s) are missing {_grp_dim_str} data "
            f"and were excluded from grouping."
        )
    else:
        _unmatched_desc = f"{len(df_unmatched)} tracks have no audio features and were excluded from clustering."

_unmatched_all_done = df_unmatched.empty

# ── UNASSIGNED WARNING ────────────────────────────────────────────────────────
if len(df_unmatched) > 0:
    _n_unassigned = sum(
        1 for tid in df_unmatched["track_id"]
        if tid not in st.session_state.get("unmatched_assignments", {})
        or st.session_state["unmatched_assignments"].get(tid) == "— unassigned —"
    )
    if _n_unassigned > 0:
        st.warning(
            f"⚠️ {_n_unassigned} unmatched track(s) are still unassigned. "
            "They will be skipped on export. Scroll down to assign them manually."
        )

# ── CLUSTER DETAILS ───────────────────────────────────────────────────────────
section_title("Cluster Details", "Ranked by size · expand to browse and download tracks")

if _is_sgl_mode:
    st.markdown(
        "<div style='background:#1a1a1a;border:1px solid #333;border-radius:10px;"
        "padding:10px 16px;margin-bottom:16px;'>"
        "<span style='color:#B3B3B3;font-size:0.85rem;'>"
        "ℹ️ A track tagged with multiple selected genres appears in <b style='color:#FFFFFF;'>each</b> "
        "of those clusters — so the same song may show up more than once across the list below.</span>"
        "</div>",
        unsafe_allow_html=True,
    )

cluster_sorted = (
    df_clust.groupby(["cluster", "cluster_name"])
    .agg(
        count=("track_id", _count_agg),
        energy=("energy", "mean"),
        valence=("valence", "mean"),
        danceability=("danceability", "mean"),
    )
    .reset_index()
    .sort_values("cluster" if _sort_by_number else "count",
                 ascending=_sort_by_number)
    .reset_index(drop=True)
)

_descriptions = st.session_state.get("cluster_descriptions", {})

# Precompute per-cluster track_id lists using only the original KMeans track_ids —
# exclude manually assigned unmatched tracks (they were appended to df_clust by save_assignments
# but must NOT be saved as "done" or their status="manual" DB rows get overwritten).
_original_track_ids = set(track_ids)
_cluster_track_ids_map = {
    int(i): grp["track_id"].drop_duplicates().tolist()
    for i, grp in df_clust[df_clust["track_id"].isin(_original_track_ids)].groupby("cluster")
}
_audio_feat_cols = [c for c in ["energy", "acousticness", "valence", "tempo", "danceability", "PC1", "PC2"] if c in df_clust.columns]
_cluster_audio_means = (
    df_clust.groupby("cluster")[_audio_feat_cols].mean().to_dict("index")
    if _audio_feat_cols else {}
)

for rank, row in cluster_sorted.iterrows():
    i     = int(row["cluster"])
    color = int_to_color[i]
    pct   = row["count"] / n_tracks * 100 if n_tracks else 0

    cluster_track_ids = _cluster_track_ids_map.get(i, [])

    _cluster_done = all(
        tid in st.session_state.get("done_tracks", set())
        for tid in cluster_track_ids
    )

    if _cluster_done:
        _done_card_col, _reopen_col = st.columns([8, 2])
        with _done_card_col:
            st.markdown(
                f"<div style='background:#1a2e1a;border-radius:12px;padding:14px 18px;"
                f"border:1px solid #1DB954;margin-bottom:10px;display:flex;"
                f"justify-content:space-between;align-items:center;'>"
                f"<div>"
                f"<span style='color:#B3B3B3;font-size:0.85rem;font-weight:700;margin-right:10px;'>"
                f"{str(rank+1).zfill(2)}</span>"
                f"<span style='color:#FFFFFF;font-weight:700;font-size:0.95rem;'>"
                f"{row['cluster_name']}</span>"
                f"</div>"
                f"<div style='display:flex;align-items:center;gap:12px;'>"
                f"<span style='color:#1DB954;font-size:0.85rem;'>✓ Done</span>"
                f"<span style='color:#B3B3B3;font-size:0.85rem;'>{int(row['count'])} tracks</span>"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with _reopen_col:
            if st.button(
                "↩ Re-open",
                key=f"reopen_cluster_{rank}_{i}",
                type="secondary",
                use_container_width=True,
                help="Bring this cluster back for re-export",
            ):
                _tids_reopen = set(cluster_track_ids)
                st.session_state["done_tracks"] -= _tids_reopen
                try:
                    from db.queries import get_engine as _get_engine_ro2
                    from sqlalchemy import text as _sqlt_ro2
                    with _get_engine_ro2().begin() as _conn_ro2:
                        _conn_ro2.execute(
                            _sqlt_ro2("DELETE FROM user_cluster_progress "
                                      "WHERE user_key = :uk AND status = 'done' "
                                      "AND track_id IN :tids"),
                            {"uk": user_key, "tids": tuple(_tids_reopen)},
                        )
                except Exception:
                    pass
                st.rerun()
    else:
        if _is_category_mode or _is_sgl_mode:
            _feature_line = f"{int(row['count']):,} tracks · {pct:.1f}% of selection"
        else:
            _feature_line = ""
        _desc = ""

        st.markdown(
            cluster_card(
                rank + 1, row["cluster_name"], int(row["count"]), n_tracks,
                row["energy"], row["valence"], row["danceability"], color,
                desc=_desc, feature_line=_feature_line,
            ),
            unsafe_allow_html=True,
        )

        cluster_tracks = [
            {"id": r2["track_id"], "name": r2["track_name"], "artists": r2["artist_name"]}
            for _, r2 in df_clust[df_clust["cluster"] == i].drop_duplicates(subset="track_id").iterrows()
        ]

        # Build display subset — audio feature columns not meaningful in category/SGL mode
        _audio_cols = [] if (_is_category_mode or _is_sgl_mode) else [
            c for c in ["energy", "acousticness", "valence", "tempo", "danceability"]
            if c in df_clust.columns
        ]
        _base_cols = ["track_name", "artist_name", "playlist_name"] + _audio_cols
        _available_cols = [c for c in _base_cols if c in df_clust.columns]

        subset = (
            df_clust[df_clust["cluster"] == i][_available_cols]
            .rename(columns={
                "track_name": "Track", "artist_name": "Artist",
                "playlist_name": "Playlist", "energy": "Energy",
                "acousticness": "Acousticness", "valence": "Valence",
                "tempo": "Tempo", "danceability": "Danceability",
            })
            .reset_index(drop=True)
        )

        if _is_category_mode or _is_sgl_mode:
            subset = (
                subset
                .groupby(["Track", "Artist"], as_index=False, sort=False)
                .agg(Playlist=("Playlist", lambda x: ", ".join(sorted(x.unique()))))
                .sort_values("Track")
                .reset_index(drop=True)
            )
        else:
            subset = subset.sort_values("Track").reset_index(drop=True)

        _slug = row["cluster_name"].replace(" ", "_").replace("·", "").replace("  ", "_")
        _spotlistr_key = f"spotlistr_clicked_{rank}_{i}"
        _dev_mode = os.getenv("DEV_MODE", "0") == "1"
        _sp_oauth = st.session_state.get("sp_oauth")

        with st.expander(f"View {int(row['count'])} tracks · Export to Spotify →"):
            st.dataframe(subset, use_container_width=True, hide_index=True)
            _csv = subset.to_csv(index=False).encode("utf-8")
            if st.download_button(
                label="⬇️ Download CSV",
                data=_csv,
                file_name=f"cluster_{rank+1}_{_slug}.csv",
                mime="text/csv",
                key=f"dl_cluster_{i}",
            ):
                _track("export_download",
                       kind="cluster",
                       cluster_name=row["cluster_name"],
                       n_tracks=int(row["count"]),
                       mode=grouping_mode)
    
            # ── Export flow ───────────────────────────────────────────────────────
            if _dev_mode and _sp_oauth:
                _export_name = f"{row['cluster_name']} — {datetime.now().strftime('%Y-%m-%d')}"
                _name_input = st.text_input(
                    "Playlist name", value=_export_name, key=f"pl_name_{rank}_{i}"
                )
                if st.button(
                    f"🎵 Create Spotify Playlist ({len(cluster_track_ids)} tracks)",
                    key=f"create_pl_{rank}_{i}", type="primary",
                ):
                    with st.spinner("Creating playlist..."):
                        from spotify_client import create_spotify_playlist
                        url = create_spotify_playlist(_sp_oauth, _name_input, cluster_track_ids)
                    if url:
                        st.success(f"✅ Playlist created! [Open in Spotify]({url})")
                        st.session_state[_spotlistr_key] = True
                    else:
                        st.error("Failed to create playlist — check your Spotify connection.")
            else:
                render_export_to_spotify(
                    cluster_tracks,
                    f"Cluster {rank + 1} — {row['cluster_name']}",
                    key_prefix=f"cluster_{i}",
                    on_export=lambda n_tracks, _cn=row["cluster_name"]: _track(
                        "export_download",
                        kind="spotlistr_csv",
                        cluster_name=_cn,
                        n_tracks=n_tracks,
                        mode=grouping_mode,
                    ),
                )

                # Check if already marked done
                _cluster_done = all(
                    tid in st.session_state.get("done_tracks", set())
                    for tid in cluster_track_ids
                )

                if _cluster_done:
                    st.markdown(
                        "<div style='background:#1a2e1a;border:1px solid #1DB954;border-radius:10px;"
                        "padding:10px 16px;margin-top:8px;'>"
                        "<span style='color:#1DB954;font-weight:700;'>✓ Done — </span>"
                        "<span style='color:#B3B3B3;font-size:0.88rem;'>"
                        "These tracks are marked as exported and hidden from future runs.</span>"
                        "</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    # Unassigned warning
                    _n_unassigned_here = sum(
                        1 for tid in df_unmatched["track_id"]
                        if tid not in st.session_state.get("unmatched_assignments", {})
                        or st.session_state["unmatched_assignments"].get(tid) == "— unassigned —"
                    ) if len(df_unmatched) > 0 else 0

                    if _n_unassigned_here > 0:
                        st.markdown(
                            f"<div style='background:#1a1a1a;border:1px solid #E8534A;"
                            f"border-radius:10px;padding:12px 18px;margin-top:12px;margin-bottom:8px;'>"
                            f"<span style='color:#E8534A;font-weight:700;'>"
                            f"⚠️ {_n_unassigned_here} unassigned track(s) — </span>"
                            f"<span style='color:#FFFFFF;font-size:0.88rem;'>"
                            f"These tracks won't be in any playlist. "
                            f"Scroll down to assign them first.</span>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )

                    _confirm_key = f"confirm_mark_done_{rank}_{i}"

                    if st.session_state.get(_confirm_key):
                        st.markdown(
                            "<div style='background:#1a1a1a;border:1px solid #333;"
                            "border-radius:10px;padding:10px 16px;margin-bottom:8px;'>"
                            "<span style='color:#FFFFFF;font-size:0.88rem;'>"
                            "These tracks will be hidden from future clustering runs. "
                            "You can choose which to restore at the end.</span>"
                            "</div>",
                            unsafe_allow_html=True,
                        )
                        _yes_col, _no_col = st.columns(2)
                        with _yes_col:
                            if st.button(
                                f"✓ Yes, mark {int(row['count'])} tracks as done",
                                key=f"confirm_yes_{rank}_{i}",
                                type="primary",
                            ):
                                if os.getenv("DEV_MODE") != "1":
                                    with st.spinner("Saving…"):
                                        save_cluster_progress_bulk(user_key, list(cluster_track_ids), status="done")
                                    _track("mark_done_click",
                                           cluster_name=row["cluster_name"],
                                           n_tracks=int(row["count"]),
                                           mode=grouping_mode)
                                st.session_state["done_tracks"].update(cluster_track_ids)
                                st.session_state.pop(_confirm_key, None)
                                st.rerun()
                        with _no_col:
                            if st.button("✗ Cancel", key=f"confirm_no_{rank}_{i}"):
                                st.session_state.pop(_confirm_key, None)
                                st.rerun()
                    else:
                        if st.button(
                            f"✓ Mark these {int(row['count'])} tracks as done",
                            key=f"mark_done_{rank}_{i}",
                            help="Hides these tracks from future clustering runs. Reversible at the end.",
                        ):
                            if _n_unassigned_here > 0:
                                st.session_state[_confirm_key] = True
                            else:
                                if os.getenv("DEV_MODE") != "1":
                                    with st.spinner("Saving…"):
                                        save_cluster_progress_bulk(user_key, list(cluster_track_ids), status="done")
                                    _track("mark_done_click",
                                           cluster_name=row["cluster_name"],
                                           n_tracks=int(row["count"]),
                                           mode=grouping_mode)
                                st.session_state["done_tracks"].update(cluster_track_ids)
                            st.rerun()

# ── UNMATCHED TRACKS SECTION ──────────────────────────────────────────────────
# Wrapped in st.fragment so only this section reruns on selectbox changes,
# not the entire page (which is expensive with many clusters).
@st.fragment
def _render_unmatched_section():
    section_title(_unmatched_title, _unmatched_desc)

    st.markdown(
        "<div style='background:#1a1a1a;border:1px solid #E8534A;border-radius:10px;"
        "padding:12px 18px;margin-bottom:16px;'>"
        "<span style='color:#E8534A;font-weight:700;'>Important — </span>"
        "<span style='color:#FFFFFF;font-size:0.88rem;'>"
        "Assign each track to a cluster using the dropdowns below, then click "
        "<b style='color:#1DB954;'>💾 Save assignments</b> at the bottom — "
        "selections are not saved automatically. "
        "Unassigned tracks will be <b>skipped on export</b> and won't appear in any Spotify playlist. "
        "Use the download button to save the full list before exporting. "
        "Some tracks may show missing or incomplete genre data — this is normal for lesser-known artists "
        "whose Spotify profile has limited metadata.</span>"
        "</div>",
        unsafe_allow_html=True,
    )

    _unmatched_csv = df_unmatched[[
        c for c in ["track_name", "artist_name", "release_year", "artist_genres", "playlist_name"]
        if c in df_unmatched.columns
    ]].rename(columns={
        "track_name": "Track", "artist_name": "Artist",
        "release_year": "Release Year", "artist_genres": "Genres",
        "playlist_name": "Playlist",
    }).to_csv(index=False).encode("utf-8")

    if st.download_button(
        label="⬇️ Download unmatched tracks list",
        data=_unmatched_csv,
        file_name="unmatched_tracks.csv",
        mime="text/csv",
        key="dl_unmatched",
    ):
        _track("export_download",
               kind="unmatched",
               n_tracks=len(df_unmatched),
               mode=grouping_mode)

    hr(top=12, bottom=12)

    _done_set_now = st.session_state.get("done_tracks", set())
    _done_cluster_indices = {
        _i for _i, _tids in _cluster_track_ids_map.items()
        if _tids and all(tid in _done_set_now for tid in _tids)
    }
    cluster_options = ["— unassigned —"] + [
        name_map[_i] for _i in range(k)
        if _i not in _done_cluster_indices
    ]
    _name_to_cluster_idx = {v: k for k, v in name_map.items()}
    _saved = dict(st.session_state.get("unmatched_assignments", {}))
    _new_vals: dict = {}

    header_cols = st.columns([3, 2, 1, 2, 3])
    for _hcol, _hlabel in zip(header_cols, ["Track", "Artist", "Year", "Genres", "Assign to Cluster"]):
        _hcol.markdown(
            f"<span style='color:#B3B3B3;font-size:0.78rem;text-transform:uppercase;"
            f"letter-spacing:0.06em;'>{_hlabel}</span>",
            unsafe_allow_html=True,
        )
    st.markdown("<hr style='border-color:#333;margin:6px 0 10px;'>", unsafe_allow_html=True)

    for _, _urow in df_unmatched.iterrows():
        _tid = _urow["track_id"]
        _ucols = st.columns([3, 2, 1, 2, 3])
        _ucols[0].markdown(
            f"<span style='color:#FFFFFF;font-size:0.85rem;'>{_urow['track_name']}</span>",
            unsafe_allow_html=True,
        )
        _ucols[1].markdown(
            f"<span style='color:#B3B3B3;font-size:0.85rem;'>{_urow['artist_name']}</span>",
            unsafe_allow_html=True,
        )
        _yr_raw = _urow.get('release_year', '')
        try:
            _yr_display = '' if pd.isna(_yr_raw) else (str(int(_yr_raw)) if _yr_raw else '')
        except (TypeError, ValueError):
            _yr_display = str(_yr_raw) if _yr_raw else ''
        _ucols[2].markdown(
            f"<span style='color:#B3B3B3;font-size:0.85rem;'>{_yr_display}</span>",
            unsafe_allow_html=True,
        )
        _ucols[3].markdown(
            f"<span style='color:#B3B3B3;font-size:0.78rem;'>"
            f"{(str(_urow.get('artist_genres', '')) or '')[:40]}</span>",
            unsafe_allow_html=True,
        )
        _prev = _saved.get(_tid, "— unassigned —")
        # Normalize old "N. Name" format to plain name
        if _prev and _prev != "— unassigned —" and ". " in _prev and _prev not in cluster_options:
            _prev = _prev.split(". ", 1)[1]
        _new_vals[_tid] = _ucols[4].selectbox(
            label="", options=cluster_options,
            index=cluster_options.index(_prev) if _prev in cluster_options else 0,
            key=f"assign_{_tid}", label_visibility="collapsed",
        )

    hr(top=16, bottom=12)
    _save_col, _status_col = st.columns([1, 2])
    with _save_col:
        if st.button("💾 Save assignments", use_container_width=True, key="save_assignments"):
            _merged = {**_saved, **_new_vals}
            st.session_state["unmatched_assignments"] = _merged

            _just_assigned = {
                _tid: _cname for _tid, _cname in _new_vals.items()
                if _cname and _cname != "— unassigned —"
            }

            # If any target cluster is already fully done, re-open it so the user
            # can re-export it with the newly assigned tracks included.
            _done_now: set = st.session_state.get("done_tracks", set())
            _reopened_names: list[str] = []
            _tids_to_reopen: set = set()
            for _assigned_cname in set(_just_assigned.values()):
                _cidx  = _name_to_cluster_idx.get(_assigned_cname, 0)
                _ctids = set(_cluster_track_ids_map.get(_cidx, []))
                if _ctids and _ctids.issubset(_done_now):
                    _reopened_names.append(name_map[_cidx])
                    _tids_to_reopen.update(_ctids)
            if _tids_to_reopen:
                st.session_state["done_tracks"] -= _tids_to_reopen
                try:
                    from db.queries import get_engine as _get_engine_ro
                    from sqlalchemy import text as _sqlt_ro
                    with _get_engine_ro().begin() as _conn_ro:
                        _conn_ro.execute(
                            _sqlt_ro("DELETE FROM user_cluster_progress "
                                     "WHERE user_key = :uk AND status = 'done' "
                                     "AND track_id IN :tids"),
                            {"uk": user_key, "tids": tuple(_tids_to_reopen)},
                        )
                except Exception:
                    pass
                st.session_state["_reopened_cluster_warning"] = _reopened_names

            st.session_state["_unmatched_done_ids"] = (
                st.session_state.get("_unmatched_done_ids", set()) | set(_just_assigned.keys())
            )

            _save_errors = []
            if os.getenv("DEV_MODE") != "1":
                for _tid, _cname in _just_assigned.items():
                    try:
                        save_cluster_progress(user_key, _tid, status="manual", cluster_name=_cname)
                    except Exception as _e:
                        _save_errors.append(str(_e))
            if _save_errors:
                st.toast(f"⚠️ DB save failed: {_save_errors[0]}", icon="🚨")
                st.session_state["_manual_save_error"] = _save_errors[0]
            else:
                st.toast(f"✅ {len(_just_assigned)} assignment(s) saved to DB")

            _assigned_rows = []
            for _, _urow in df_unmatched.iterrows():
                _tid   = _urow["track_id"]
                _cname = _just_assigned.get(_tid)
                if not _cname:
                    continue
                _cluster_idx = _name_to_cluster_idx.get(_cname, 0)
                _cmeans = _cluster_audio_means.get(_cluster_idx, {})
                _assigned_rows.append({
                    "track_id":      _tid,
                    "track_name":    _urow["track_name"],
                    "artist_name":   _urow["artist_name"],
                    "playlist_name": _urow["playlist_name"],
                    "cluster":       _cluster_idx,
                    "cluster_name":  name_map[_cluster_idx],
                    "energy":        _cmeans.get("energy", 0),
                    "acousticness":  _cmeans.get("acousticness", 0),
                    "valence":       _cmeans.get("valence", 0),
                    "tempo":         _cmeans.get("tempo", 0),
                    "danceability":  _cmeans.get("danceability", 0),
                    "PC1":           _cmeans.get("PC1", 0),
                    "PC2":           _cmeans.get("PC2", 0),
                })

            if _assigned_rows:
                _df_assigned  = pd.DataFrame(_assigned_rows)
                _all_assigned = set(_merged.keys())
                _base_clust   = st.session_state["clustering_results"]["df_clust"][
                    ~st.session_state["clustering_results"]["df_clust"]["track_id"].isin(_all_assigned)
                ]
                st.session_state["clustering_results"]["df_clust"] = pd.concat(
                    [_base_clust, _df_assigned], ignore_index=True
                )

            _assigned_tids = set(_just_assigned.keys())
            if _assigned_tids:
                _uc = st.session_state["clustering_results"].get("df_unmatched_cat", pd.DataFrame())
                if not _uc.empty:
                    st.session_state["clustering_results"]["df_unmatched_cat"] = _uc[
                        ~_uc["track_id"].isin(_assigned_tids)
                    ]

            _n_assigned = len(_assigned_rows)
            _n_skipped  = len(df_unmatched) - _n_assigned
            _total_assigned = st.session_state.get("_total_assigned_count", 0) + _n_assigned
            st.session_state["_total_assigned_count"] = _total_assigned
            st.session_state["unmatched_save_status"] = (_total_assigned, _n_skipped)
            st.rerun(scope="app")  # full rerun so cluster details update after save

    with _status_col:
        if "unmatched_save_status" in st.session_state:
            _n_a, _n_s = st.session_state["unmatched_save_status"]
            _reopened = st.session_state.pop("_reopened_cluster_warning", [])
            if _reopened:
                _rnames = " and ".join(f'**"{n}"**' for n in _reopened)
                _was = "was" if len(_reopened) == 1 else "were"
                _it  = "it"  if len(_reopened) == 1 else "them"
                st.warning(
                    f"⚠️ {_rnames} {_was} already marked as done and "
                    f"{_was.replace('was','has been').replace('were','have been')} re-opened — "
                    f"please re-export {_it} to include the newly assigned tracks."
                )
            if _n_s > 0:
                st.warning(f"✅ {_n_a} tracks assigned · ⚠️ {_n_s} unassigned and will be skipped on export.")
            else:
                st.success(f"✅ All {_n_a} tracks assigned.")

if len(df_unmatched) > 0:
    _render_unmatched_section()

hr()

# ── KEEP VISIBLE (shown at bottom when all done, where the user already is) ───
if _all_done:
    _keep_visible = st.session_state.get("keep_visible", {})
    st.markdown(
        "<p style='color:#FFFFFF;font-size:0.88rem;font-weight:700;margin-bottom:6px;'>"
        "🎉 All done! Which clusters do you want to keep available for future runs?</p>"
        "<p style='color:#B3B3B3;font-size:0.82rem;margin-bottom:12px;'>"
        "Unchecked clusters will be hidden from the next run.</p>",
        unsafe_allow_html=True,
    )
    _new_keep_visible = {}
    for _ci in range(k):
        _cname = name_map[_ci]
        _ctracks = df_clust[df_clust["cluster"] == _ci]["track_id"].drop_duplicates().tolist()
        _checked = st.checkbox(
            f"{_cname} ({len(_ctracks)} tracks) — keep visible",
            value=_keep_visible.get(_cname, False),
            key=f"keep_visible_cb_{_ci}",
        )
        _new_keep_visible[_cname] = _checked
    st.session_state["keep_visible"] = _new_keep_visible
    hr(top=16, bottom=16)

# ── CONGRATULATIONS BANNER ───────────────────────────────────────────────────
if _all_done and _unmatched_all_done:
    _n_manually = st.session_state.get("_total_assigned_count", 0)
    _sub = (
        f"{n_tracks:,} tracks clustered · {_n_manually:,} manually assigned"
        if _n_manually
        else f"{n_tracks:,} tracks fully organized across {k} clusters"
    )
    st.markdown(
        "<div style='background:#1a2e1a;border:2px solid #1DB954;border-radius:16px;"
        "padding:28px 24px;margin-bottom:24px;text-align:center;'>"
        "<div style='font-size:2.4rem;margin-bottom:10px;'>🎉</div>"
        "<p style='color:#1DB954;font-weight:800;font-size:1.3rem;margin:0 0 8px;'>"
        "Congratulations! Your collection is fully organized.</p>"
        f"<p style='color:#B3B3B3;font-size:0.9rem;margin:0;'>{_sub}</p>"
        "</div>",
        unsafe_allow_html=True,
    )

# ── WHAT'S NEXT ───────────────────────────────────────────────────────────────
def _apply_keep_visible():
    """Remove checked clusters from done_tracks (session + DB) before navigating."""
    _kv = st.session_state.get("keep_visible", {})
    _to_restore = set()
    for _ci in range(k):
        _cname = name_map[_ci]
        if _kv.get(_cname, False):
            _to_restore.update(df_clust[df_clust["cluster"] == _ci]["track_id"].tolist())
    if _to_restore:
        st.session_state["done_tracks"] -= _to_restore
        try:
            from db.queries import get_engine
            from sqlalchemy import text as _sqlt
            with get_engine().begin() as _conn:
                _conn.execute(
                    _sqlt("DELETE FROM user_cluster_progress "
                          "WHERE user_key = :uk AND track_id IN :tids"),
                    {"uk": user_key, "tids": tuple(_to_restore)},
                )
        except Exception:
            pass

st.markdown(
    "<p style='color:#B3B3B3;font-size:0.85rem;font-weight:700;margin-bottom:10px;'>"
    "What's next?</p>",
    unsafe_allow_html=True,
)
_nav_col1, _nav_col2 = st.columns(2)
with _nav_col1:
    if st.button(
        "← Reconfigure with same filters",
        use_container_width=True,
        key="bottom_reconfigure",
    ):
        _apply_keep_visible()
        st.switch_page("pages/6_My_Clusters.py")
with _nav_col2:
    if st.button(
        "🔄 Start fresh — clear filters",
        use_container_width=True,
        key="bottom_fresh",
        type="secondary",
    ):
        _apply_keep_visible()
        st.session_state["_start_fresh"] = True
        st.switch_page("pages/6_My_Clusters.py")

hr()
st.markdown(
    "<p style='color:#B3B3B3;font-size:0.78rem;text-align:center;'>"
    "scikit-learn KMeans · StandardScaler · PCA for visualization only</p>",
    unsafe_allow_html=True,
)
