import html
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from db.queries import get_all_tracks, load_audio_features_by_playlist, load_playlist_meta
from config import AUDIO_FEATURES, NORMALIZED_FEATURES

from utils import inject_global_css
inject_global_css()
from utils import inject_sidebar_nav, spotify_icon_html, page_brand_html
inject_sidebar_nav("Playlist Comparison")
from utils import check_collection_mode
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
if st.session_state.get("mode") == "🔗 Your Collection" and st.session_state.get("uc_active"):
    n_unique = df["track_id"].nunique()
    n_pl     = df["playlist_name"].nunique()
    st.info(f"🎵 Viewing: Your Collection — {n_unique:,} unique tracks across {n_pl} playlists (duplicates across playlists not counted)")
# ---------------------------------------------------------------------------

if st.session_state.get("mode") == "🔗 Your Collection":
    meta = pd.DataFrame(st.session_state.get("uc_playlists", []))
    meta = meta.rename(columns={"name": "playlist_name", "track_count": "total_tracks"})
    _af_cols = [c for c in ["energy", "acousticness", "valence", "danceability",
                             "speechiness", "instrumentalness", "liveness", "tempo"]
                if c in df.columns]
    af_avg = (
        df.groupby("playlist_name")[_af_cols]
        .mean()
        .reset_index()
    ) if _af_cols else pd.DataFrame()
else:
    meta   = load_playlist_meta()
    af_avg = load_audio_features_by_playlist()
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fmt_duration(minutes: float) -> str:
    m = int(minutes)
    s = int(round((minutes - m) * 60))
    return f"{m}:{s:02d}"

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

size       = meta.sort_values("total_tracks", ascending=False).reset_index(drop=True)
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

followers     = meta.sort_values("followers", ascending=False).reset_index(drop=True)
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
def _fmt_dupe_playlists(pl_list: list) -> str:
    counts: dict = {}
    for pl in pl_list:
        counts[pl] = counts.get(pl, 0) + 1
    parts = [f"{pl} (×{cnt})" if cnt > 1 else pl for pl, cnt in sorted(counts.items())]
    return " · ".join(parts)

# Build raw per-occurrence data (real Spotify IDs) shared by both duplicate sections.
# Use raw session state in YC mode so skipped/failed tracks retain their real Spotify IDs.
_is_yc = st.session_state.get("mode") == "🔗 Your Collection" and st.session_state.get("uc_active")
if _is_yc:
    _all_uc_raw = (
        st.session_state.get("uc_enriched", [])
        + st.session_state.get("uc_skipped", [])
        + st.session_state.get("uc_failed", [])
    )
    _raw_all = pd.DataFrame(_all_uc_raw)
    if not _raw_all.empty:
        _dupe_src   = _raw_all[["id", "playlist_name"]].rename(columns={"id": "track_id"})
        _track_info = (
            _raw_all.rename(columns={"id": "track_id", "name": "track_name", "artists": "artist_display"})
            .drop_duplicates("track_id")[["track_id", "track_name", "artist_display"]]
        )
        _ver_src = _raw_all[["id", "name", "artists", "playlist_name"]].rename(
            columns={"id": "track_id", "name": "track_name", "artists": "artist_name"}
        )
    else:
        _dupe_src   = pd.DataFrame(columns=["track_id", "playlist_name"])
        _track_info = pd.DataFrame(columns=["track_id", "track_name", "artist_display"])
        _ver_src    = pd.DataFrame(columns=["track_id", "track_name", "artist_name", "playlist_name"])
else:
    _dupe_src   = df[["track_id", "playlist_name"]]
    _track_info = df.drop_duplicates("track_id")[["track_id", "track_name", "artist_display"]]
    _ver_src    = df[["track_id", "track_name", "artist_name", "playlist_name"]].copy()

_dupe_src = _dupe_src[_dupe_src["track_id"].notna() & (_dupe_src["track_id"] != "")]
_ver_src  = _ver_src[_ver_src["track_id"].notna() & (_ver_src["track_id"] != "")]

# ---------------------------------------------------------------------------
# Section 1c-A — Exact duplicates (same Spotify ID)
# ---------------------------------------------------------------------------
st.markdown("## Exact Duplicates")
st.markdown(
    "<p style='color:#B3B3B3; margin-top:-8px; font-size:0.85rem;'>"
    "Tracks saved more than once with the exact same Spotify ID — across or within playlists.</p>",
    unsafe_allow_html=True,
)

_dupe_groups = (
    _dupe_src.groupby("track_id")
    .agg(pl_list=("playlist_name", list), total=("playlist_name", "count"))
    .reset_index()
)
_dupes = _dupe_groups[_dupe_groups["total"] > 1].copy()
_dupes["Playlists"] = _dupes["pl_list"].apply(_fmt_dupe_playlists)
_dupes = _dupes.merge(_track_info, on="track_id", how="left")
_dupes = _dupes.sort_values("track_name").reset_index(drop=True)
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
        _dupes[["track_name", "artist_display", "Playlists"]]
        .rename(columns={"track_name": "Track", "artist_display": "Artist"}),
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

_ver_groups = (
    _ver_src.groupby(["track_name", "artist_name"])
    .agg(
        n_unique_ids=("track_id", "nunique"),
        total=("track_id", "count"),
        pl_list=("playlist_name", list),
    )
    .reset_index()
)
_versions = _ver_groups[(_ver_groups["total"] > 1) & (_ver_groups["n_unique_ids"] > 1)].copy()
_versions["Playlists"] = _versions["pl_list"].apply(_fmt_dupe_playlists)
_versions = _versions.sort_values("track_name").reset_index(drop=True)
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
        _versions[["track_name", "artist_name", "n_unique_ids", "Playlists"]]
        .rename(columns={"track_name": "Track", "artist_name": "Artist", "n_unique_ids": "Versions"}),
        use_container_width=True,
        hide_index=True,
    )

st.markdown("<hr style='border-color:#333; margin-top:24px; margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 2 — Duration
# ---------------------------------------------------------------------------
st.markdown("## Duration")
st.markdown("<p style='color:#B3B3B3; margin-top:-8px; font-size:0.85rem;'>The most extreme tracks.</p>", unsafe_allow_html=True)

if "duration_raw" in df.columns:
    dur_df = df.copy()
    if st.session_state.get("mode") == "🔗 Your Collection":
        dur_df["duration_raw"] = dur_df["duration_raw"] / 60000

    dur          = dur_df.groupby("playlist_name")["duration_raw"].agg(["mean", "min", "max"]).reset_index()
    dur.columns  = ["playlist_name", "avg_min", "min_min", "max_min"]
    longest_row  = dur_df.loc[dur_df["duration_raw"].idxmax()]
    shortest_row = dur_df.loc[dur_df["duration_raw"].idxmin()]

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        <div style="background:#282828; border-radius:14px; padding:22px 24px; border:1px solid #333;">
            <div style="font-size:1.6rem;">⏱️</div>
            <div style="color:#B3B3B3; font-size:0.78rem; font-weight:600; letter-spacing:0.06em; text-transform:uppercase; margin-top:8px;">Longest Track</div>
            <div style="color:#FFFFFF; font-size:1.1rem; font-weight:800; margin-top:6px;">{longest_row['track_name']}</div>
            <div style="color:#1DB954; font-size:0.85rem; margin-top:4px;">{longest_row['artist_display']} · {longest_row['playlist_name']} · {fmt_duration(longest_row['duration_raw'])}</div>
        </div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div style="background:#282828; border-radius:14px; padding:22px 24px; border:1px solid #333;">
            <div style="font-size:1.6rem;">⚡</div>
            <div style="color:#B3B3B3; font-size:0.78rem; font-weight:600; letter-spacing:0.06em; text-transform:uppercase; margin-top:8px;">Shortest Track</div>
            <div style="color:#FFFFFF; font-size:1.1rem; font-weight:800; margin-top:6px;">{shortest_row['track_name']}</div>
            <div style="color:#1DB954; font-size:0.85rem; margin-top:4px;">{shortest_row['artist_display']} · {shortest_row['playlist_name']} · {fmt_duration(shortest_row['duration_raw'])}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

st.markdown("<hr style='border-color:#333; margin-top:24px; margin-bottom:24px;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 3 — Popularity  →  vertical bar zoomed in + KPI cards
# ---------------------------------------------------------------------------
st.markdown("## Popularity")
st.markdown("<p style='color:#B3B3B3; margin-top:-8px; font-size:0.85rem;'>Average Spotify popularity score (0–100) per playlist.</p>", unsafe_allow_html=True)

if "popularity_raw" in df.columns:
    pop = df.groupby("playlist_name")["popularity_raw"].mean().reset_index()
    pop.columns = ["playlist_name", "avg_popularity"]
    pop = pop.sort_values("avg_popularity", ascending=False)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(kpi_card("⭐", "Most Popular Playlist",
            pop.iloc[0]["playlist_name"], f"{pop.iloc[0]['avg_popularity']:.1f} avg score"), unsafe_allow_html=True)
    with col2:
        st.markdown(kpi_card("💀", "Least Popular Playlist",
            pop.iloc[-1]["playlist_name"], f"{pop.iloc[-1]['avg_popularity']:.1f} avg score"), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    y_min = max(0, pop["avg_popularity"].min() - 5)
    y_max = min(100, pop["avg_popularity"].max() + 8)

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

    available_items = [
        (feat, m) for feat, m in FEATURE_LABELS.items()
        if feat in af_avg.columns and af_avg[feat].notna().any()
    ]
    for row_items in [available_items[:4], available_items[4:]]:
        if not row_items:
            continue
        cols = st.columns(len(row_items))
        for col, (feat, (icon, label)) in zip(cols, row_items):
            winner = af_avg.loc[af_avg[feat].idxmax()]
            with col:
                st.markdown(kpi_card(icon, label, winner["playlist_name"], f"{winner[feat]:.3f}"), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

    _heatmap_feats = [f for f in NORMALIZED_FEATURES if f in af_avg.columns and af_avg[f].notna().any()]
    if _heatmap_feats:
        heatmap_df = af_avg.set_index("playlist_name")[_heatmap_feats]
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
if "artist_genres" in df.columns:
    st.markdown("## Genre Diversity")
    st.markdown("<p style='color:#B3B3B3; margin-top:-8px; font-size:0.85rem;'>Number of unique genres across all artists per playlist.</p>", unsafe_allow_html=True)

    def count_unique_genres(genres_series: pd.Series) -> int:
        genres = set()
        for g in genres_series.dropna():
            for part in str(g).split(","):
                part = part.strip()
                if part:
                    genres.add(part.lower())
        return len(genres)

    diversity         = df.groupby("playlist_name")["artist_genres"].apply(count_unique_genres).reset_index()
    diversity.columns = ["playlist_name", "unique_genres"]
    diversity         = diversity.sort_values("unique_genres", ascending=True)

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

if "release_year" in df.columns:
    release         = (
        df[df["release_year"].notna()]
        .groupby("playlist_name")["release_year"]
        .agg(["mean", "min", "max"])
        .reset_index()
    )
    release.columns = ["playlist_name", "avg_release_year", "min_year", "max_year"]
    release         = release.sort_values("avg_release_year", ascending=True)

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

if "decade" in df.columns:
    decade_dist = (
        df[df["decade"].notna()]
        .assign(decade_label=lambda x: x["decade"].astype(int).astype(str) + "s")
        .groupby(["playlist_name", "decade_label"])
        .size()
        .reset_index(name="count")
    )

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
            deduped   = df.drop_duplicates(subset="track_id")
            mask      = (
                (deduped["playlist_name"] == selected_playlist) &
                (deduped["decade"].notna()) &
                (deduped["decade"].astype("Int64") == decade_int)
            )
            cols_show = [c for c in ["track_name", "artist_display", "release_year", "popularity_raw"] if c in deduped.columns]
            dec_tracks = deduped[mask][cols_show].copy()
            if "release_year" in dec_tracks.columns:
                dec_tracks = dec_tracks.sort_values("release_year")
                dec_tracks["release_year"] = dec_tracks["release_year"].fillna(0).astype(int)
            dec_tracks = dec_tracks.rename(columns={
                "track_name": "Track", "artist_display": "Artist",
                "release_year": "Year", "popularity_raw": "Popularity",
            })
            st.markdown(
                f"<p style='color:#1DB954;font-weight:700;font-size:1rem;margin-bottom:4px;'>"
                f"🎯 {len(dec_tracks)} tracks — {selected_playlist} · {selected_decade_label}</p>",
                unsafe_allow_html=True,
            )
            st.dataframe(dec_tracks.reset_index(drop=True), use_container_width=True, hide_index=True)

st.markdown("<hr style='border-color:#333; margin-top:24px; margin-bottom:24px;'>", unsafe_allow_html=True)
# ---------------------------------------------------------------------------
# Section 8 — Playlist Age  →  dot plot / timeline
# ---------------------------------------------------------------------------
st.markdown("## Playlist Age")
st.markdown("<p style='color:#B3B3B3; margin-top:-8px; font-size:0.85rem;'>When each playlist was first active — position on timeline = date.</p>", unsafe_allow_html=True)

if "added_at" in df.columns:
    age         = (
        df[df["added_at"].notna()]
        .assign(added_at=lambda x: pd.to_datetime(x["added_at"]))
        .groupby("playlist_name")["added_at"]
        .min()
        .reset_index()
    )
    age.columns = ["playlist_name", "first_added"]
    age         = age.sort_values("first_added", ascending=True).reset_index(drop=True)
    age["first_added_str"] = age["first_added"].dt.strftime("%b %Y")

    missing = set(df["playlist_name"].unique()) - set(age["playlist_name"].tolist())
    if missing:
        st.markdown(f"<p style='color:#B3B3B3; font-size:0.8rem;'>⚠️ No date data for: {', '.join(sorted(missing))}</p>", unsafe_allow_html=True)

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