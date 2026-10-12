import html
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from app_state.collection import get_all_tracks
from config import CLUSTER_FEATURES
from core import duplicates as dup
from core import playlist_detail as pd_core
from core.formatting import fmt_duration

from ui.theme import inject_global_css

inject_global_css()
from ui.theme import spotify_icon_html, page_brand_html
from ui.nav import inject_sidebar_nav
inject_sidebar_nav("Playlist Detail")
from ui.nav import check_collection_mode
if not check_collection_mode():
    st.stop()

# ---------------------------------------------------------------------------
# Config & helpers
# ---------------------------------------------------------------------------
from ui.charts import BASE_LAYOUT as _BASE_LAYOUT

SPOTIFY_LOGO = spotify_icon_html(36)

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

# Derive af_avg from df (audio features come from Spotify enrichment)
af_avg = pd_core.playlist_audio_averages(df)
meta = pd_core.playlist_meta(df, st.session_state.get("uc_playlists", []))

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
if st.session_state.get("uc_active"):
    n_unique = df["track_id"].nunique()
    n_pl     = df["playlist_name"].nunique()
    st.info(f"🎵 Viewing: Your Collection — {n_unique:,} unique tracks across {n_pl} playlists (duplicates across playlists not counted)")

# ---------------------------------------------------------------------------
# Playlist selector
# ---------------------------------------------------------------------------
playlists = sorted(df["playlist_name"].unique().tolist())
selected  = st.selectbox("Choose a playlist", playlists, label_visibility="collapsed")

# Playlist rows, duration normalized to minutes (YC delivers milliseconds)
pl_df   = pd_core.playlist_tracks(df, selected)
pl_meta = meta[meta["playlist_name"] == selected].iloc[0]

# Ensure speechiness_log is present for the radar chart (log1p transform used by CLUSTER_FEATURES)
af_avg = pd_core.add_speechiness_log(af_avg)

# Per-playlist and global audio feature rows
audio = pd_core.compare_audio(af_avg, selected)

st.markdown("<hr style='border-color:#333;margin-top:16px;margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 1 — Header metrics
# ---------------------------------------------------------------------------
kpis = pd_core.header_kpis(pl_df, int(pl_meta["followers"]))
total_tracks   = kpis.total_tracks
unique_artists = kpis.unique_artists
followers      = kpis.followers
first_added    = kpis.first_added
last_added     = kpis.last_added

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

hl = pd_core.track_highlights(pl_df)

with col1:
    if hl.longest is not None:
        longest_row, shortest_row = hl.longest, hl.shortest
        st.markdown(
            highlight_card("⏱️", "Longest Track", longest_row["track_name"], longest_row["artist_display"], fmt_duration(longest_row["duration_raw"])) +
            highlight_card("⚡", "Shortest Track", shortest_row["track_name"], shortest_row["artist_display"], fmt_duration(shortest_row["duration_raw"])),
            unsafe_allow_html=True,
        )

with col2:
    if hl.most_popular is not None:
        most_pop_row, least_pop_row = hl.most_popular, hl.least_popular
        st.markdown(
            highlight_card("⭐", "Most Popular", most_pop_row["track_name"], most_pop_row["artist_display"], f"{int(most_pop_row['popularity_raw'])} pts") +
            highlight_card("💀", "Least Popular", least_pop_row["track_name"], least_pop_row["artist_display"], f"{int(least_pop_row['popularity_raw'])} pts"),
            unsafe_allow_html=True,
        )

with col3:
    if hl.oldest is not None:
        oldest_row, newest_row = hl.oldest, hl.newest
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

avgs = pd_core.playlist_averages(pl_df)
avg_dur, avg_pop, avg_year = avgs.avg_duration, avgs.avg_popularity, avgs.avg_release_year
top_artist, top_artist_count = avgs.top_artist, avgs.top_artist_count

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

_top = pd_core.top_artists(pl_df, 5)
top_artists = _top.table
top_artists_pct = _top.covered_pct
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
if st.session_state.get("uc_active"):
    pl_raw_df = dup.raw_records_frame(
        st.session_state.get("uc_enriched", [])
        + st.session_state.get("uc_skipped", [])
        + st.session_state.get("uc_failed", []),
        selected,
    )
    _pl_artist_col = "artist_name"
else:
    pl_raw_df      = pl_df.copy()
    _pl_artist_col = "artist_display" if "artist_display" in pl_raw_df.columns else "artist_name"

pl_raw_df = dup.drop_missing_ids(pl_raw_df)

st.markdown("## Exact Duplicates")
st.markdown(
    "<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>"
    "Same Spotify ID saved more than once in this playlist.</p>",
    unsafe_allow_html=True,
)

_pl_id_dupes = dup.exact_duplicates(pl_raw_df, _pl_artist_col)

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

_pl_versions = dup.different_versions(pl_raw_df)

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

radar = pd_core.radar_profile(af_avg, audio, CLUSTER_FEATURES)

if radar is not None:
    _radar_feats = radar.features
    pl_vals      = radar.playlist_values
    global_vals  = radar.global_values

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
    st.info(
        "Audio features aren't available for this playlist — "
        "these tracks weren't found in the audio database during enrichment."
    )

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
        decade_counts = pd_core.decade_counts(pl_df)
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
            dec_tracks   = pd_core.decade_track_listing(pl_df, decade_val)
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
        year_counts = pd_core.year_counts(pl_df)

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
    top_genres = pd_core.top_genres(pl_df, 15)

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

scatter_df = pd_core.mood_map_points(pl_df)

if pd_core.mood_map_available(pl_df):
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

monthly_raw = pd_core.monthly_additions(pl_df)

if monthly_raw.empty or len(monthly_raw) <= 1:
    # Check if it's the "added all at once" scenario vs genuinely missing data
    single_date = pd_core.single_session_date(pl_df)
    if single_date is not None:
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
    monthly = pd_core.growth_timeline(monthly_raw)

    # Annotation: peak month
    _peak      = pd_core.peak_month(monthly)
    peak_month = _peak.label
    peak_count = _peak.count

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
        x=_peak.month,
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

    if not af_avg.empty and audio.playlist is not None:
        if pd_core.similarity_features(af_avg):
            # Distance on normalised features (tempo scaled to 0-1)
            similar = pd_core.with_similarity_pct(pd_core.similar_playlists(af_avg, selected, 5))

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

table = pd_core.track_table(pl_df)

st.dataframe(
    table.reset_index(drop=True),
    use_container_width=True,
    hide_index=True,
)
