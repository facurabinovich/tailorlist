import html
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from db.queries import get_all_tracks, load_audio_features_by_playlist, load_playlist_meta, load_tracks_added_by_month
from config import CLUSTER_FEATURES

from utils import inject_global_css

inject_global_css()
from utils import inject_sidebar_nav, spotify_icon_html, page_brand_html
inject_sidebar_nav("Playlist Detail")
from utils import check_collection_mode
if not check_collection_mode():
    st.stop()

# ---------------------------------------------------------------------------
# Config & helpers
# ---------------------------------------------------------------------------
_BASE_LAYOUT = dict(
    plot_bgcolor="#121212",
    paper_bgcolor="#121212",
    font_color="#B3B3B3",
    margin=dict(t=20, b=20, l=10, r=10),
)

SPOTIFY_LOGO = spotify_icon_html(36)

def fmt_duration(minutes: float) -> str:
    m = int(minutes)
    s = int(round((minutes - m) * 60))
    return f"{m}:{s:02d}"

def kpi_card(icon: str, label: str, value: str, sub: str = "") -> str:
    sub_html = f"<div style='color:#B3B3B3;font-size:0.78rem;margin-top:4px;'>{html.escape(str(sub))}</div>" if sub else ""
    lines = [
        "<div style='background:#282828;border-radius:14px;padding:22px 24px;border:1px solid #333;height:100%;'>",
        f"<div style='font-size:1.6rem;margin-bottom:8px;'>{html.escape(str(icon))}</div>",
        f"<div style='color:#B3B3B3;font-size:0.78rem;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;'>{html.escape(str(label))}</div>",
        f"<div style='color:#FFFFFF;font-size:1.5rem;font-weight:800;line-height:1.1;'>{html.escape(str(value))}</div>",
        sub_html,
        "</div>",
    ]
    return "".join(lines)

def highlight_card(icon: str, label: str, track: str, artist: str, badge: str) -> str:
    lines = [
        "<div style='background:#282828;border-radius:12px;padding:16px 18px;border:1px solid #333;margin-bottom:10px;'>",
        f"<div style='color:#1DB954;font-size:0.75rem;font-weight:700;text-transform:uppercase;letter-spacing:0.07em;margin-bottom:8px;'>{icon} {label}</div>",
        f"<div style='color:#FFFFFF;font-weight:700;font-size:0.95rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{track}</div>",
        f"<div style='color:#B3B3B3;font-size:0.82rem;margin-top:2px;'>{artist}</div>",
        f"<div style='color:#1DB954;font-size:0.88rem;font-weight:800;margin-top:6px;'>{badge}</div>",
        "</div>",
    ]
    return "".join(lines)

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
df = get_all_tracks()

if st.session_state.get("mode") != "🔗 Your Collection":
    af_avg = load_audio_features_by_playlist()
    meta   = load_playlist_meta()
else:
    # Derive af_avg from df (audio features come from Spotify enrichment)
    _af_cols = [c for c in ["energy", "acousticness", "valence", "danceability",
                             "speechiness", "instrumentalness", "liveness", "tempo"]
                if c in df.columns]
    af_avg = (
        df.groupby("playlist_name")[_af_cols]
        .mean()
        .reset_index()
    ) if _af_cols else pd.DataFrame()
    meta = df.groupby("playlist_name").size().reset_index(name="total_tracks")
    _uc_playlists = st.session_state.get("uc_playlists", [])
    meta["followers"] = meta["playlist_name"].apply(
        lambda name: next((p.get("followers", 0) for p in _uc_playlists if p["name"] == name), 0)
    )

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(page_brand_html(), unsafe_allow_html=True)
st.markdown(
    f"<div style='display:flex;align-items:center;gap:14px;margin-bottom:2px;'>"
    f"{SPOTIFY_LOGO}"
    f"<h1 style='margin:0;font-size:2rem;font-weight:800;color:#FFFFFF;'>Playlist Detail</h1>"
    f"</div>"
    f"<p style='color:#B3B3B3;margin-top:6px;margin-bottom:0;font-size:0.9rem;'>"
    f"Deep dive into a single playlist — audio DNA, era breakdown, standout tracks and more."
    f"</p>",
    unsafe_allow_html=True,
)

st.markdown("<hr style='border-color:#333;margin-top:16px;margin-bottom:20px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Active collection banner
# ---------------------------------------------------------------------------
if st.session_state.get("mode") == "🔗 Your Collection" and st.session_state.get("uc_active"):
    n_unique = df["track_id"].nunique()
    n_pl     = df["playlist_name"].nunique()
    st.info(f"🎵 Viewing: Your Collection — {n_unique:,} unique tracks across {n_pl} playlists (duplicates across playlists not counted)")

# ---------------------------------------------------------------------------
# Playlist selector
# ---------------------------------------------------------------------------
playlists = sorted(df["playlist_name"].unique().tolist())
selected  = st.selectbox("Choose a playlist", playlists, label_visibility="collapsed")

pl_df   = df[df["playlist_name"] == selected].copy()
# Normalize duration to minutes (YC delivers milliseconds, FC delivers minutes)
if "duration_raw" in pl_df.columns and st.session_state.get("mode") == "🔗 Your Collection":
    pl_df["duration_raw"] = pl_df["duration_raw"] / 60000
pl_meta = meta[meta["playlist_name"] == selected].iloc[0]

# Ensure speechiness_log is present for the radar chart (log1p transform used by CLUSTER_FEATURES)
if not af_avg.empty and "speechiness" in af_avg.columns and "speechiness_log" not in af_avg.columns:
    af_avg = af_avg.copy()
    af_avg["speechiness_log"] = np.log1p(af_avg["speechiness"])

# af_avg-derived per-playlist and global audio feature rows
if not af_avg.empty and selected in af_avg["playlist_name"].values:
    pl_af     = af_avg[af_avg["playlist_name"] == selected].iloc[0]
    global_af = af_avg.mean(numeric_only=True)
else:
    pl_af     = None
    global_af = None

st.markdown("<hr style='border-color:#333;margin-top:16px;margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 1 — Header metrics
# ---------------------------------------------------------------------------
total_tracks   = len(pl_df)
unique_artists = pl_df["artist_name"].nunique()
followers      = int(pl_meta["followers"])

if "added_at" in pl_df.columns:
    first_added = pd.to_datetime(pl_df["added_at"].min()).strftime("%b %Y")
    last_added  = pd.to_datetime(pl_df["added_at"].max()).strftime("%b %d, %Y")
else:
    first_added = "N/A"
    last_added  = "N/A"

k1, k2, k3, k4, k5 = st.columns(5)
with k1: st.markdown(kpi_card("🎵", "Tracks", str(total_tracks)), unsafe_allow_html=True)
with k2: st.markdown(kpi_card("🎤", "Artists", str(unique_artists), "primary only"), unsafe_allow_html=True)
with k3: st.markdown(kpi_card("👥", "Followers", f"{followers:,}"), unsafe_allow_html=True)
with k4: st.markdown(kpi_card("📅", "First Added", first_added), unsafe_allow_html=True)
with k5: st.markdown(kpi_card("🆕", "Last Added", last_added), unsafe_allow_html=True)

st.markdown("<hr style='border-color:#333;margin-top:24px;margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 2 — Track highlights
# ---------------------------------------------------------------------------
st.markdown("## Track Highlights")
st.markdown(
    "<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>Standout tracks at the extremes of duration, popularity and release year.</p>",
    unsafe_allow_html=True,
)

col1, col2, col3 = st.columns(3)

with col1:
    if "duration_raw" in pl_df.columns:
        longest_row  = pl_df.loc[pl_df["duration_raw"].idxmax()]
        shortest_row = pl_df.loc[pl_df["duration_raw"].idxmin()]
        st.markdown(
            highlight_card("⏱️", "Longest Track", longest_row["track_name"], longest_row["artist_display"], fmt_duration(longest_row["duration_raw"])) +
            highlight_card("⚡", "Shortest Track", shortest_row["track_name"], shortest_row["artist_display"], fmt_duration(shortest_row["duration_raw"])),
            unsafe_allow_html=True,
        )

with col2:
    if "popularity_raw" in pl_df.columns:
        most_pop_row  = pl_df.loc[pl_df["popularity_raw"].idxmax()]
        least_pop_row = pl_df.loc[pl_df["popularity_raw"].idxmin()]
        st.markdown(
            highlight_card("⭐", "Most Popular", most_pop_row["track_name"], most_pop_row["artist_display"], f"{int(most_pop_row['popularity_raw'])} pts") +
            highlight_card("💀", "Least Popular", least_pop_row["track_name"], least_pop_row["artist_display"], f"{int(least_pop_row['popularity_raw'])} pts"),
            unsafe_allow_html=True,
        )

with col3:
    if "release_year" in pl_df.columns:
        _ry = pl_df["release_year"].dropna()
        if not _ry.empty:
            oldest_row = pl_df.loc[_ry.idxmin()]
            newest_row = pl_df.loc[_ry.idxmax()]
            st.markdown(
                highlight_card("📻", "Oldest Track", oldest_row["track_name"], oldest_row["artist_display"], str(int(oldest_row["release_year"]))) +
                highlight_card("🆕", "Newest Track", newest_row["track_name"], newest_row["artist_display"], str(int(newest_row["release_year"]))),
                unsafe_allow_html=True,
            )

st.markdown("<hr style='border-color:#333;margin-top:24px;margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 3 — Averages
# ---------------------------------------------------------------------------
st.markdown("## Averages")

avg_dur  = pl_df["duration_raw"].mean() if "duration_raw" in pl_df.columns else None
avg_pop  = pl_df["popularity_raw"].mean() if "popularity_raw" in pl_df.columns else None
avg_year = pl_df["release_year"].dropna().mean() if "release_year" in pl_df.columns else None
top_artist       = pl_df["artist_name"].value_counts().index[0]
top_artist_count = pl_df["artist_name"].value_counts().iloc[0]

a1, a2, a3, a4 = st.columns(4)
with a1: st.markdown(kpi_card("⏱️", "Avg Duration",     fmt_duration(avg_dur) if avg_dur is not None else "N/A"), unsafe_allow_html=True)
with a2: st.markdown(kpi_card("⭐", "Avg Popularity",   f"{avg_pop:.1f}" if avg_pop is not None else "N/A"), unsafe_allow_html=True)
with a3: st.markdown(kpi_card("📅", "Avg Release Year", f"{avg_year:.0f}" if avg_year is not None else "N/A"), unsafe_allow_html=True)
with a4: st.markdown(kpi_card("🎤", "Top Artist",       top_artist, f"{top_artist_count} tracks"), unsafe_allow_html=True)

st.markdown("<hr style='border-color:#333;margin-top:24px;margin-bottom:24px;'>", unsafe_allow_html=True)
# ---------------------------------------------------------------------------
# Section 4 — Top Artists
# ---------------------------------------------------------------------------
st.markdown("## Top Artists")
st.markdown(
    "<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>The most represented artists in this playlist — primary artists only, featured artists not counted.</p>",
    unsafe_allow_html=True,
)

top_artists = (
    pl_df["artist_name"]
    .value_counts()
    .head(5)
    .reset_index()
)
top_artists.columns = ["artist", "tracks"]
top_artists_pct = top_artists["tracks"].sum() / total_tracks * 100
max_tracks_artist = top_artists["tracks"].max()
medals = ["🥇", "🥈", "🥉", "4.", "5."]

cards_html = []
for i, row in top_artists.iterrows():
    pct  = row["tracks"] / max_tracks_artist
    card_lines = [
        "<div style='background:#282828;border-radius:12px;padding:14px 18px;border:1px solid #333;margin-bottom:10px;'>",
        "<div style='display:flex;justify-content:space-between;align-items:center;'>",
        f"<span style='color:#FFFFFF;font-weight:700;font-size:0.95rem;'>{medals[i]} {row['artist']}</span>",
        f"<span style='color:#1DB954;font-weight:800;font-size:0.9rem;'>{row['tracks']} tracks</span>",
        "</div>",
        "<div style='margin-top:8px;background:#333;border-radius:4px;height:4px;'>",
        f"<div style='width:{pct*100:.0f}%;background:#1DB954;height:4px;border-radius:4px;'></div>",
        "</div>",
        "</div>",
    ]
    cards_html.append("".join(card_lines))

col1, col2 = st.columns([2, 1])
with col1:
    st.markdown("".join(cards_html), unsafe_allow_html=True)
with col2:
    st.markdown(
        f"""
        <div style='background:#282828;border-radius:14px;padding:28px 24px;border:1px solid #333;
                    display:flex;flex-direction:column;align-items:center;justify-content:center;
                    height:100%;text-align:center;'>
            <div style='font-size:2.4rem;font-weight:800;color:#1DB954;'>{top_artists_pct:.0f}%</div>
            <div style='color:#B3B3B3;font-size:0.78rem;text-transform:uppercase;
                        letter-spacing:0.06em;margin-top:8px;'>of playlist</div>
            <div style='color:#FFFFFF;font-size:0.85rem;margin-top:6px;'>covered by top 5 artists</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<hr style='border-color:#333;margin-top:24px;margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 4b — Duplicated tracks within this playlist
# ---------------------------------------------------------------------------

# Raw per-playlist data with real Spotify IDs (used for duplicate detection).
# Rebuilt from session state so skipped/failed tracks use their real Spotify IDs, not synthetic ones.
if st.session_state.get("mode") == "🔗 Your Collection" and st.session_state.get("uc_active"):
    _pl_all_raw = [
        t for t in (
            st.session_state.get("uc_enriched", [])
            + st.session_state.get("uc_skipped", [])
            + st.session_state.get("uc_failed", [])
        )
        if t.get("playlist_name") == selected
    ]
    pl_raw_df = (
        pd.DataFrame(_pl_all_raw).rename(columns={"id": "track_id", "name": "track_name", "artists": "artist_name"})
        if _pl_all_raw else pd.DataFrame(columns=["track_id", "track_name", "artist_name"])
    )
    _pl_artist_col = "artist_name"
else:
    pl_raw_df      = pl_df.copy()
    _pl_artist_col = "artist_display" if "artist_display" in pl_raw_df.columns else "artist_name"

pl_raw_df = pl_raw_df[pl_raw_df["track_id"].notna() & (pl_raw_df["track_id"].astype(str) != "")]

st.markdown("## Exact Duplicates")
st.markdown(
    "<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>"
    "Same Spotify ID saved more than once in this playlist.</p>",
    unsafe_allow_html=True,
)

_pl_id_groups = (
    pl_raw_df.groupby("track_id")
    .agg(count=("track_id", "count"), track_name=("track_name", "first"), artist=(_pl_artist_col, "first"))
    .reset_index()
)
_pl_id_dupes = _pl_id_groups[_pl_id_groups["count"] > 1].sort_values("count", ascending=False).reset_index(drop=True)

if _pl_id_dupes.empty:
    st.markdown(
        "<div style='background:#1a1a1a;border:1px solid #333;border-radius:10px;"
        "padding:14px 18px;color:#B3B3B3;font-size:0.9rem;'>"
        "No exact duplicates — every Spotify ID appears only once.</div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f"<div style='background:#282828;border-radius:14px;padding:14px 20px;"
        f"border:1px solid #333;display:inline-block;margin-bottom:14px;'>"
        f"<span style='color:#B3B3B3;font-size:0.78rem;font-weight:600;"
        f"text-transform:uppercase;letter-spacing:.06em;'>Exact Duplicates</span><br>"
        f"<span style='color:#1DB954;font-size:2rem;font-weight:800;'>{len(_pl_id_dupes)}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.dataframe(
        _pl_id_dupes[["track_name", "artist", "count"]].rename(columns={
            "track_name": "Track", "artist": "Artist", "count": "Times Saved",
        }),
        use_container_width=True,
        hide_index=True,
    )

st.markdown("## Different Versions")
st.markdown(
    "<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>"
    "Same song name and artist, different Spotify IDs — separate recordings or releases.</p>",
    unsafe_allow_html=True,
)

_pl_ver_groups = (
    pl_raw_df.groupby(["track_name", "artist_name"])
    .agg(n_unique_ids=("track_id", "nunique"), total=("track_id", "count"))
    .reset_index()
)
_pl_versions = _pl_ver_groups[
    (_pl_ver_groups["total"] > 1) & (_pl_ver_groups["n_unique_ids"] > 1)
].sort_values("track_name").reset_index(drop=True)

if _pl_versions.empty:
    st.markdown(
        "<div style='background:#1a1a1a;border:1px solid #333;border-radius:10px;"
        "padding:14px 18px;color:#B3B3B3;font-size:0.9rem;'>"
        "No different versions found.</div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f"<div style='background:#282828;border-radius:14px;padding:14px 20px;"
        f"border:1px solid #333;display:inline-block;margin-bottom:14px;'>"
        f"<span style='color:#B3B3B3;font-size:0.78rem;font-weight:600;"
        f"text-transform:uppercase;letter-spacing:.06em;'>Different Versions</span><br>"
        f"<span style='color:#1DB954;font-size:2rem;font-weight:800;'>{len(_pl_versions)}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.dataframe(
        _pl_versions[["track_name", "artist_name", "n_unique_ids"]].rename(columns={
            "track_name": "Track", "artist_name": "Artist", "n_unique_ids": "Versions",
        }),
        use_container_width=True,
        hide_index=True,
    )

st.markdown("<hr style='border-color:#333;margin-top:24px;margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 5 — Audio DNA radar
# ---------------------------------------------------------------------------
st.markdown("## Audio DNA")
st.markdown(
    "<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>This playlist vs the global average across all playlists.</p>",
    unsafe_allow_html=True,
)

_radar_feats_avail = [f for f in CLUSTER_FEATURES if f in af_avg.columns] if not af_avg.empty else []
_pl_has_audio = (
    pl_af is not None
    and global_af is not None
    and _radar_feats_avail
    and not pl_af[_radar_feats_avail].isna().all()
)

if _pl_has_audio:
    def normalize_tempo(val):
        return (val - 60) / (200 - 60)

    _radar_feats = _radar_feats_avail
    pl_vals     = [pl_af[f] if f != "tempo" else normalize_tempo(pl_af[f]) for f in _radar_feats]
    global_vals = [global_af[f] if f != "tempo" else normalize_tempo(global_af[f]) for f in _radar_feats]

    fig_radar = go.Figure()
    fig_radar.add_trace(go.Scatterpolar(
        r=pl_vals + [pl_vals[0]],
        theta=_radar_feats + [_radar_feats[0]],
        fill="toself",
        name=selected,
        line=dict(color="#1DB954", width=2),
        fillcolor="rgba(29,185,84,0.15)",
        hovertemplate="%{theta}: %{r:.2f}<extra></extra>",
    ))
    fig_radar.add_trace(go.Scatterpolar(
        r=global_vals + [global_vals[0]],
        theta=_radar_feats + [_radar_feats[0]],
        fill="toself",
        name="Global Avg",
        line=dict(color="#B3B3B3", width=1.5, dash="dot"),
        fillcolor="rgba(179,179,179,0.07)",
        hovertemplate="%{theta}: %{r:.2f}<extra></extra>",
    ))
    fig_radar.update_layout(
        polar=dict(
            bgcolor="#181818",
            radialaxis=dict(visible=True, range=[0, 1], gridcolor="#333", tickfont=dict(color="#B3B3B3")),
            angularaxis=dict(gridcolor="#333", tickfont=dict(color="#FFFFFF")),
        ),
        paper_bgcolor="#121212",
        font_color="#B3B3B3",
        legend=dict(bgcolor="#181818", font=dict(color="#B3B3B3")),
        margin=dict(t=40, b=40, l=40, r=40),
        height=420,
    )
    st.plotly_chart(fig_radar, use_container_width=True)
else:
    if st.session_state.get("mode") == "🔗 Your Collection":
        st.info(
            "Audio features aren't available for this playlist — "
            "these tracks weren't found in the audio database during enrichment."
        )
    else:
        st.info("Audio features haven't been loaded for this playlist yet.")

st.markdown("<hr style='border-color:#333;margin-top:24px;margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 6 — Era Breakdown
# ---------------------------------------------------------------------------
st.markdown("## Era Breakdown")
st.markdown(
    "<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>Distribution of tracks by decade and by individual release year. Click a bar in the 'By Decade' chart to view tracks from that era.</p>",
    unsafe_allow_html=True,
)

col1, col2 = st.columns(2)

# -- Decades: one shade of green per era
ERA_COLORS = {
    1950: "#0a3d1a", 1960: "#0d5224", 1970: "#10672e",
    1980: "#137d38", 1990: "#1DB954", 2000: "#25d163",
    2010: "#4dda80", 2020: "#80e8a6",
}

with col1:
    st.markdown("#### By Decade")
    if "decade" in pl_df.columns:
        decade_counts = (
            pl_df["decade"].dropna().astype(int)
            .value_counts().sort_index().reset_index()
        )
        decade_counts.columns = ["decade", "count"]
        decade_counts["label"] = decade_counts["decade"].astype(str) + "s"
        decade_counts["color"] = decade_counts["decade"].map(
            lambda d: ERA_COLORS.get(d, "#1DB954")
        )

        fig_dec = go.Figure(go.Bar(
            x=decade_counts["label"],
            y=decade_counts["count"],
            text=decade_counts["count"],
            textposition="outside",
            marker=dict(color=decade_counts["color"], line_width=0),
            hovertemplate="%{x}: %{y} tracks<extra></extra>",
        ))
        fig_dec.update_layout(
            **{**_BASE_LAYOUT, "margin": dict(t=10, b=10, l=10, r=10)},
            xaxis=dict(gridcolor="#282828", tickfont=dict(color="#FFFFFF")),
            yaxis=dict(gridcolor="#282828"),
        )
        selected_dec = st.plotly_chart(fig_dec, use_container_width=True, on_select="rerun", key="decade_chart")

        if selected_dec and selected_dec.selection and selected_dec.selection.points:
            decade_label = selected_dec.selection.points[0]["x"]
            decade_val   = int(decade_label.replace("s", ""))
            dec_tracks   = (
                pl_df[pl_df["decade"].astype("Int64") == decade_val]
                [[c for c in ["track_name", "artist_display", "release_year", "popularity_raw"] if c in pl_df.columns]]
                .copy()
                .sort_values("popularity_raw", ascending=False) if "popularity_raw" in pl_df.columns
                else pl_df[pl_df["decade"].astype("Int64") == decade_val]
                [[c for c in ["track_name", "artist_display", "release_year"] if c in pl_df.columns]].copy()
            )
            if "release_year" in dec_tracks.columns:
                dec_tracks["release_year"] = dec_tracks["release_year"].fillna(0).astype("Int64")
            dec_tracks = dec_tracks.rename(columns={
                "track_name": "Track", "artist_display": "Artist",
                "release_year": "Year", "popularity_raw": "Popularity",
            })
            st.markdown(
                f"<p style='color:#1DB954;font-weight:700;font-size:1rem;margin-bottom:4px;'>"
                f"📅 {len(dec_tracks)} tracks — {decade_label}</p>",
                unsafe_allow_html=True,
            )
            st.dataframe(dec_tracks.reset_index(drop=True), use_container_width=True, hide_index=True)
    else:
        st.markdown("<p style='color:#B3B3B3;font-size:0.85rem;'>Decade data not available.</p>", unsafe_allow_html=True)
# -- Years: area chart
with col2:
    st.markdown("#### By Year")
    if "release_year" in pl_df.columns:
        year_counts = (
            pl_df["release_year"].dropna().astype(int)
            .value_counts().sort_index().reset_index()
        )
        year_counts.columns = ["year", "count"]

        fig_year = go.Figure(go.Scatter(
            x=year_counts["year"],
            y=year_counts["count"],
            mode="lines+markers",
            fill="tozeroy",
            fillcolor="rgba(29,185,84,0.12)",
            line=dict(color="#1DB954", width=2),
            marker=dict(color="#1DB954", size=5),
            hovertemplate="Year %{x}: %{y} tracks<extra></extra>",
        ))
        fig_year.update_layout(
            **{**_BASE_LAYOUT, "margin": dict(t=10, b=10, l=10, r=10)},
            xaxis=dict(gridcolor="#282828", tickfont=dict(color="#FFFFFF", size=9)),
            yaxis=dict(gridcolor="#282828"),
        )
        st.plotly_chart(fig_year, use_container_width=True)
    else:
        st.markdown("<p style='color:#B3B3B3;font-size:0.85rem;'>Release year data not available.</p>", unsafe_allow_html=True)

st.markdown("<hr style='border-color:#333;margin-top:24px;margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 7 — Top Genres (lollipop)
# ---------------------------------------------------------------------------
st.markdown("## Top Genres")
st.markdown(
    "<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>Most represented genres based on primary artist tags.</p>",
    unsafe_allow_html=True,
)

if "artist_genres" in pl_df.columns:
    genres_series = (
        pl_df["artist_genres"]
        .dropna()
        .str.split(", ")
        .explode()
        .str.strip()
    )
    genres_series = genres_series[genres_series != ""]
    top_genres = genres_series.value_counts().head(15).reset_index()
    top_genres.columns = ["genre", "count"]
    top_genres = top_genres.sort_values("count")

    fig_genres = go.Figure()
    for _, row in top_genres.iterrows():
        fig_genres.add_trace(go.Scatter(
            x=[0, row["count"]],
            y=[row["genre"], row["genre"]],
            mode="lines",
            line=dict(color="#333", width=2),
            showlegend=False,
            hoverinfo="skip",
        ))
    fig_genres.add_trace(go.Scatter(
        x=top_genres["count"],
        y=top_genres["genre"],
        mode="markers+text",
        marker=dict(color="#1DB954", size=12, line_width=0),
        text=top_genres["count"],
        textposition="middle right",
        textfont=dict(color="#FFFFFF", size=11),
        hovertemplate="%{y}: %{x} tracks<extra></extra>",
        showlegend=False,
    ))
    fig_genres.update_layout(
        **{**_BASE_LAYOUT, "margin": dict(t=10, b=10, l=10, r=60)},
        xaxis=dict(gridcolor="#282828", tickfont=dict(color="#B3B3B3")),
        yaxis=dict(tickfont=dict(color="#FFFFFF", size=11), gridcolor="#282828"),
        height=420,
    )
    st.plotly_chart(fig_genres, use_container_width=True)
else:
    st.markdown("<p style='color:#B3B3B3;font-size:0.85rem;'>Genre data not available for this collection.</p>", unsafe_allow_html=True)

st.markdown("<hr style='border-color:#333;margin-top:24px;margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 8 — Energy vs Valence scatter (Mood Map)
# ---------------------------------------------------------------------------
st.markdown("## Mood Map")
st.markdown(
    "<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>"
    "Energy vs Valence for every track — hover to explore. "
    "Top-right = loud &amp; happy · Bottom-left = quiet &amp; somber."
    "</p>",
    unsafe_allow_html=True,
)

_scatter_audio = [c for c in ["energy", "valence"] if c in pl_df.columns]
scatter_df = pl_df[["track_name", "artist_display"] + _scatter_audio +
                   (["popularity_raw"] if "popularity_raw" in pl_df.columns else [])].dropna()

if len(_scatter_audio) == 2:
    if "popularity_raw" in pl_df.columns:
        fig_scatter = px.scatter(
            scatter_df,
            x="valence",
            y="energy",
            size="popularity_raw",
            size_max=18,
            color="energy",
            color_continuous_scale=[[0, "#0a3d1a"], [0.5, "#1DB954"], [1, "#80e8a6"]],
            hover_data={"track_name": True, "artist_display": True, "popularity_raw": True, "valence": False, "energy": False},
            labels={"valence": "Valence →", "energy": "Energy ↑"},
        )
        fig_scatter.update_traces(
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "%{customdata[1]}<br>"
                "Energy: %{y:.2f} · Valence: %{x:.2f}<br>"
                "Popularity: %{customdata[2]}"
                "<extra></extra>"
            ),
            marker_line_width=0,
        )
    else:
        fig_scatter = px.scatter(
            scatter_df,
            x="valence",
            y="energy",
            color="energy",
            color_continuous_scale=[[0, "#0a3d1a"], [0.5, "#1DB954"], [1, "#80e8a6"]],
            hover_data={"track_name": True, "artist_display": True, "valence": False, "energy": False},
            labels={"valence": "Valence →", "energy": "Energy ↑"},
        )
        fig_scatter.update_traces(
            marker=dict(size=10, line_width=0),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "%{customdata[1]}<br>"
                "Energy: %{y:.2f} · Valence: %{x:.2f}"
                "<extra></extra>"
            ),
        )

    fig_scatter.add_hline(y=0.5, line_dash="dot", line_color="#333", line_width=1)
    fig_scatter.add_vline(x=0.5, line_dash="dot", line_color="#333", line_width=1)

    for x, y, label in [
        (0.25, 0.93, "Turbulent"), (0.75, 0.93, "Happy"),
        (0.25, 0.07, "Dark"),      (0.75, 0.07, "Peaceful"),
    ]:
        fig_scatter.add_annotation(
            x=x, y=y, text=label, showarrow=False,
            font=dict(color="#FFFFFF", size=11, family="Plus Jakarta Sans"),
            bgcolor="rgba(0,0,0,0.55)",
            bordercolor="rgba(255,255,255,0.08)",
            borderwidth=1,
            borderpad=4,
            xref="x", yref="y",
        )
    fig_scatter.update_layout(
        **{**_BASE_LAYOUT, "margin": dict(t=20, b=40, l=40, r=20)},
        xaxis=dict(gridcolor="#282828", tickfont=dict(color="#B3B3B3"), range=[0, 1]),
        yaxis=dict(gridcolor="#282828", tickfont=dict(color="#B3B3B3"), range=[0, 1]),
        coloraxis_showscale=False,
        height=420,
    )
    st.plotly_chart(fig_scatter, use_container_width=True)
else:
    st.markdown(
        "<p style='color:#B3B3B3;font-size:0.85rem;'>Mood map not available — energy and valence data missing.</p>",
        unsafe_allow_html=True,
    )

st.markdown("<hr style='border-color:#333;margin-top:24px;margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 9 — Tracks added by month (Playlist Growth)
# ---------------------------------------------------------------------------
st.markdown("## Playlist Growth")
st.markdown(
    "<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>"
    "When tracks were added — reveals whether this playlist was built all at once or grew over time."
    "</p>",
    unsafe_allow_html=True,
)

if st.session_state.get("mode") != "🔗 Your Collection":
    monthly_raw = load_tracks_added_by_month(selected)
else:
    if "added_at" in pl_df.columns:
        _monthly = (
            pl_df.assign(_month=pd.to_datetime(pl_df["added_at"]).dt.to_period("M").astype(str))
            .groupby("_month")
            .size()
            .reset_index(name="count")
        )
        _monthly.columns = ["period", "count"]
        monthly_raw = _monthly
    else:
        monthly_raw = pd.DataFrame()

if monthly_raw.empty or len(monthly_raw) <= 1:
    # Check if it's the "added all at once" scenario vs genuinely missing data
    if "added_at" in pl_df.columns and pl_df["added_at"].notna().any():
        single_date = pd.to_datetime(pl_df["added_at"].dropna().iloc[0]).strftime("%B %d, %Y")
        st.markdown(
            f"""
            <div style='background:#282828;border-radius:12px;padding:20px 24px;border:1px solid #333;'>
                <div style='font-size:1.6rem;margin-bottom:8px;'>⚡</div>
                <div style='color:#FFFFFF;font-weight:700;font-size:1rem;margin-bottom:4px;'>Built in a single session</div>
                <div style='color:#B3B3B3;font-size:0.85rem;'>
                    All {total_tracks} tracks were added on <span style='color:#1DB954;font-weight:700;'>{single_date}</span> —
                    this playlist was assembled all at once and never touched again.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<p style='color:#B3B3B3;font-size:0.85rem;'>Not enough date data to show growth timeline.</p>",
            unsafe_allow_html=True,
        )
else:
    monthly = monthly_raw.copy()
    monthly.columns = ["period", "count"]
    monthly["month"] = pd.to_datetime(monthly["period"], format="%Y-%m")

    # Annotation: peak month
    peak_idx   = monthly["count"].idxmax()
    peak_month = monthly.loc[peak_idx, "month"].strftime("%b %Y")
    peak_count = int(monthly.loc[peak_idx, "count"])

    fig_growth = go.Figure(go.Scatter(
        x=monthly["month"],
        y=monthly["count"],
        mode="lines+markers",
        fill="tozeroy",
        fillcolor="rgba(29,185,84,0.10)",
        line=dict(color="#1DB954", width=2),
        marker=dict(color="#1DB954", size=5),
        hovertemplate="%{x|%b %Y}: %{y} tracks added<extra></extra>",
    ))

    # Peak annotation
    fig_growth.add_annotation(
        x=monthly.loc[peak_idx, "month"],
        y=peak_count,
        text=f"Peak: {peak_count} tracks",
        showarrow=True,
        arrowhead=2,
        arrowcolor="#1DB954",
        arrowwidth=1.5,
        font=dict(color="#1DB954", size=11),
        bgcolor="#181818",
        bordercolor="#333",
        borderwidth=1,
        borderpad=4,
        yshift=10,
    )

    fig_growth.update_layout(
        **{**_BASE_LAYOUT, "margin": dict(t=40, b=20, l=10, r=10)},
        xaxis=dict(gridcolor="#282828", tickfont=dict(color="#B3B3B3"), tickformat="%b %Y"),
        yaxis=dict(gridcolor="#282828", tickfont=dict(color="#B3B3B3")),
        height=300,
    )
    st.plotly_chart(fig_growth, use_container_width=True)

    # Summary line below chart
    span_months = (monthly["month"].max() - monthly["month"].min()).days // 30 + 1
    total_months_active = len(monthly)
    st.markdown(
        f"<p style='color:#1DB954;font-weight:700;font-size:0.95rem;'>"
        f"📆 {total_tracks} tracks · {total_months_active} active months · "
        f"peak in {peak_month} ({peak_count} tracks)"
        f"</p>",
        unsafe_allow_html=True,
    )

st.markdown("<hr style='border-color:#333;margin-top:24px;margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 10 — Similar Playlists
# ---------------------------------------------------------------------------
if df["playlist_name"].nunique() > 1:
    st.markdown("## Similar Playlists")
    st.markdown(
        "<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>"
        "Closest playlists by Euclidean distance across audio feature averages.</p>",
        unsafe_allow_html=True,
    )

    if not af_avg.empty and pl_af is not None:
        numeric_features = ["energy", "acousticness", "valence", "danceability", "instrumentalness", "tempo"]
        _avail_feats = [f for f in numeric_features if f in af_avg.columns]

        if _avail_feats:
            # Normalise tempo for fair distance
            af_norm = af_avg.copy()
            if "tempo" in af_norm.columns:
                af_norm["tempo"] = (af_norm["tempo"] - 60) / (200 - 60)

            selected_vec = af_norm[af_norm["playlist_name"] == selected][_avail_feats].values[0]
            others = af_norm[af_norm["playlist_name"] != selected].copy()
            others["distance"] = others[_avail_feats].apply(
                lambda row: np.sqrt(np.sum((row.values - selected_vec) ** 2)), axis=1
            )
            similar = others.sort_values("distance").head(5).reset_index(drop=True)

            max_dist = similar["distance"].max()
            similar["similarity_pct"] = (1 - similar["distance"] / max_dist) * 100
            similar = similar[similar["similarity_pct"].round() > 0].reset_index(drop=True)

            if similar.empty:
                st.markdown(
                    "<p style='color:#B3B3B3;font-size:0.85rem;'>No similar playlists found.</p>",
                    unsafe_allow_html=True,
                )
            else:
                medals = ["🥇", "🥈", "🥉", "4.", "5."]

                cards_html = []
                for i, row in similar.iterrows():
                    pct        = row["similarity_pct"]
                    dist_score = f"{pct:.0f}% match"
                    medal      = medals[i] if i < len(medals) else f"{i+1}."
                    card_lines = [
                        "<div style='background:#282828;border-radius:12px;padding:14px 18px;border:1px solid #333;margin-bottom:10px;'>",
                        "<div style='display:flex;justify-content:space-between;align-items:center;'>",
                        f"<span style='color:#FFFFFF;font-weight:700;font-size:0.95rem;'>{medal} {row['playlist_name']}</span>",
                        f"<span style='color:#1DB954;font-weight:800;font-size:0.9rem;'>{dist_score}</span>",
                        "</div>",
                        "<div style='margin-top:8px;background:#333;border-radius:4px;height:4px;'>",
                        f"<div style='width:{pct:.0f}%;background:#1DB954;height:4px;border-radius:4px;'></div>",
                        "</div>",
                        "</div>",
                    ]
                    cards_html.append("".join(card_lines))

                st.markdown("".join(cards_html), unsafe_allow_html=True)
    else:
        st.markdown(
            "<p style='color:#B3B3B3;font-size:0.85rem;'>Audio feature data not available for similarity comparison.</p>",
            unsafe_allow_html=True,
        )

    st.markdown("<hr style='border-color:#333;margin-top:24px;margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 11 — Full track table
# ---------------------------------------------------------------------------
st.markdown("## All Tracks")

_base_cols = ["track_name", "artist_display"]
_optional  = ["release_year", "duration_raw", "popularity_raw"]
_audio     = ["energy", "valence", "danceability", "acousticness"]
_table_cols = _base_cols + [c for c in _optional if c in pl_df.columns] + [c for c in _audio if c in pl_df.columns]

table = pl_df[_table_cols].copy()

if "duration_raw" in table.columns:
    table["duration_raw"] = table["duration_raw"].apply(fmt_duration)
if "release_year" in table.columns:
    table["release_year"] = table["release_year"].fillna(0).astype("Int64")
if "popularity_raw" in table.columns:
    table["popularity_raw"] = table["popularity_raw"].astype(int)

table = table.rename(columns={
    "track_name":     "Track",
    "artist_display": "Artist",
    "release_year":   "Year",
    "duration_raw":   "Duration",
    "popularity_raw": "Popularity",
    "energy":         "Energy",
    "valence":        "Valence",
    "danceability":   "Danceability",
    "acousticness":   "Acousticness",
})

st.dataframe(
    table.reset_index(drop=True),
    use_container_width=True,
    hide_index=True,
)
