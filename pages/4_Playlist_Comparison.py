import html
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from app_state.collection import get_all_tracks
from config import AUDIO_FEATURES, NORMALIZED_FEATURES
from core import comparison
from core.formatting import fmt_duration
from core.playlist_detail import playlist_audio_averages

from ui.theme import inject_global_css
inject_global_css()
from ui.theme import spotify_icon_html, page_brand_html
from ui.nav import inject_sidebar_nav
inject_sidebar_nav("Playlist Comparison")
from ui.nav import check_collection_mode
if not check_collection_mode():
    st.stop()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(page_brand_html(), unsafe_allow_html=True)
st.markdown(
    f"<div style='display:flex;align-items:center;gap:14px;margin-bottom:4px;'>"
    f"{spotify_icon_html(36)}"
    f"<div>"
    f"<h1 style='margin:0;font-size:2rem;font-weight:800;color:#FFFFFF;'>Playlist Comparison</h1>"
    f"</div>"
    f"</div>"
    f"<hr style='border-color:#333;margin-top:12px;margin-bottom:24px;'>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
df    = get_all_tracks()
_n_pl = df["playlist_name"].nunique()

if _n_pl == 1:
    st.info("ℹ️ Only one playlist loaded — add more playlists to compare.")
    st.stop()

st.markdown(
    f"<p style='color:#B3B3B3; margin-top:-16px; margin-bottom:8px; font-size:0.95rem;'>"
    f"How do the {_n_pl} playlists stack up against each other?</p>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Active collection banner
# ---------------------------------------------------------------------------
if st.session_state.get("uc_active"):
    n_unique = df["track_id"].nunique()
    n_pl     = df["playlist_name"].nunique()
    st.info(f"🎵 Viewing: Your Collection — {n_unique:,} unique tracks across {n_pl} playlists (duplicates across playlists not counted)")
# ---------------------------------------------------------------------------

meta   = comparison.playlist_meta(st.session_state.get("uc_playlists", []))
af_avg = playlist_audio_averages(df)
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def kpi_card(icon: str, label: str, value: str, sub: str = ""):
    sub_html = f"<div style='color:#B3B3B3; font-size:0.78rem; margin-top:6px;'>{html.escape(sub)}</div>" if sub else ""
    return f"""
    <div style="background:#282828; border-radius:14px; padding:22px 24px; border:1px solid #333; height:100%;">
        <div style="font-size:1.6rem;">{html.escape(icon)}</div>
        <div style="color:#B3B3B3; font-size:0.78rem; font-weight:600; letter-spacing:0.06em; text-transform:uppercase; margin-top:8px;">{html.escape(label)}</div>
        <div style="color:#FFFFFF; font-size:1.5rem; font-weight:800; margin-top:4px;">{html.escape(str(value))}</div>
        {sub_html}
    </div>"""

def ranking_card(rank: int, name: str, value: str, pct: float, sub: str = ""):
    medal   = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")
    pct_str = f"{pct * 100:.1f}"
    lines   = [
        f'<div style="background:#282828;border-radius:12px;padding:14px 18px;border:1px solid #333;margin-bottom:8px;">',
        f'<div style="display:flex;justify-content:space-between;align-items:center;">',
        f'<div style="display:flex;align-items:center;gap:10px;">',
        f'<span style="font-size:1.1rem;">{medal}</span>',
        f'<span style="color:#FFFFFF;font-weight:700;font-size:0.95rem;">{html.escape(str(name))}</span>',
        f'</div>',
        f'<span style="color:#1DB954;font-weight:800;font-size:1rem;">{html.escape(str(value))}</span>',
        f'</div>',
    ]
    if sub:
        lines.append(f'<div style="color:#B3B3B3;font-size:0.75rem;margin-top:4px;">{sub}</div>')
    lines.append(f'<div style="height:4px;background:#333;border-radius:4px;margin-top:8px;">')
    lines.append(f'<div style="width:{pct_str}%;height:4px;background:#1DB954;border-radius:4px;"></div>')
    lines.append('</div></div>')
    return "".join(lines)

_BASE_LAYOUT = dict(
    plot_bgcolor="#121212", paper_bgcolor="#121212", font_color="#B3B3B3",
    margin=dict(t=20, b=20, l=10, r=10),
)

# ---------------------------------------------------------------------------
# Section 1 — Size
# ---------------------------------------------------------------------------
st.markdown("## Size")
st.markdown("<p style='color:#B3B3B3; margin-top:-8px; font-size:0.85rem;'>Spotify's track count per playlist. The same track saved in multiple playlists is counted once in Overview's Unique Tracks — that's why the sum here may be higher.</p>", unsafe_allow_html=True)

size       = comparison.size_ranking(meta)
max_tracks = int(size["total_tracks"].max())

cards_left, cards_right = [], []
for i, row in size.iterrows():
    pct  = int(row["total_tracks"]) / max_tracks
    card = ranking_card(i + 1, row["playlist_name"], f"{int(row['total_tracks'])} tracks", pct)
    (cards_left if i % 2 == 0 else cards_right).append(card)

col1, col2 = st.columns(2)
with col1:
    st.markdown("".join(cards_left), unsafe_allow_html=True)
with col2:
    st.markdown("".join(cards_right), unsafe_allow_html=True)

st.markdown("<hr style='border-color:#333; margin-top:24px; margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 1b — Followers
# ---------------------------------------------------------------------------
st.markdown("## Followers")
st.markdown("<p style='color:#B3B3B3; margin-top:-8px; font-size:0.85rem;'>Most followed playlists in your collection.</p>", unsafe_allow_html=True)

followers     = comparison.follower_ranking(meta)
max_followers = int(followers["followers"].max())

if max_followers == 0:
    st.markdown("<p style='color:#B3B3B3; font-size:0.85rem;'>No follower data available.</p>", unsafe_allow_html=True)
else:
    cards = []
    for i, row in followers.head(3).iterrows():
        pct = int(row["followers"]) / max_followers
        cards.append(ranking_card(i + 1, row["playlist_name"], f"{int(row['followers']):,} followers", pct))
    col1, col2, col3 = st.columns(3)
    for col, card in zip([col1, col2, col3], cards):
        with col:
            st.markdown(card, unsafe_allow_html=True)

st.markdown("<hr style='border-color:#333; margin-top:24px; margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 1c — Duplicated tracks across playlists
# ---------------------------------------------------------------------------
# Raw per-occurrence records (real Spotify IDs, skipped/failed tracks included) feed both duplicate sections.
_raw_records = (
    st.session_state.get("uc_enriched", [])
    + st.session_state.get("uc_skipped", [])
    + st.session_state.get("uc_failed", [])
)

# ---------------------------------------------------------------------------
# Section 1c-A — Exact duplicates (same Spotify ID)
# ---------------------------------------------------------------------------
st.markdown("## Exact Duplicates")
st.markdown(
    "<p style='color:#B3B3B3; margin-top:-8px; font-size:0.85rem;'>"
    "Tracks saved more than once with the exact same Spotify ID — across or within playlists.</p>",
    unsafe_allow_html=True,
)

_dupes = comparison.exact_duplicates_across_playlists(_raw_records)
n_dupes = len(_dupes)

if n_dupes == 0:
    st.markdown(
        "<div style='background:#1a1a1a;border:1px solid #333;border-radius:10px;"
        "padding:16px 20px;color:#B3B3B3;font-size:0.9rem;'>"
        "No exact duplicates found — every Spotify ID appears only once.</div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f"<div style='background:#282828;border-radius:14px;padding:16px 22px;"
        f"border:1px solid #333;display:inline-block;margin-bottom:16px;'>"
        f"<span style='color:#B3B3B3;font-size:0.78rem;font-weight:600;"
        f"text-transform:uppercase;letter-spacing:.06em;'>Exact Duplicates</span><br>"
        f"<span style='color:#1DB954;font-size:2rem;font-weight:800;'>{n_dupes}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.dataframe(
        _dupes[["track_name", "artist_display", "playlists"]]
        .rename(columns={"track_name": "Track", "artist_display": "Artist", "playlists": "Playlists"}),
        use_container_width=True,
        hide_index=True,
    )

# ---------------------------------------------------------------------------
# Section 1c-B — Different versions (same name + artist, different Spotify IDs)
# ---------------------------------------------------------------------------
st.markdown("## Different Versions")
st.markdown(
    "<p style='color:#B3B3B3; margin-top:-8px; font-size:0.85rem;'>"
    "Same song name and artist saved multiple times with different Spotify IDs — "
    "separate recordings, album releases, or live versions.</p>",
    unsafe_allow_html=True,
)

_versions = comparison.different_versions_across_playlists(_raw_records)
n_versions = len(_versions)

if n_versions == 0:
    st.markdown(
        "<div style='background:#1a1a1a;border:1px solid #333;border-radius:10px;"
        "padding:16px 20px;color:#B3B3B3;font-size:0.9rem;'>"
        "No different versions found.</div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f"<div style='background:#282828;border-radius:14px;padding:16px 22px;"
        f"border:1px solid #333;display:inline-block;margin-bottom:16px;'>"
        f"<span style='color:#B3B3B3;font-size:0.78rem;font-weight:600;"
        f"text-transform:uppercase;letter-spacing:.06em;'>Different Versions</span><br>"
        f"<span style='color:#1DB954;font-size:2rem;font-weight:800;'>{n_versions}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.dataframe(
        _versions[["track_name", "artist_name", "n_unique_ids", "playlists"]]
        .rename(columns={"track_name": "Track", "artist_name": "Artist", "n_unique_ids": "Versions", "playlists": "Playlists"}),
        use_container_width=True,
        hide_index=True,
    )

st.markdown("<hr style='border-color:#333; margin-top:24px; margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 2 — Duration
# ---------------------------------------------------------------------------
st.markdown("## Duration")
st.markdown("<p style='color:#B3B3B3; margin-top:-8px; font-size:0.85rem;'>The most extreme tracks.</p>", unsafe_allow_html=True)

extremes = comparison.duration_extremes(df)
if extremes is not None:
    longest_row, shortest_row = extremes.longest, extremes.shortest

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        <div style="background:#282828; border-radius:14px; padding:22px 24px; border:1px solid #333;">
            <div style="font-size:1.6rem;">⏱️</div>
            <div style="color:#B3B3B3; font-size:0.78rem; font-weight:600; letter-spacing:0.06em; text-transform:uppercase; margin-top:8px;">Longest Track</div>
            <div style="color:#FFFFFF; font-size:1.1rem; font-weight:800; margin-top:6px;">{longest_row.track_name}</div>
            <div style="color:#1DB954; font-size:0.85rem; margin-top:4px;">{longest_row.artist_display} · {longest_row.playlist_name} · {fmt_duration(longest_row.minutes)}</div>
        </div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div style="background:#282828; border-radius:14px; padding:22px 24px; border:1px solid #333;">
            <div style="font-size:1.6rem;">⚡</div>
            <div style="color:#B3B3B3; font-size:0.78rem; font-weight:600; letter-spacing:0.06em; text-transform:uppercase; margin-top:8px;">Shortest Track</div>
            <div style="color:#FFFFFF; font-size:1.1rem; font-weight:800; margin-top:6px;">{shortest_row.track_name}</div>
            <div style="color:#1DB954; font-size:0.85rem; margin-top:4px;">{shortest_row.artist_display} · {shortest_row.playlist_name} · {fmt_duration(shortest_row.minutes)}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

st.markdown("<hr style='border-color:#333; margin-top:24px; margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 3 — Popularity  →  vertical bar zoomed in + KPI cards
# ---------------------------------------------------------------------------
st.markdown("## Popularity")
st.markdown("<p style='color:#B3B3B3; margin-top:-8px; font-size:0.85rem;'>Average Spotify popularity score (0–100) per playlist.</p>", unsafe_allow_html=True)

pop = comparison.popularity_by_playlist(df)
if pop is not None:

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(kpi_card("⭐", "Most Popular Playlist",
            pop.iloc[0]["playlist_name"], f"{pop.iloc[0]['avg_popularity']:.1f} avg score"), unsafe_allow_html=True)
    with col2:
        st.markdown(kpi_card("💀", "Least Popular Playlist",
            pop.iloc[-1]["playlist_name"], f"{pop.iloc[-1]['avg_popularity']:.1f} avg score"), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    y_min, y_max = comparison.popularity_axis_range(pop)

    fig_pop = go.Figure(go.Bar(
        x=pop["playlist_name"],
        y=pop["avg_popularity"],
        text=pop["avg_popularity"].round(1),
        textposition="outside",
        marker=dict(
            color=pop["avg_popularity"],
            colorscale=[[0, "#145e2a"], [1, "#1DB954"]],
            cmin=y_min, cmax=y_max,
            line=dict(width=0),
        ),
        hovertemplate="<b>%{x}</b><br>Avg popularity: %{y:.1f}<extra></extra>",
    ))
    fig_pop.update_layout(
        **_BASE_LAYOUT,
        xaxis=dict(gridcolor="#282828", tickfont=dict(color="#FFFFFF")),
        yaxis=dict(
            gridcolor="#282828",
            range=[y_min, y_max],
            title="Avg Popularity",
        ),
        height=max(300, 380),
    )
    st.plotly_chart(fig_pop, use_container_width=True)

st.markdown("<hr style='border-color:#333; margin-top:24px; margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 4 — Audio Feature Leaders
# ---------------------------------------------------------------------------
st.markdown("## Audio Feature Leaders")
st.markdown("<p style='color:#B3B3B3; margin-top:-8px; font-size:0.85rem;'>Which playlist tops each audio dimension?</p>", unsafe_allow_html=True)

if not af_avg.empty:
    FEATURE_LABELS = {
        "energy":           ("⚡", "Most Energetic"),
        "acousticness":     ("🎸", "Most Acoustic"),
        "valence":          ("😄", "Happiest"),
        "danceability":     ("🕺", "Most Danceable"),
        "speechiness":      ("🎤", "Most Speechy"),
        "instrumentalness": ("🎹", "Most Instrumental"),
        "liveness":         ("🎪", "Most Live"),
    }

    available_items = comparison.feature_leaders(af_avg)
    for row_items in [available_items[:4], available_items[4:]]:
        if not row_items:
            continue
        cols = st.columns(len(row_items))
        for col, leader in zip(cols, row_items):
            icon, label = FEATURE_LABELS[leader.feature]
            with col:
                st.markdown(kpi_card(icon, label, leader.playlist_name, f"{leader.value:.3f}"), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

    heatmap_df = comparison.heatmap_matrix(af_avg, NORMALIZED_FEATURES)
    if heatmap_df is not None:
        _heatmap_feats = heatmap_df.columns.tolist()
        fig_heat   = go.Figure(data=go.Heatmap(
            z=heatmap_df.values,
            x=_heatmap_feats,
            y=heatmap_df.index.tolist(),
            colorscale=[[0, "#121212"], [0.5, "#1a5c32"], [1, "#1DB954"]],
            text=heatmap_df.values.round(2),
            texttemplate="%{text}",
            showscale=True,
            hovertemplate="<b>%{y}</b><br>%{x}: %{z:.3f}<extra></extra>",
        ))
        fig_heat.update_layout(
            **_BASE_LAYOUT,
            xaxis=dict(tickfont=dict(color="#FFFFFF")),
            yaxis=dict(tickfont=dict(color="#FFFFFF")),
            height=max(300, len(af_avg) * 50),
        )
        st.plotly_chart(fig_heat, use_container_width=True)

st.markdown("<hr style='border-color:#333; margin-top:24px; margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 5 — Genre Diversity
# ---------------------------------------------------------------------------
diversity = comparison.genre_diversity(df)
if diversity is not None:
    st.markdown("## Genre Diversity")
    st.markdown("<p style='color:#B3B3B3; margin-top:-8px; font-size:0.85rem;'>Number of unique genres across all artists per playlist.</p>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(kpi_card("🌍", "Most Diverse",
            diversity.iloc[-1]["playlist_name"],
            f"{int(diversity.iloc[-1]['unique_genres'])} unique genres"), unsafe_allow_html=True)
    with col2:
        st.markdown(kpi_card("🎯", "Most Focused",
            diversity.iloc[0]["playlist_name"],
            f"{int(diversity.iloc[0]['unique_genres'])} unique genres"), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    fig_lollipop = go.Figure()
    for _, row in diversity.iterrows():
        fig_lollipop.add_trace(go.Scatter(
            x=[0, row["unique_genres"]],
            y=[row["playlist_name"], row["playlist_name"]],
            mode="lines",
            line=dict(color="#333333", width=2),
            showlegend=False,
            hoverinfo="skip",
        ))
    fig_lollipop.add_trace(go.Scatter(
        x=diversity["unique_genres"],
        y=diversity["playlist_name"],
        mode="markers+text",
        marker=dict(color="#1DB954", size=12, line=dict(color="#121212", width=2)),
        text=diversity["unique_genres"],
        textposition="middle right",
        textfont=dict(color="#FFFFFF", size=11),
        hovertemplate="<b>%{y}</b><br>%{x} unique genres<extra></extra>",
        showlegend=False,
    ))
    fig_lollipop.update_layout(
        **{**_BASE_LAYOUT, "margin": dict(t=20, b=20, l=10, r=60)},
        xaxis=dict(gridcolor="#282828", tickfont=dict(color="#FFFFFF"), title="Unique Genres"),
        yaxis=dict(tickfont=dict(color="#FFFFFF")),
        height=max(200, len(diversity) * 50),
    )
    st.plotly_chart(fig_lollipop, use_container_width=True)

    st.markdown("<hr style='border-color:#333; margin-top:24px; margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 6 — Release Era
# ---------------------------------------------------------------------------
st.markdown("## Release Era")
st.markdown("<p style='color:#B3B3B3; margin-top:-8px; font-size:0.85rem;'>Oldest to newest track range per playlist, with avg year as diamond.</p>", unsafe_allow_html=True)

release = comparison.release_era(df)
if release is not None:

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(kpi_card("🕰️", "Most Nostalgic",
            release.iloc[0]["playlist_name"],
            f"avg {release.iloc[0]['avg_release_year']:.0f}"), unsafe_allow_html=True)
    with col2:
        st.markdown(kpi_card("🆕", "Most Contemporary",
            release.iloc[-1]["playlist_name"],
            f"avg {release.iloc[-1]['avg_release_year']:.0f}"), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    fig_era = go.Figure()
    for _, row in release.iterrows():
        fig_era.add_trace(go.Scatter(
            x=[row["min_year"], row["max_year"]],
            y=[row["playlist_name"], row["playlist_name"]],
            mode="lines",
            line=dict(color="#333333", width=3),
            showlegend=False,
            hoverinfo="skip",
        ))
    fig_era.add_trace(go.Scatter(
        x=release["min_year"], y=release["playlist_name"],
        mode="markers",
        marker=dict(color="#145e2a", size=7, line=dict(color="#121212", width=1)),
        hovertemplate="<b>%{y}</b><br>Oldest: %{x:.0f}<extra></extra>",
        name="Oldest track",
    ))
    fig_era.add_trace(go.Scatter(
        x=release["max_year"], y=release["playlist_name"],
        mode="markers",
        marker=dict(color="#1DB954", size=7, line=dict(color="#121212", width=1)),
        hovertemplate="<b>%{y}</b><br>Newest: %{x:.0f}<extra></extra>",
        name="Newest track",
    ))
    fig_era.add_trace(go.Scatter(
        x=release["avg_release_year"], y=release["playlist_name"],
        mode="markers+text",
        marker=dict(color="#1DB954", size=14, symbol="diamond", line=dict(color="#121212", width=2)),
        text=release["avg_release_year"].apply(lambda x: f"{x:.0f}"),
        textposition="middle right",
        textfont=dict(color="#FFFFFF", size=10),
        hovertemplate="<b>%{y}</b><br>Avg: %{x:.0f}<extra></extra>",
        name="Avg year",
    ))
    fig_era.update_layout(
        **{**_BASE_LAYOUT, "margin": dict(t=40, b=20, l=10, r=80)},
        xaxis=dict(gridcolor="#282828", tickfont=dict(color="#FFFFFF"), tickformat="d", title="Release Year"),
        yaxis=dict(tickfont=dict(color="#FFFFFF")),
        legend=dict(bgcolor="#181818", font=dict(color="#B3B3B3"),
                    orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=max(200, len(release) * 80),
    )
    st.plotly_chart(fig_era, use_container_width=True)

st.markdown("<hr style='border-color:#333; margin-top:24px; margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 7 — Decade Distribution  →  stacked bar + click to see tracks
# ---------------------------------------------------------------------------

st.markdown("## Decade Distribution")
st.markdown("<p style='color:#B3B3B3; margin-top:-8px; font-size:0.85rem;'>Era composition of each playlist. Click a segment to see the tracks.</p>", unsafe_allow_html=True)

decade_dist = comparison.decade_mix(df)
if decade_dist is not None:

    decade_order   = sorted(decade_dist["decade_label"].unique().tolist())
    playlist_order = sorted(df["playlist_name"].unique().tolist())
    colors         = px.colors.sequential.Greens_r[:len(decade_order)]

    fig_decade = go.Figure()
    for i, decade_label in enumerate(decade_order):
        d = decade_dist[decade_dist["decade_label"] == decade_label]
        d = d.set_index("playlist_name").reindex(playlist_order).fillna(0).reset_index()
        fig_decade.add_trace(go.Bar(
            y=d["playlist_name"],
            x=d["count"],
            name=decade_label,
            orientation="h",
            marker_color=colors[i % len(colors)],
            # encode decade_label in customdata for reliable retrieval on click
            customdata=[[decade_label]] * len(d),
            hovertemplate=f"<b>%{{y}}</b><br>{decade_label}: %{{x:.0f}} tracks<extra></extra>",
        ))

    fig_decade.update_layout(
        barmode="stack",
        **_BASE_LAYOUT,
        xaxis=dict(gridcolor="#282828", tickfont=dict(color="#FFFFFF")),
        yaxis=dict(tickfont=dict(color="#FFFFFF"), categoryorder="category ascending"),
        legend=dict(bgcolor="#181818", font=dict(color="#B3B3B3"), title="Decade"),
        height=max(200, len(playlist_order) * 80),
    )

    selected_decade = st.plotly_chart(fig_decade, use_container_width=True, on_select="rerun", key="decade_dist")

    if selected_decade and selected_decade.selection and selected_decade.selection.points:
        pt                    = selected_decade.selection.points[0]
        selected_playlist     = pt.get("y")
        selected_decade_label = pt.get("customdata", [None])[0]

        decade_int = int(selected_decade_label.replace("s", "")) if selected_decade_label and selected_decade_label.endswith("s") else None

        if decade_int and selected_playlist:
            dec_tracks = comparison.decade_tracks(df, selected_playlist, decade_int)
            st.markdown(
                f"<p style='color:#1DB954;font-weight:700;font-size:1rem;margin-bottom:4px;'>"
                f"🎯 {len(dec_tracks)} tracks — {selected_playlist} · {selected_decade_label}</p>",
                unsafe_allow_html=True,
            )
            st.dataframe(dec_tracks, use_container_width=True, hide_index=True)

st.markdown("<hr style='border-color:#333; margin-top:24px; margin-bottom:24px;'>", unsafe_allow_html=True)
# ---------------------------------------------------------------------------
# Section 8 — Playlist Age  →  dot plot / timeline
# ---------------------------------------------------------------------------
st.markdown("## Playlist Age")
st.markdown("<p style='color:#B3B3B3; margin-top:-8px; font-size:0.85rem;'>When each playlist was first active — position on timeline = date.</p>", unsafe_allow_html=True)

age = comparison.playlist_age(df)
if age is not None:
    missing = comparison.playlists_without_dates(df, age)
    if missing:
        st.markdown(f"<p style='color:#B3B3B3; font-size:0.8rem;'>⚠️ No date data for: {', '.join(missing)}</p>", unsafe_allow_html=True)

    fig_age   = go.Figure()
    x_anchor  = age["first_added"].min()

    for _, row in age.iterrows():
        fig_age.add_trace(go.Scatter(
            x=[x_anchor, row["first_added"]],
            y=[row["playlist_name"], row["playlist_name"]],
            mode="lines",
            line=dict(color="#333333", width=1),
            showlegend=False,
            hoverinfo="skip",
        ))

    fig_age.add_trace(go.Scatter(
        x=age["first_added"],
        y=age["playlist_name"],
        mode="markers",
        marker=dict(color="#1DB954", size=12, line=dict(color="#121212", width=2)),
        customdata=age[["playlist_name", "first_added_str"]].values,
        hovertemplate="<b>%{customdata[0]}</b><br>First track added: %{customdata[1]}<extra></extra>",
        showlegend=False,
    ))

    fig_age.add_trace(go.Scatter(
        x=age["first_added"] + pd.Timedelta(days=60),
        y=age["playlist_name"],
        mode="text",
        text=age["first_added_str"],
        textposition="middle right",
        textfont=dict(color="#B3B3B3", size=11),
        hoverinfo="skip",
        showlegend=False,
    ))

    x_min = age["first_added"].min() - pd.Timedelta(days=60)
    x_max = age["first_added"].max() + pd.Timedelta(days=400)

    fig_age.update_layout(
        **_BASE_LAYOUT,
        xaxis=dict(
            gridcolor="#282828",
            tickfont=dict(color="#FFFFFF", size=10),
            range=[x_min, x_max],
        ),
        yaxis=dict(
            tickfont=dict(color="#FFFFFF"),
            categoryorder="array",
            categoryarray=age["playlist_name"].tolist(),
        ),
        height=max(200, len(age) * 80),
        showlegend=False,
    )
    st.plotly_chart(fig_age, use_container_width=True)