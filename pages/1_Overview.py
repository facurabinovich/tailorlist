import streamlit as st
import plotly.graph_objects as go
import re
import pandas as pd
from db.queries import get_all_tracks
from utils import inject_global_css, inject_sidebar_nav, spotify_icon_html, page_brand_html

inject_global_css()
inject_sidebar_nav("Overview")
from utils import check_collection_mode
if not check_collection_mode():
    st.stop()

# ---------------------------------------------------------------------------
# Load & derive — works for both DB and Your Collection modes
# ---------------------------------------------------------------------------
df = get_all_tracks()

# force fresh load if album_name missing (cache may be stale)
if "album_name" not in df.columns:
    st.cache_data.clear()
    st.rerun()

deduped = df.drop_duplicates(subset="track_id").copy()

mode               = st.session_state.get("mode", "🎵 Demo Collection")
is_your_collection = (mode == "🔗 Your Collection")

# Tracks per playlist
counts = (
    df.groupby("playlist_name")
    .size()
    .reset_index(name="track_count")
    .sort_values("track_count", ascending=False)
)

# Top 20 artists by unique track count
top_artists = (
    df.groupby("artist_name")["track_id"]
    .nunique()
    .reset_index(name="track_count")
    .sort_values("track_count", ascending=False)
    .head(20)
)

# Dynamic threshold
min_t = min(5, max(1, len(deduped) // 10))

# Top 5 artists by avg popularity (min_t unique tracks required)
top_popular_artists = pd.DataFrame()
if "popularity_raw" in df.columns:
    top_popular_artists = (
        df.groupby("artist_name")
        .agg(track_count=("track_id", "nunique"), avg_popularity=("popularity_raw", "mean"))
        .query(f"track_count >= {min_t}")
        .sort_values("avg_popularity", ascending=False)
        .head(20)
        .reset_index()
    )

# Top 5 albums by tracks saved
top_albums = (
    df.groupby(["album_name", "artist_name"])
    .agg(track_count=("track_id", "nunique"), avg_popularity=("popularity_raw", "mean"))
    .sort_values(["track_count", "avg_popularity"], ascending=False)
    .head(20)
    .reset_index()
) if ("album_name" in df.columns and "popularity_raw" in df.columns) else pd.DataFrame()

# Additions timeline
timeline = pd.DataFrame()
if "added_at" in df.columns and df["added_at"].notna().any():
    _df = df.copy()
    _df["added_at"] = pd.to_datetime(_df["added_at"], errors="coerce")
    timeline = (
        _df.dropna(subset=["added_at"])
        .assign(year_month=lambda x: x["added_at"].dt.strftime("%Y-%m"))
        .drop_duplicates(subset=["track_id", "year_month"])
        .groupby("year_month")
        .size()
        .reset_index(name="tracks_added")
        .sort_values("year_month")
    )

# KPIs
total_tracks   = len(deduped)
total_artists  = df["artist_name"].nunique()
total_playlist = df["playlist_name"].nunique()
avg_popularity = deduped["popularity_raw"].mean() if "popularity_raw" in deduped.columns else None
decade_mode    = int(deduped["decade"].mode()[0]) if "decade" in deduped.columns and deduped["decade"].notna().any() else None

# duration_raw: DB = minutes float | Your Collection = milliseconds
avg_duration = None
if "duration_raw" in deduped.columns:
    raw = deduped["duration_raw"].mean()
    if pd.notna(raw):
        avg_duration = (raw / 60000) if is_your_collection else raw

import datetime
listening_age = None
median_year   = None
est_birth     = None
if "release_year" in deduped.columns and deduped["release_year"].notna().any():
    median_year   = int(deduped["release_year"].dropna().median())
    est_birth     = median_year - 16
    listening_age = datetime.date.today().year - est_birth

oldest_year = newest_year = span = None

# Oldest & newest track
oldest_track = newest_track = None
if "release_year" in deduped.columns and deduped["release_year"].notna().any():
    valid = deduped.dropna(subset=["release_year"]).copy()
    valid["release_year"] = valid["release_year"].astype(int)
    oldest_track = valid.loc[valid["release_year"].idxmin()]
    newest_track = valid.loc[valid["release_year"].idxmax()]
    oldest_year  = int(valid["release_year"].min())
    newest_year  = int(valid["release_year"].max())
    span         = newest_year - oldest_year


def fmt_duration(minutes: float) -> str:
    m = int(minutes)
    s = int(round((minutes - m) * 60))
    return f"{m}:{s:02d}"


MEDALS   = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
BIN_SIZE = 5  # popularity histogram bin width — must match xbins below


def kpi_card(icon: str, label: str, value: str, subtitle: str = "") -> str:
    sub_html = f'<span style="color:#B3B3B3;font-size:0.75rem;margin-top:2px;">{subtitle}</span>' if subtitle else ""
    return (
        f'<div style="background:#282828;border-radius:14px;padding:22px 24px;border:1px solid #333;'
        f'display:flex;flex-direction:column;gap:8px;height:100%;">'
        f'<span style="font-size:1.6rem;">{icon}</span>'
        f'<span style="color:#B3B3B3;font-size:0.78rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase;">{label}</span>'
        f'<span style="color:#FFFFFF;font-size:2rem;font-weight:800;line-height:1.1;">{value}</span>'
        f'{sub_html}'
        f'</div>'
    )


def ranking_card(medal: str, title: str, subtitle: str, value: str, bar_pct: int, footer: str) -> str:
    sub_html = f'<div style="color:#B3B3B3;font-size:0.8rem;margin-bottom:8px;">{subtitle}</div>' if subtitle else ""
    return (
        f'<div style="background:#282828;border-radius:12px;padding:16px 20px;border:1px solid #333;margin-bottom:10px;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">'
        f'<span style="font-size:1rem;font-weight:700;color:#FFFFFF;">{medal} {title}</span>'
        f'<span style="color:#1DB954;font-weight:800;font-size:1.1rem;">{value}</span>'
        f'</div>'
        f'{sub_html}'
        f'<div style="background:#333;border-radius:4px;height:5px;width:100%;margin-bottom:6px;">'
        f'<div style="background:#1DB954;height:5px;border-radius:4px;width:{bar_pct}%;"></div>'
        f'</div>'
        f'<span style="color:#B3B3B3;font-size:0.75rem;">{footer}</span>'
        f'</div>'
    )
# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(page_brand_html(), unsafe_allow_html=True)
st.markdown(
    f"<div style='display:flex;align-items:center;gap:18px;margin-bottom:4px;'>"
    f"{spotify_icon_html(36)}"
    f"<div>"
    f"<h1 style='margin:0;font-size:2.6rem;font-weight:900;color:#FFFFFF;line-height:1.1;'>Overview</h1>"
    f"<p style='margin:0;color:#B3B3B3;font-size:1rem;'>A bird's eye view of the entire collection.</p>"
    f"</div>"
    f"</div>",
    unsafe_allow_html=True,
)
st.markdown("<hr style='border-color:#333;margin-top:16px;margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Active collection banner
# ---------------------------------------------------------------------------
if st.session_state.get("mode") == "🔗 Your Collection" and st.session_state.get("uc_active"):
    n_pl  = df["playlist_name"].nunique()
    st.info(f"🎵 Viewing: Your Collection — {total_tracks:,} unique tracks across {n_pl} playlists (duplicates across playlists not counted)")

# ---------------------------------------------------------------------------
# KPI Cards — 2 rows × 3
# ---------------------------------------------------------------------------
k1, k2, k3 = st.columns(3)
k1.markdown(kpi_card("🎵", "Unique Tracks",  f"{total_tracks:,}"),  unsafe_allow_html=True)
k2.markdown(kpi_card("🎤", "Artists",        f"{total_artists:,}", "primary artists only"), unsafe_allow_html=True)
k3.markdown(kpi_card("📂", "Playlists",      str(total_playlist)),  unsafe_allow_html=True)

st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

k4, k5, k6 = st.columns(3)
k4.markdown(kpi_card("⭐", "Avg Popularity", f"{avg_popularity:.1f}" if avg_popularity is not None else "N/A"), unsafe_allow_html=True)
k5.markdown(kpi_card("📅", "Top Decade",     f"{decade_mode}s"       if decade_mode    is not None else "N/A"), unsafe_allow_html=True)
k6.markdown(kpi_card("⏱️", "Avg Duration",   fmt_duration(avg_duration) if avg_duration is not None else "N/A"), unsafe_allow_html=True)

st.markdown("<hr style='border-color:#333;margin-top:28px;margin-bottom:8px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Oldest & Newest Track cards
# ---------------------------------------------------------------------------
if oldest_track is not None and newest_track is not None:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"""
        <div style="background:#282828;border-radius:14px;padding:20px 24px;border:1px solid #333;">
            <span style="color:#B3B3B3;font-size:0.78rem;font-weight:600;letter-spacing:.06em;
                         text-transform:uppercase;">🕰️ Oldest Track</span>
            <div style="color:#FFFFFF;font-size:1.3rem;font-weight:800;margin-top:8px;
                        white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                {oldest_track['track_name']}
            </div>
            <div style="color:#B3B3B3;font-size:0.9rem;margin-top:4px;">
                {oldest_track['artist_display']}
            </div>
            <div style="color:#1DB954;font-size:1rem;font-weight:700;margin-top:6px;">
                {int(oldest_track['release_year'])}
            </div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div style="background:#282828;border-radius:14px;padding:20px 24px;border:1px solid #333;">
            <span style="color:#B3B3B3;font-size:0.78rem;font-weight:600;letter-spacing:.06em;
                         text-transform:uppercase;">✨ Newest Track</span>
            <div style="color:#FFFFFF;font-size:1.3rem;font-weight:800;margin-top:8px;
                        white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                {newest_track['track_name']}
            </div>
            <div style="color:#B3B3B3;font-size:0.9rem;margin-top:4px;">
                {newest_track['artist_display']}
            </div>
            <div style="color:#1DB954;font-size:1rem;font-weight:700;margin-top:6px;">
                {int(newest_track['release_year'])}
            </div>
        </div>
        """, unsafe_allow_html=True)

if listening_age is not None:
    _stat_label = "color:#B3B3B3;font-size:0.72rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;"
    st.markdown(
        f'<div style="background:#282828;border-radius:12px;padding:16px 28px;border:1px solid #333;margin-top:12px;">'
        f'<div style="display:flex;gap:48px;align-items:center;">'
        f'<div style="display:flex;flex-direction:column;gap:4px;">'
        f'<span style="{_stat_label}">Median Era</span>'
        f'<span style="font-size:1.15rem;font-weight:800;color:#1DB954;">{median_year}</span>'
        f'</div>'
        f'<div style="display:flex;flex-direction:column;gap:4px;">'
        f'<span style="{_stat_label}">Span</span>'
        f'<span style="font-size:1.15rem;font-weight:800;color:#FFFFFF;">{span} yrs</span>'
        f'</div>'
        f'<div style="display:flex;flex-direction:column;gap:4px;">'
        f'<span style="{_stat_label}">Listening Age</span>'
        f'<span style="font-size:1.15rem;font-weight:800;color:#1DB954;">{listening_age} yrs</span>'
        f'</div>'
        f'</div>'
        f'<div style="color:#B3B3B3;font-size:0.78rem;margin-top:8px;">'
        f'Median era {median_year} · est. born {est_birth} · Listening Age {listening_age} yrs'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

st.markdown("<hr style='border-color:#333;margin-top:20px;margin-bottom:8px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 1 — Tracks per Playlist
# ---------------------------------------------------------------------------
st.markdown("## Tracks per Playlist")
st.markdown(
    "<p style='color:#B3B3B3;margin-top:-8px;'>To see the tracks in each playlist, go to the Playlist Detail page in the navigation.</p>", 
    unsafe_allow_html=True
)

counts_sorted = counts.sort_values("track_count", ascending=True)
fig_counts = go.Figure(go.Bar(
    x=counts_sorted["track_count"],
    y=counts_sorted["playlist_name"],
    orientation="h",
    text=counts_sorted["track_count"],
    textposition="outside",
    marker=dict(
        color=counts_sorted["track_count"],
        colorscale=[[0, "#145e2a"], [1, "#1DB954"]],
        showscale=False,
        line=dict(width=0),
    ),
    hovertemplate="<b>%{y}</b><br>%{x} tracks<extra></extra>",
))
fig_counts.update_layout(
    plot_bgcolor="#121212", paper_bgcolor="#121212", font_color="#B3B3B3",
    xaxis=dict(gridcolor="#282828", title="Tracks"),
    yaxis=dict(tickfont=dict(color="#FFFFFF", size=11)),
    margin=dict(t=20, b=20, l=10, r=40),
    height=max(300, len(counts_sorted) * 32),
)
st.plotly_chart(fig_counts, use_container_width=True)
st.markdown("<hr style='border-color:#333;margin-top:8px;margin-bottom:8px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 2 — Top 20 Artists
# ---------------------------------------------------------------------------
st.markdown("## Top 20 Artists")
st.markdown(
    "<p style='color:#B3B3B3;margin-top:-8px;'>Click a bar to see the tracks. Primary artists only — featured artists are not counted.</p>",
    unsafe_allow_html=True,
)

top_sorted = top_artists.sort_values("track_count", ascending=True)
fig_artists = go.Figure(go.Bar(
    x=top_sorted["track_count"],
    y=top_sorted["artist_name"],
    orientation="h",
    text=top_sorted["track_count"],
    textposition="outside",
    marker=dict(color="#1DB954", line=dict(width=0)),
    hovertemplate="<b>%{y}</b><br>%{x} unique tracks<extra></extra>",
))
fig_artists.update_layout(
    plot_bgcolor="#121212", paper_bgcolor="#121212", font_color="#B3B3B3",
    xaxis=dict(gridcolor="#282828", title="Unique Tracks"),
    yaxis=dict(tickfont=dict(color="#FFFFFF", size=11)),
    margin=dict(t=20, b=20, l=10, r=40),
    height=580,
)
selected_artist = st.plotly_chart(fig_artists, use_container_width=True, on_select="rerun", key="top_artists_chart")

if selected_artist and selected_artist.selection and selected_artist.selection.points:
    artist_name = selected_artist.selection.points[0]["y"]
    artist_tracks = (
        deduped[deduped["artist_name"] == artist_name]
        [[c for c in ["track_name", "playlist_name", "popularity_raw", "release_year"] if c in deduped.columns]]
        .copy()
        .sort_values("popularity_raw", ascending=False)
    )
    if "release_year" in artist_tracks.columns:
        artist_tracks["release_year"] = artist_tracks["release_year"].fillna(0).astype(int)
    artist_tracks = artist_tracks.rename(columns={
        "track_name": "Track", "playlist_name": "Playlist",
        "popularity_raw": "Popularity", "release_year": "Year",
    })
    st.markdown(
        f"<p style='color:#1DB954;font-weight:700;font-size:1rem;margin-bottom:4px;'>"
        f"🎤 {len(artist_tracks)} tracks — {artist_name}</p>",
        unsafe_allow_html=True,
    )
    st.dataframe(artist_tracks.reset_index(drop=True), use_container_width=True, hide_index=True)

st.markdown("<hr style='border-color:#333;margin-top:8px;margin-bottom:8px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 3 — Collection by Decade
# ---------------------------------------------------------------------------
if "decade" in deduped.columns and deduped["decade"].notna().any():
    st.markdown("## Collection by Decade")
    st.markdown(
        "<p style='color:#B3B3B3;margin-top:-8px;'>Click a bar to see the tracks in that range.</p>",
        unsafe_allow_html=True,
    )

    decade_counts = (
        deduped["decade"].dropna().astype(int)
        .value_counts().sort_index().reset_index()
    )
    decade_counts.columns = ["decade", "count"]
    decade_counts["decade_label"] = decade_counts["decade"].astype(str) + "s"

    era_colors = {
        1950: "#0d3320", 1960: "#0f3d26", 1970: "#11472c",
        1980: "#145e2a", 1990: "#179141", 2000: "#1aaa4c",
        2010: "#1DB954", 2020: "#4dcb76",
    }
    decade_counts["color"] = decade_counts["decade"].map(lambda d: era_colors.get(d, "#1DB954"))

    fig_decade = go.Figure(go.Bar(
        x=decade_counts["decade_label"],
        y=decade_counts["count"],
        text=decade_counts["count"],
        textposition="outside",
        marker=dict(color=decade_counts["color"], line=dict(width=0)),
        hovertemplate="<b>%{x}</b><br>%{y} tracks<extra></extra>",
    ))
    fig_decade.update_layout(
        plot_bgcolor="#121212", paper_bgcolor="#121212", font_color="#B3B3B3",
        xaxis=dict(gridcolor="#282828", tickfont=dict(color="#FFFFFF", size=12)),
        yaxis=dict(gridcolor="#282828", title="Tracks"),
        margin=dict(t=20, b=20),
        height=360,
    )
    selected_decade = st.plotly_chart(fig_decade, use_container_width=True, on_select="rerun", key="decade_chart")

    if selected_decade and selected_decade.selection and selected_decade.selection.points:
        decade_label = selected_decade.selection.points[0]["x"]  # e.g. "1990s"
        decade_val   = int(decade_label.replace("s", ""))
        decade_tracks = (
            deduped[deduped["decade"].astype("Int64") == decade_val]
            [[c for c in ["track_name", "artist_display", "playlist_name", "popularity_raw", "release_year"] if c in deduped.columns]]
            .copy()
            .sort_values("popularity_raw", ascending=False)
        )
        if "release_year" in decade_tracks.columns:
            decade_tracks["release_year"] = decade_tracks["release_year"].fillna(0).astype(int)
        decade_tracks = decade_tracks.rename(columns={
            "track_name": "Track", "artist_display": "Artist",
            "playlist_name": "Playlist", "popularity_raw": "Popularity", "release_year": "Year",
        })
        st.markdown(
            f"<p style='color:#1DB954;font-weight:700;font-size:1rem;margin-bottom:4px;'>"
            f"📅 {len(decade_tracks)} tracks — {decade_label}</p>",
            unsafe_allow_html=True,
        )
        st.dataframe(decade_tracks.reset_index(drop=True), use_container_width=True, hide_index=True)

    st.markdown("<hr style='border-color:#333;margin-top:8px;margin-bottom:8px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 4 — Popularity Distribution (interactive click)
# ---------------------------------------------------------------------------
if "popularity_raw" in deduped.columns and deduped["popularity_raw"].notna().any():
    st.markdown("## Popularity Distribution")
    st.markdown(
        "<p style='color:#B3B3B3;margin-top:-8px;'>Click a bar to see the tracks in that range.</p>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='background:#1a1a1a;border:1px solid #2a2a2a;border-radius:10px;"
        "padding:12px 16px;margin-bottom:16px;font-size:0.82rem;color:#888;line-height:1.5;'>"
        "ℹ️ Popularity scores come from the Spotify API and are calculated by their algorithm — "
        "based mainly on total play count and how recent those plays are. "
        "Scores update continuously, so a legendary track you'd expect to score 90 might sit at 5 "
        "simply because no one streamed it this week. Don't read too much into low scores."
        "</div>",
        unsafe_allow_html=True,
    )

    fig_pop = go.Figure(go.Histogram(
        x=deduped["popularity_raw"],
        xbins=dict(start=0, end=100, size=BIN_SIZE),
        marker=dict(color="#1DB954", line=dict(width=0)),
        hovertemplate="Popularity %{x} · %{y} tracks<extra></extra>",
    ))
    fig_pop.update_layout(
        plot_bgcolor="#121212", paper_bgcolor="#121212", font_color="#B3B3B3",
        xaxis=dict(gridcolor="#282828", tickfont=dict(color="#FFFFFF"), title="Popularity Score"),
        yaxis=dict(title="Tracks", gridcolor="#282828"),
        bargap=0.05,
        margin=dict(t=20, b=20),
        height=340,
    )

    selected_pop = st.plotly_chart(fig_pop, use_container_width=True, on_select="rerun", key="pop_histogram")

    if selected_pop and selected_pop.selection and selected_pop.selection.points:
        points = selected_pop.selection.points
        x_vals = [p["x"] for p in points]

        # p["x"] is bin center — snap to left edge via floor division
        bin_min = (min(x_vals) // BIN_SIZE) * BIN_SIZE
        bin_max = bin_min + BIN_SIZE

        cols_show = [
            c for c in ["track_name", "artist_display", "playlist_name", "popularity_raw", "release_year"]
            if c in deduped.columns
        ]
        bin_tracks = (
            deduped[
                (deduped["popularity_raw"] >= bin_min) &
                (deduped["popularity_raw"] <  bin_max)
            ]
            [cols_show]
            .copy()
            .sort_values("popularity_raw", ascending=False)
        )

        if "release_year" in bin_tracks.columns:
            bin_tracks["release_year"] = bin_tracks["release_year"].fillna(0).astype(int)
        bin_tracks = bin_tracks.rename(columns={
            "track_name":     "Track",
            "artist_display": "Artist",
            "playlist_name":  "Playlist",
            "popularity_raw": "Popularity",
            "release_year":   "Year",
        })
        st.markdown(
            f"<p style='color:#1DB954;font-weight:700;font-size:1rem;margin-bottom:4px;'>"
            f"🎯 {len(bin_tracks)} tracks — popularity {int(bin_min)}–{int(bin_max - 1)}</p>",
            unsafe_allow_html=True,
        )
        st.dataframe(bin_tracks.reset_index(drop=True), use_container_width=True, hide_index=True)

    st.markdown("<hr style='border-color:#333;margin-top:8px;margin-bottom:8px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 4b — Most Popular Artists + Favourite Albums
# ---------------------------------------------------------------------------
col_pop_artists, col_albums = st.columns(2)

with col_pop_artists:
    st.markdown("## 🏆 Most Popular Artists")
    st.markdown(
        f"<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>"
        f"Avg popularity · min. {min_t} tracks · primary artists only</p>",
        unsafe_allow_html=True,
    )
    show_all_artists = st.session_state.get("show_all_artists", False)
    artists_to_show = top_popular_artists.head(20) if show_all_artists else top_popular_artists.head(5)

    if not top_popular_artists.empty:
        for rank, (_, row) in enumerate(artists_to_show.iterrows()):
            pop = round(row["avg_popularity"], 1)
            st.markdown(ranking_card(
                medal    = MEDALS[rank] if rank < 5 else f"{rank+1}.",
                title    = row["artist_name"],
                subtitle = "",
                value    = str(pop),
                bar_pct  = int(pop),
                footer   = f"{int(row['track_count'])} tracks",
            ), unsafe_allow_html=True)

        if len(top_popular_artists) > 5:
            if st.button("Show top 20" if not show_all_artists else "Show less", key="toggle_artists"):
                st.session_state["show_all_artists"] = not show_all_artists
                st.rerun()
    else:
        st.markdown("<p style='color:#B3B3B3;'>Not enough data.</p>", unsafe_allow_html=True)

with col_albums:
    st.markdown("## 💿 Favourite Albums")
    st.markdown(
        "<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>"
        "Ranked by tracks saved · avg popularity shown</p>",
        unsafe_allow_html=True,
    )
    show_all_albums = st.session_state.get("show_all_albums", False)
    albums_to_show = top_albums.head(20) if show_all_albums else top_albums.head(5)

    if not top_albums.empty:
        for rank, (_, row) in enumerate(albums_to_show.iterrows()):
            pop = round(row["avg_popularity"], 1)
            st.markdown(ranking_card(
                medal    = MEDALS[rank] if rank < 5 else f"{rank+1}.",
                title    = row["album_name"],
                subtitle = row["artist_name"],
                value    = str(pop),
                bar_pct  = int(pop),
                footer   = f"{int(row['track_count'])} tracks saved",
            ), unsafe_allow_html=True)

        if len(top_albums) > 5:
            if st.button("Show top 20" if not show_all_albums else "Show less", key="toggle_albums"):
                st.session_state["show_all_albums"] = not show_all_albums
                st.rerun()
    else:
        st.markdown("<p style='color:#B3B3B3;'>Not enough data.</p>", unsafe_allow_html=True)
# ---------------------------------------------------------------------------
# Section 5 — Top Genres treemap
# ---------------------------------------------------------------------------

if "artist_genres" in df.columns:
    st.markdown("## Top Genres")
    st.markdown(
        "<p style='color:#B3B3B3;margin-top:-8px;'>Sized by unique tracks per genre. The top 30 genres are in the treemap, but you can select any genre (including sub-genres) in the dropdown below to see all its tracks.</p>",
        unsafe_allow_html=True,
    )

    genres_exploded = (
        df[df["artist_genres"].notna() & (df["artist_genres"] != "")]
        .assign(genre=lambda x: x["artist_genres"].str.split(","))
        .explode("genre")
        .assign(genre=lambda x: x["genre"].str.strip())
        .query("genre != ''")
    )

    all_genres = genres_exploded["genre"].unique().tolist()
    genre_counts = []
    for g in all_genres:
        count = df[
            df["artist_genres"].notna() &
            df["artist_genres"].str.contains(g, case=False, regex=False)
        ]["track_id"].nunique()
        genre_counts.append({"genre": g, "track_count": count})

    top_genres = (
        pd.DataFrame(genre_counts)
        .sort_values("track_count", ascending=False)
        .head(30)
        .reset_index(drop=True)
    )

    fig_genres = go.Figure(go.Treemap(
        labels=top_genres["genre"],
        parents=[""] * len(top_genres),
        values=top_genres["track_count"],
        texttemplate="<b>%{label}</b><br>%{value}",
        hovertemplate="<b>%{label}</b><br>%{value} tracks<extra></extra>",
        marker=dict(
            colors=top_genres["track_count"],
            colorscale=[[0, "#0f3d26"], [0.4, "#145e2a"], [0.7, "#1DB954"], [1, "#4dcb76"]],
            showscale=False,
            line=dict(width=2, color="#121212"),
        ),
        textfont=dict(color="#FFFFFF", size=13),
        pathbar=dict(visible=False),
    ))
    fig_genres.update_layout(
        plot_bgcolor="#121212",
        paper_bgcolor="#121212",
        font_color="#B3B3B3",
        margin=dict(t=10, b=10, l=10, r=10),
        height=480,
    )

    st.plotly_chart(
        fig_genres,
        use_container_width=True,
        key="genre_chart",
        config={"staticPlot": True},
    )

    # Tracks without genre data
    no_genre = deduped[
        deduped["artist_genres"].isna() | (deduped["artist_genres"].str.strip() == "")
    ]
    no_genre_count = len(no_genre)
    if no_genre_count > 0:
        pct = round(no_genre_count / len(deduped) * 100, 1)
        st.markdown(
            f"<p style='color:#B3B3B3;font-size:0.78rem;margin-top:4px;'>"
            f"⚠️ {no_genre_count} tracks ({pct}%) have no genre data from Spotify — "
            f"they are excluded from this chart.</p>",
            unsafe_allow_html=True,
        )

    # --- Genre selector ---
    st.markdown(
        "<p style='color:#B3B3B3;font-size:0.85rem;margin-top:4px;margin-bottom:2px;'>"
        "Pick a genre to see all its tracks — sub-genres are included "
        "(e.g. <b>rock</b> includes <b>argentine rock</b>, <b>indie rock</b>, etc.)</p>",
        unsafe_allow_html=True,
    )

    genre_options = pd.DataFrame(genre_counts).sort_values("track_count", ascending=False)["genre"].tolist()
    chosen_genre = st.selectbox(
        "",
        genre_options,
        index=None,
        placeholder="Pick a genre...",
        label_visibility="collapsed",
        key="genre_selector",
    )

    if chosen_genre:
        # str.contains catches all sub-genres that include the chosen word
        genre_tracks = (
            deduped[
                deduped["artist_genres"].notna() &
                deduped["artist_genres"].str.contains(chosen_genre, case=False, regex=False)
            ]
            [[c for c in ["track_name", "artist_display", "playlist_name", "popularity_raw", "release_year"] if c in deduped.columns]]
            .copy()
            .sort_values("popularity_raw", ascending=False)
        )
        if "release_year" in genre_tracks.columns:
            genre_tracks["release_year"] = genre_tracks["release_year"].fillna(0).astype(int)
        genre_tracks = genre_tracks.rename(columns={
            "track_name": "Track", "artist_display": "Artist",
            "playlist_name": "Playlist", "popularity_raw": "Popularity", "release_year": "Year",
        })

        # Count exact vs sub-genre matches for the overlap note
        exact_count = top_genres.loc[top_genres["genre"] == chosen_genre, "track_count"]
        exact_count = int(exact_count.values[0]) if not exact_count.empty else len(genre_tracks)
        total_count = len(genre_tracks)
        overlap_note = ""
        if total_count > exact_count:
            overlap_note = f" · <span style='color:#B3B3B3;font-weight:400;font-size:0.85rem;'>{exact_count} tagged exactly, {total_count - exact_count} from sub-genres</span>"

        st.markdown(
            f"<p style='color:#1DB954;font-weight:700;font-size:1rem;margin-bottom:4px;'>"
            f"🎸 {total_count} tracks — {chosen_genre}{overlap_note}</p>",
            unsafe_allow_html=True,
        )
        st.dataframe(genre_tracks.reset_index(drop=True), use_container_width=True, hide_index=True)

    st.markdown("<hr style='border-color:#333;margin-top:8px;margin-bottom:8px;'>", unsafe_allow_html=True)
# ---------------------------------------------------------------------------
# Section 6 — Tracks Added Over Time
# ---------------------------------------------------------------------------
st.markdown("## Tracks Added Over Time")
st.markdown(
    "<p style='color:#B3B3B3;margin-top:-8px;'>Click any point on the chart to see which tracks were added that month.</p>",
    unsafe_allow_html=True,
)

if not timeline.empty:
    timeline["year_month_dt"] = pd.to_datetime(timeline["year_month"], format="%Y-%m", errors="coerce")
    timeline_clean = timeline.dropna(subset=["year_month_dt"]).sort_values("year_month_dt")

    if len(timeline_clean) < 2:
        row = timeline_clean.iloc[0]
        st.markdown(
            f"<div style='background:#282828;border-radius:12px;padding:20px 24px;border:1px solid #333;'>"
            f"<span style='color:#B3B3B3;font-size:0.85rem;text-transform:uppercase;letter-spacing:.06em;'>All tracks added in</span><br>"
            f"<span style='color:#FFFFFF;font-size:1.8rem;font-weight:800;'>{row['year_month']}</span>"
            f"<span style='color:#1DB954;font-size:1rem;font-weight:700;margin-left:12px;'>{int(row['tracks_added'])} tracks</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        fig_timeline = go.Figure(go.Scatter(
            x=timeline_clean["year_month_dt"],
            y=timeline_clean["tracks_added"],
            fill="tozeroy",
            fillcolor="rgba(29,185,84,0.15)",
            line=dict(color="#1DB954", width=2),
            mode="lines+markers",
            marker=dict(color="#1DB954", size=5, opacity=0.7),
            hovertemplate="%{x|%b %Y}<br><b>%{y} tracks added</b><extra></extra>",
        ))
        fig_timeline.update_layout(
            plot_bgcolor="#121212", paper_bgcolor="#121212", font_color="#B3B3B3",
            xaxis=dict(gridcolor="#282828", tickfont=dict(color="#FFFFFF", size=10), tickangle=-45, title=""),
            yaxis=dict(gridcolor="#282828", title="Tracks Added"),
            margin=dict(t=20, b=60),
            height=340,
            showlegend=False,
        )
        selected_month = st.plotly_chart(fig_timeline, use_container_width=True, on_select="rerun", key="timeline_chart")

        if selected_month and selected_month.selection and selected_month.selection.points:
            clicked_x = selected_month.selection.points[0]["x"]
            clicked_ym = pd.to_datetime(clicked_x).strftime("%Y-%m")

            _df_at = df.copy()
            _df_at["added_at"] = pd.to_datetime(_df_at["added_at"], errors="coerce")
            _df_at["_ym"] = _df_at["added_at"].dt.strftime("%Y-%m")
            month_tracks = (
                _df_at[_df_at["_ym"] == clicked_ym]
                .drop_duplicates(subset="track_id")
                [[c for c in ["track_name", "artist_display", "playlist_name", "popularity_raw", "release_year"] if c in _df_at.columns]]
                .copy()
                .sort_values("popularity_raw", ascending=False) if "popularity_raw" in _df_at.columns
                else _df_at[_df_at["_ym"] == clicked_ym]
                .drop_duplicates(subset="track_id")
                [[c for c in ["track_name", "artist_display", "playlist_name", "release_year"] if c in _df_at.columns]]
                .copy()
            )
            if "release_year" in month_tracks.columns:
                month_tracks["release_year"] = month_tracks["release_year"].fillna(0).astype(int)
            month_tracks = month_tracks.rename(columns={
                "track_name": "Track", "artist_display": "Artist",
                "playlist_name": "Playlist", "popularity_raw": "Popularity", "release_year": "Year",
            })
            label = pd.to_datetime(clicked_ym).strftime("%B %Y")
            st.markdown(
                f"<p style='color:#1DB954;font-weight:700;font-size:1rem;margin-bottom:4px;'>"
                f"📅 {len(month_tracks)} tracks added in {label}</p>",
                unsafe_allow_html=True,
            )
            st.dataframe(month_tracks.reset_index(drop=True), use_container_width=True, hide_index=True)
else:
    st.markdown(
        "<p style='color:#B3B3B3;'>No timeline data available for this collection.</p>",
        unsafe_allow_html=True,
    )

