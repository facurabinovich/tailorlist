import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import datetime

from utils import inject_global_css, inject_sidebar_nav, check_collection_mode, spotify_icon_html, page_brand_html
from db.queries import get_all_tracks

# ── Boilerplate ───────────────────────────────────────────────────────────────
inject_global_css()
inject_sidebar_nav("Artist / Album")
if not check_collection_mode():
    st.stop()

# ── Data ──────────────────────────────────────────────────────────────────────
df = get_all_tracks()

# ── Base layout for all Plotly charts ────────────────────────────────────────
_BASE_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#AAAAAA", family="Inter, sans-serif", size=12),
    margin=dict(t=40, b=40, l=40, r=40),
    hoverlabel=dict(bgcolor="#282828", font_color="#FFFFFF", font_size=13),
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt_duration(minutes: float) -> str:
    """Format decimal minutes → m:ss string."""
    total_sec = int(round(minutes * 60))
    m, s = divmod(total_sec, 60)
    return f"{m}:{s:02d}"


def genre_pills_html(genres_series: pd.Series) -> str:
    """Build HTML genre pill string from a column of comma-separated genres."""
    all_genres: list[str] = []
    for val in genres_series.dropna():
        all_genres.extend([g.strip() for g in str(val).split(",") if g.strip()])
    counts = pd.Series(all_genres).value_counts()
    top = counts.head(8).index.tolist()
    pills = "".join(
        f'<span style="background:#1DB954;color:#000;border-radius:12px;'
        f'padding:2px 10px;margin:2px;font-size:0.75rem;font-weight:600;'
        f'display:inline-block;">{g}</span>'
        for g in top
    )
    return pills


def header_card_html(name: str, track_count: int, playlist_count: int,
                     genre_html: str = "") -> str:
    lines = [
        '<div style="background:#282828;border-radius:12px;padding:20px 24px;'
        'margin-bottom:20px;">',
        f'<div style="font-size:1.6rem;font-weight:700;color:#FFFFFF;'
        f'margin-bottom:6px;">{name}</div>',
        f'<div style="color:#AAAAAA;font-size:0.9rem;margin-bottom:{'10px' if genre_html else '0'};">'
        f'{track_count} track{"s" if track_count != 1 else ""} across '
        f'{playlist_count} playlist{"s" if playlist_count != 1 else ""}</div>',
    ]
    if genre_html:
        lines.append(f'<div style="margin-top:8px;">{genre_html}</div>')
    lines.append("</div>")
    return "".join(lines)


# ── Page header ───────────────────────────────────────────────────────────────
st.markdown(page_brand_html(), unsafe_allow_html=True)
st.markdown(
    f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px;">'
    f'{spotify_icon_html(36)}'
    f'<span style="font-size:1.8rem;font-weight:700;color:#FFFFFF;">Artist / Album Deep Dive</span>'
    f"</div>",
    unsafe_allow_html=True,
)
st.markdown(
    '<p style="color:#AAAAAA;margin-top:0;margin-bottom:24px;">'
    "Drill into a specific artist or album across your collection.</p>",
    unsafe_allow_html=True,
)

# ── Mode toggle ───────────────────────────────────────────────────────────────
# If an album was requested via the pie chart button, force Album mode
_preselect_album = st.session_state.pop("album_preselect", None)

# If redirected from artist page, lock mode to Album and persist it
if _preselect_album:
    st.session_state["_forced_mode"] = "💿 Album"

# Use persisted mode as radio default if present
_forced_mode = st.session_state.get("_forced_mode")
mode = st.radio(
    "Browse by",
    options=["🎤 Artist", "💿 Album"],
    index=1 if _forced_mode == "💿 Album" else 0,
    horizontal=True,
    label_visibility="collapsed",
)
is_artist_mode = mode == "🎤 Artist"

# Clear the forced mode and pinned selection once user manually switches back to Artist
if mode == "🎤 Artist":
    st.session_state.pop("_forced_mode", None)
    st.session_state.pop("_pinned_selection", None)
mode_key = "artist" if is_artist_mode else "album"

# ── Search selectbox ──────────────────────────────────────────────────────────
MIN_TRACKS_ARTIST = 5
MIN_TRACKS_ALBUM = 3

if is_artist_mode:
    track_counts_all = df["artist_name"].value_counts()
    filtered_artists = track_counts_all[track_counts_all >= MIN_TRACKS_ARTIST]
    eligible = sorted(filtered_artists.index.tolist())
    if not eligible:
        st.info(
            f"No artists meet the minimum track threshold yet. "
            "Try adding more playlists to your collection."
        )
        st.stop()
    top_default = filtered_artists.idxmax() if not filtered_artists.empty else eligible[0]
    label = "Select an artist"
    threshold_note = (
        f"Only artists with {MIN_TRACKS_ARTIST}+ tracks in your collection are shown. "
        "Add more playlists to unlock more artists."
    )
    # Rank eligible artists by track count; badge the top 20
    ranked_artists = (
        track_counts_all[track_counts_all >= MIN_TRACKS_ARTIST]
        .sort_values(ascending=False)
        .reset_index()
    )
    ranked_artists.columns = ["artist_name", "count"]
    rank_map_artists = {
        row["artist_name"]: i + 1
        for i, row in ranked_artists.head(20).iterrows()
    }
    options_raw = eligible
    options = [
        f"🏆 #{rank_map_artists[name]} · {name}" if name in rank_map_artists else name
        for name in eligible
    ]
else:
    if "album_name" not in df.columns:
        st.warning("Album data is not available in your collection.")
        st.stop()
    # Group by (album, artist) pair to avoid "Greatest Hits" collisions across artists
    pair_counts = (
        df.dropna(subset=["album_name", "artist_name", "track_id"])
        .groupby(["album_name", "artist_name"], observed=True)["track_id"]
        .nunique()
        .reset_index(name="n")
    )
    pair_counts = pair_counts[pair_counts["n"] >= MIN_TRACKS_ALBUM].copy()
    pair_counts["label"] = pair_counts["album_name"] + " — " + pair_counts["artist_name"]
    pair_counts = pair_counts.sort_values("label")
    eligible_pairs = pair_counts[["label", "album_name", "artist_name", "n"]].reset_index(drop=True)
    options_raw = eligible_pairs["label"].tolist()
    if not pair_counts.empty:
        top_default = pair_counts.loc[pair_counts["n"].idxmax(), "label"]
    else:
        st.info(
            f"No albums meet the minimum track threshold yet. "
            "Try adding more playlists to your collection."
        )
        st.stop()
    label = "Select an album"
    threshold_note = (
        f"Only albums with {MIN_TRACKS_ALBUM}+ tracks in your collection are shown. "
        "Add more playlists to unlock more albums."
    )
    # Rank the top 10 albums by unique track count
    top10_pairs = pair_counts.nlargest(10, "n").reset_index(drop=True)
    rank_map_albums = {
        row["label"]: i + 1
        for i, row in top10_pairs.iterrows()
    }
    options = [
        f"🏆 #{rank_map_albums[lbl]} · {lbl}" if lbl in rank_map_albums else lbl
        for lbl in options_raw
    ]

_pinned = st.session_state.get("_pinned_selection")

if not is_artist_mode and _pinned:
    match = next((o for o in options if _pinned in o), None)
    default_index = options.index(match) if match else 0
else:
    default_index = options_raw.index(top_default) if top_default in options_raw else 0

st.caption(f"ℹ️ {threshold_note}")

selected_display = st.selectbox(label, options=options, index=default_index, label_visibility="visible")
selected = options_raw[options.index(selected_display)]

# ── Filter df to selection ────────────────────────────────────────────────────
if is_artist_mode:
    sel_df = df[df["artist_name"] == selected].copy()
else:
    # Resolve back to album_name + artist_name from the pair lookup
    pair_row = eligible_pairs[eligible_pairs["label"] == selected].iloc[0]
    sel_df = df[
        (df["album_name"] == pair_row["album_name"]) &
        (df["artist_name"] == pair_row["artist_name"])
    ].copy()

# Deduplicate: bridge_song_artists can produce multiple rows per track when an
# artist appears under different roles. Keep one row per (track_id, playlist_name).
if "track_id" in sel_df.columns:
    sel_df = sel_df.drop_duplicates(subset=["track_id", "playlist_name"])

track_count = sel_df["track_id"].nunique() if "track_id" in sel_df.columns else len(sel_df)
playlist_count = sel_df["playlist_name"].nunique()
min_threshold = MIN_TRACKS_ARTIST if is_artist_mode else MIN_TRACKS_ALBUM
enough = track_count >= min_threshold

# ── Duration: normalise YC milliseconds → minutes ────────────────────────────
is_yc = st.session_state.get("mode") == "🔗 Your Collection"
if "duration_raw" in sel_df.columns:
    if is_yc:
        sel_df["duration_min"] = sel_df["duration_raw"] / 60_000
    else:
        sel_df["duration_min"] = sel_df["duration_raw"]

# ── Header card ───────────────────────────────────────────────────────────────
display_name = selected if is_artist_mode else f"{pair_row['album_name']} · {pair_row['artist_name']}"
genre_html = ""
if is_artist_mode and "artist_genres" in sel_df.columns and not sel_df["artist_genres"].isna().all():
    genre_html = genre_pills_html(sel_df["artist_genres"])

st.markdown(header_card_html(display_name, track_count, playlist_count, genre_html),
            unsafe_allow_html=True)

st.markdown("<hr style='border-color:#282828;margin:16px 0;'>", unsafe_allow_html=True)

# ── Tracks table ──────────────────────────────────────────────────────────────
st.markdown("### 🎵 Tracks")
st.caption("Sorted by popularity — most streamed tracks first. The same track may appear more than once if you saved it across multiple playlists.")

table_cols = ["track_name", "playlist_name"]
rename_map = {"track_name": "Track", "playlist_name": "Playlist"}

# In artist mode, show which album each track belongs to
if is_artist_mode and "album_name" in sel_df.columns:
    table_cols.insert(1, "album_name")
    rename_map["album_name"] = "Album"

has_popularity = "popularity_raw" in sel_df.columns
if has_popularity:
    table_cols.append("popularity_raw")
    rename_map["popularity_raw"] = "Popularity"

if "release_year" in sel_df.columns:
    table_cols.append("release_year")
    rename_map["release_year"] = "Year"

if "duration_min" in sel_df.columns:
    sel_df["_duration_fmt"] = sel_df["duration_min"].apply(
        lambda x: fmt_duration(x) if pd.notna(x) else "—"
    )
    table_cols.append("_duration_fmt")
    rename_map["_duration_fmt"] = "Duration"

sort_col = "popularity_raw" if has_popularity else "track_name"
table_df = (
    sel_df[table_cols]
    .rename(columns=rename_map)
    .sort_values(rename_map[sort_col], ascending=not has_popularity)
    .reset_index(drop=True)
)

# Cast Year to nullable int for clean display
if "Year" in table_df.columns:
    table_df["Year"] = table_df["Year"].astype("Int64")

# Column config: auto-width on all columns
col_config = {col: st.column_config.Column(width="auto") for col in table_df.columns}

st.dataframe(table_df, use_container_width=True, hide_index=True, column_config=col_config)

st.markdown("<hr style='border-color:#333;margin:24px 0;'>", unsafe_allow_html=True)

# ── Albums breakdown (artist mode only) ───────────────────────────────────────
if is_artist_mode and "album_name" in sel_df.columns:
    st.markdown("### 💿 Albums in Your Collection")
    st.markdown(
        "<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>"
        "All albums from this artist in your collection. Albums with 3+ tracks are available for deep dive analysis.</p>",
        unsafe_allow_html=True,
    )

    album_counts = (
        sel_df.groupby("album_name", observed=True)["track_id"]
        .nunique()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )

    # All albums in pie — no threshold
    pie_df = album_counts.copy()

    # Color palette for all slices
    n_albums = len(pie_df)
    greens = [
        f"hsl({120 + i * 12 % 60}, {55 + i * 7 % 30}%, {32 + i * 8 % 28}%)"
        for i in range(n_albums)
    ]

    # Static pie chart
    fig_albums = go.Figure(
        go.Pie(
            labels=pie_df["album_name"],
            values=pie_df["count"],
            marker=dict(colors=greens, line=dict(color="#181818", width=2)),
            hovertemplate="<b>%{label}</b><br>%{value} tracks<br>%{percent}<extra></extra>",
            textinfo="percent",
            textfont=dict(size=12, color="#FFFFFF"),
            insidetextorientation="radial",
        )
    )
    fig_albums.update_layout(
        **{
            **_BASE_LAYOUT,
            "legend": dict(
                orientation="v",
                x=1.02,
                y=0.5,
                xanchor="left",
                yanchor="middle",
                font=dict(color="#FFFFFF", size=11),
                bgcolor="rgba(0,0,0,0)",
                itemsizing="constant",
            ),
            "height": max(420, 40 * len(pie_df) + 120),
            "margin": dict(t=20, b=20, l=20, r=200),
        }
    )

    st.plotly_chart(fig_albums, use_container_width=True)

    # ── Album selector → deep dive ────────────────────────────────────────────
    # Only albums with 3+ unique tracks are eligible for deep dive
    named_albums = (
        album_counts[album_counts["count"] >= MIN_TRACKS_ALBUM]["album_name"].tolist()
    )

    st.markdown(
        "<p style='color:#B3B3B3;font-size:0.85rem;margin-top:4px;'>"
        "Want to go deeper on a specific album? Select one below and hit the button "
        "to open its full analysis.</p>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"ℹ️ Only albums with {MIN_TRACKS_ALBUM}+ tracks in your collection appear here — "
        "the album deep dive requires at least 3 tracks to generate meaningful insights."
    )
    col_sel, col_btn = st.columns([3, 1], vertical_alignment="bottom")
    with col_sel:
        chosen_album = st.selectbox(
            "Dive into an album",
            options=named_albums,
            label_visibility="collapsed",
        )
    with col_btn:
        if st.button("🔍 Analyze album", use_container_width=True):
            st.session_state["album_preselect"] = f"{chosen_album} — {selected}"
            st.session_state["_pinned_selection"] = f"{chosen_album} — {selected}"
            st.session_state["_forced_mode"] = "💿 Album"
            st.switch_page("pages/_album_goto.py")
    st.caption("↑ After clicking, scroll up to see the album analysis.")

    st.markdown("<hr style='border-color:#333;margin:24px 0;'>", unsafe_allow_html=True)

# ── Extremes ──────────────────────────────────────────────────────────────────
st.markdown("### ⚡ Extremes")
st.markdown(
    "<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>The most notable tracks in this selection.</p>",
    unsafe_allow_html=True,
)

def extreme_card_html(icon: str, label: str, track: str, detail: str) -> str:
    return (
        f'<div style="background:#282828;border-radius:14px;padding:22px 24px;'
        f'border:1px solid #333;height:100%;">'
        f'<div style="font-size:1.6rem;">{icon}</div>'
        f'<div style="color:#B3B3B3;font-size:0.78rem;font-weight:600;letter-spacing:0.06em;'
        f'text-transform:uppercase;margin-top:8px;">{label}</div>'
        f'<div style="color:#FFFFFF;font-size:1.05rem;font-weight:800;margin-top:6px;">{track}</div>'
        f'<div style="color:#1DB954;font-size:0.85rem;margin-top:4px;">{detail}</div>'
        f'</div>'
    )

_extremes_shown = False

# Duration extremes
if "duration_min" in sel_df.columns:
    dur_valid = sel_df.dropna(subset=["duration_min"])
    if not dur_valid.empty:
        longest  = dur_valid.loc[dur_valid["duration_min"].idxmax()]
        shortest = dur_valid.loc[dur_valid["duration_min"].idxmin()]
        col1, col2 = st.columns(2)
        with col1:
            detail = f"{longest['artist_display']} · {longest['playlist_name']} · {fmt_duration(longest['duration_min'])}"
            st.markdown(extreme_card_html("⏱️", "Longest Track", longest["track_name"], detail), unsafe_allow_html=True)
        with col2:
            detail = f"{shortest['artist_display']} · {shortest['playlist_name']} · {fmt_duration(shortest['duration_min'])}"
            st.markdown(extreme_card_html("⚡", "Shortest Track", shortest["track_name"], detail), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        _extremes_shown = True

# Popularity extremes
if "popularity_raw" in sel_df.columns:
    pop_valid = sel_df.dropna(subset=["popularity_raw"])
    if not pop_valid.empty:
        most_pop  = pop_valid.loc[pop_valid["popularity_raw"].idxmax()]
        least_pop = pop_valid.loc[pop_valid["popularity_raw"].idxmin()]
        col1, col2 = st.columns(2)
        with col1:
            detail = f"{most_pop['artist_display']} · {most_pop['playlist_name']} · {int(most_pop['popularity_raw'])} popularity"
            st.markdown(extreme_card_html("⭐", "Most Popular Track", most_pop["track_name"], detail), unsafe_allow_html=True)
        with col2:
            detail = f"{least_pop['artist_display']} · {least_pop['playlist_name']} · {int(least_pop['popularity_raw'])} popularity"
            st.markdown(extreme_card_html("💀", "Least Popular Track", least_pop["track_name"], detail), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        _extremes_shown = True

# Release year extremes — artist mode only (album tracks share the same year)
if is_artist_mode and "release_year" in sel_df.columns:
    yr_valid = sel_df.dropna(subset=["release_year"])
    if not yr_valid.empty:
        oldest  = yr_valid.loc[yr_valid["release_year"].idxmin()]
        newest  = yr_valid.loc[yr_valid["release_year"].idxmax()]
        col1, col2 = st.columns(2)
        with col1:
            detail = f"{oldest['artist_display']} · {oldest['playlist_name']} · {int(oldest['release_year'])}"
            st.markdown(extreme_card_html("🕰️", "Oldest Track", oldest["track_name"], detail), unsafe_allow_html=True)
        with col2:
            detail = f"{newest['artist_display']} · {newest['playlist_name']} · {int(newest['release_year'])}"
            st.markdown(extreme_card_html("🆕", "Newest Track", newest["track_name"], detail), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        _extremes_shown = True

if not _extremes_shown:
    st.info("No extreme track data available for this selection.")

st.markdown("<hr style='border-color:#333;margin:24px 0;'>", unsafe_allow_html=True)

# ── Playlist distribution ─────────────────────────────────────────────────────
if playlist_count > 1:
    st.markdown("### 📂 Playlist Distribution")
    st.markdown(
        "<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>"
        "Click a bar to see the tracks in that playlist.</p>",
        unsafe_allow_html=True,
    )

    pl_counts = (
        sel_df.groupby("playlist_name", observed=True)
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )

    fig_pl = go.Figure(
        go.Bar(
            x=pl_counts["playlist_name"],
            y=pl_counts["count"],
            marker_color="#1DB954",
            marker_line_width=0,
            hovertemplate="<b>%{x}</b><br>%{y} track%{customdata}<extra></extra>",
            customdata=["s" if c != 1 else "" for c in pl_counts["count"]],
        )
    )
    fig_pl.update_layout(
        **{
            **_BASE_LAYOUT,
            "xaxis": dict(
                title="",
                type="category",
                categoryorder="total descending",
                tickfont=dict(color="#AAAAAA"),
            ),
            "yaxis": dict(
                title="Tracks",
                gridcolor="#333333",
                tickfont=dict(color="#AAAAAA"),
                tickformat="d",
            ),
        }
    )

    selected_pl = st.plotly_chart(fig_pl, use_container_width=True, on_select="rerun", key=f"pl_dist_chart_{mode_key}")

    if selected_pl and selected_pl.selection and selected_pl.selection.points:
        clicked_playlist = selected_pl.selection.points[0]["x"]
        pl_tracks = (
            sel_df[sel_df["playlist_name"] == clicked_playlist]
            .copy()
        )
        # Build display columns
        pl_cols = ["track_name"]
        pl_rename = {"track_name": "Track"}
        if is_artist_mode and "album_name" in pl_tracks.columns:
            pl_cols.append("album_name")
            pl_rename["album_name"] = "Album"
        if "popularity_raw" in pl_tracks.columns:
            pl_cols.append("popularity_raw")
            pl_rename["popularity_raw"] = "Popularity"
        if "release_year" in pl_tracks.columns:
            pl_cols.append("release_year")
            pl_rename["release_year"] = "Year"
        if "duration_min" in pl_tracks.columns:
            pl_tracks["_dur"] = pl_tracks["duration_min"].apply(
                lambda x: fmt_duration(x) if pd.notna(x) else "—"
            )
            pl_cols.append("_dur")
            pl_rename["_dur"] = "Duration"

        sort_col_pl = "popularity_raw" if "popularity_raw" in pl_tracks.columns else "track_name"
        pl_table = (
            pl_tracks[pl_cols]
            .rename(columns=pl_rename)
            .sort_values(pl_rename[sort_col_pl], ascending=(sort_col_pl == "track_name"))
            .reset_index(drop=True)
        )
        if "Year" in pl_table.columns:
            pl_table["Year"] = pl_table["Year"].astype("Int64")

        st.markdown(
            f"<p style='color:#1DB954;font-weight:700;font-size:1rem;margin-bottom:4px;'>"
            f"🎯 {len(pl_table)} track{'s' if len(pl_table) != 1 else ''} in <b>{clicked_playlist}</b></p>",
            unsafe_allow_html=True,
        )
        pl_col_config = {col: st.column_config.Column(width="auto") for col in pl_table.columns}
        st.dataframe(pl_table, use_container_width=True, hide_index=True, column_config=pl_col_config)

    st.markdown("<hr style='border-color:#282828;margin:16px 0;'>", unsafe_allow_html=True)

# ── Audio fingerprint (radar) ─────────────────────────────────────────────────
RADAR_FEATURES = ["energy", "valence", "danceability", "acousticness", "speechiness", "liveness"]
available_radar = [f for f in RADAR_FEATURES if f in sel_df.columns]
n_enriched = int(sel_df[available_radar].dropna(how="all").shape[0]) if available_radar else 0

if len(available_radar) >= 3:
    st.markdown("### 🎛️ Audio Fingerprint")

    if not enough:
        st.info("Not enough tracks to show audio analysis — add more playlists to get richer insights.")
    elif n_enriched == 0:
        if is_yc:
            st.info(
                "Audio features aren't available for these tracks — "
                "they weren't found in the audio database during enrichment."
            )
        else:
            st.info("Audio features haven't been loaded for these tracks yet.")
    else:
        if n_enriched < len(sel_df):
            st.caption(f"ℹ️ Based on {n_enriched} of {len(sel_df)} tracks — the rest haven't been enriched yet.")
        means = sel_df[available_radar].mean()

        # Normalise tempo separately: use collection-wide min/max
        show_tempo = "tempo" in sel_df.columns
        if show_tempo:
            t_min = df["tempo"].min()
            t_max = df["tempo"].max()
            mean_tempo_raw = sel_df["tempo"].mean()
            mean_tempo_norm = (mean_tempo_raw - t_min) / (t_max - t_min) if t_max > t_min else 0.5

            radar_labels = available_radar + ["tempo"]
            radar_values_norm = means.tolist() + [mean_tempo_norm]
            # Raw values for hover
            raw_values = means.tolist() + [mean_tempo_raw]
            hover_texts = [
                f"{f.capitalize()}: {means[f]:.2f}" for f in available_radar
            ] + [f"Tempo: {mean_tempo_raw:.0f} BPM"]
        else:
            radar_labels = available_radar
            radar_values_norm = means.tolist()
            raw_values = means.tolist()
            hover_texts = [f"{f.capitalize()}: {means[f]:.2f}" for f in available_radar]

        # Close the polygon
        radar_labels_closed = radar_labels + [radar_labels[0]]
        radar_values_closed = radar_values_norm + [radar_values_norm[0]]
        hover_closed = hover_texts + [hover_texts[0]]

        fig_radar = go.Figure(
            go.Scatterpolar(
                r=radar_values_closed,
                theta=radar_labels_closed,
                fill="toself",
                fillcolor="rgba(29,185,84,0.2)",
                line=dict(color="#1DB954", width=2),
                hovertemplate="%{customdata}<extra></extra>",
                customdata=hover_closed,
            )
        )
        fig_radar.update_layout(
            **{
                **_BASE_LAYOUT,
                "polar": dict(
                    bgcolor="rgba(0,0,0,0)",
                    angularaxis=dict(
                        tickfont=dict(color="#FFFFFF", size=12),
                        linecolor="#444444",
                        gridcolor="#333333",
                    ),
                    radialaxis=dict(
                        visible=True,
                        range=[0, 1],
                        tickfont=dict(color="#888888", size=9),
                        gridcolor="#333333",
                        linecolor="#333333",
                    ),
                ),
                "showlegend": False,
            }
        )
        st.plotly_chart(fig_radar, use_container_width=True)

    st.markdown("<hr style='border-color:#282828;margin:16px 0;'>", unsafe_allow_html=True)

# ── Popularity distribution ───────────────────────────────────────────────────
if "popularity_raw" in sel_df.columns:
    st.markdown("### 📊 Popularity Distribution")
    st.markdown(
        "<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>"
        "Click a bar to see the tracks in that range.</p>",
        unsafe_allow_html=True,
    )

    if not enough:
        st.info("Not enough tracks to show audio analysis — add more playlists to get richer insights.")
    else:
        BIN_SIZE = 5
        pop_vals = sel_df["popularity_raw"].dropna()
        # Build horizontal bar chart via explicit bins
        bin_edges = list(range(0, 105, BIN_SIZE))
        bin_labels = [f"{b}–{b + BIN_SIZE - 1}" for b in bin_edges[:-1]]
        bin_counts = [
            int(((pop_vals >= b) & (pop_vals < b + BIN_SIZE)).sum())
            for b in bin_edges[:-1]
        ]
        # Filter to non-zero bins for cleaner display
        non_zero = [(l, c, b) for l, c, b in zip(bin_labels, bin_counts, bin_edges[:-1]) if c > 0]
        nz_labels = [x[0] for x in non_zero]
        nz_counts = [x[1] for x in non_zero]
        nz_bins   = [x[2] for x in non_zero]

        fig_pop = go.Figure(
            go.Bar(
                x=nz_counts,
                y=nz_labels,
                orientation="h",
                marker_color="#1DB954",
                marker_line_width=0,
                customdata=nz_bins,
                hovertemplate="Popularity %{y}<br>%{x} track(s)<extra></extra>",
            )
        )
        fig_pop.update_layout(
            **{
                **_BASE_LAYOUT,
                "xaxis": dict(
                    title="Tracks",
                    gridcolor="#333333",
                    tickfont=dict(color="#AAAAAA"),
                    tickformat="d",
                ),
                "yaxis": dict(
                    title="Popularity (0–100)",
                    tickfont=dict(color="#AAAAAA"),
                    type="category",
                    autorange="reversed",
                ),
                "bargap": 0.15,
                "height": max(250, len(nz_labels) * 28),
            }
        )

        sel_pop = st.plotly_chart(fig_pop, use_container_width=True, on_select="rerun", key=f"pop_dist_chart_{mode_key}")

        if sel_pop and sel_pop.selection and sel_pop.selection.points:
            clicked_bin = sel_pop.selection.points[0]["customdata"]
            bin_min = clicked_bin
            bin_max = bin_min + BIN_SIZE
            pop_tracks = sel_df[
                (sel_df["popularity_raw"] >= bin_min) &
                (sel_df["popularity_raw"] <  bin_max)
            ].copy()

            pt_cols = ["track_name"]
            pt_rename = {"track_name": "Track"}
            if is_artist_mode and "album_name" in pop_tracks.columns:
                pt_cols.append("album_name"); pt_rename["album_name"] = "Album"
            pt_cols.append("playlist_name"); pt_rename["playlist_name"] = "Playlist"
            if "popularity_raw" in pop_tracks.columns:
                pt_cols.append("popularity_raw"); pt_rename["popularity_raw"] = "Popularity"
            if "release_year" in pop_tracks.columns:
                pt_cols.append("release_year"); pt_rename["release_year"] = "Year"
            if "duration_min" in pop_tracks.columns:
                pop_tracks["_dur"] = pop_tracks["duration_min"].apply(
                    lambda x: fmt_duration(x) if pd.notna(x) else "—"
                )
                pt_cols.append("_dur"); pt_rename["_dur"] = "Duration"

            pt_table = (
                pop_tracks[pt_cols]
                .rename(columns=pt_rename)
                .sort_values("Popularity", ascending=False)
                .reset_index(drop=True)
            )
            if "Year" in pt_table.columns:
                pt_table["Year"] = pt_table["Year"].astype("Int64")

            st.markdown(
                f"<p style='color:#1DB954;font-weight:700;font-size:1rem;margin-bottom:4px;'>"
                f"🎯 {len(pt_table)} track{'s' if len(pt_table) != 1 else ''} "
                f"— popularity {bin_min}–{bin_max - 1}</p>",
                unsafe_allow_html=True,
            )
            pt_col_config = {col: st.column_config.Column(width="auto") for col in pt_table.columns}
            st.dataframe(pt_table, use_container_width=True, hide_index=True, column_config=pt_col_config)

        # ── Popularity avg stat card ──
        avg_pop  = pop_vals.mean()
        med_pop  = pop_vals.median()
        max_pop  = pop_vals.max()
        min_pop  = pop_vals.min()
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            f'<div style="background:#282828;border-radius:12px;padding:16px 24px;'
            f'display:flex;gap:40px;flex-wrap:wrap;">'
            f'<div><div style="color:#B3B3B3;font-size:0.75rem;font-weight:600;'
            f'text-transform:uppercase;letter-spacing:0.06em;">Avg Popularity</div>'
            f'<div style="color:#FFFFFF;font-size:1.4rem;font-weight:800;">{avg_pop:.1f}</div></div>'
            f'<div><div style="color:#B3B3B3;font-size:0.75rem;font-weight:600;'
            f'text-transform:uppercase;letter-spacing:0.06em;">Median</div>'
            f'<div style="color:#FFFFFF;font-size:1.4rem;font-weight:800;">{med_pop:.1f}</div></div>'
            f'<div><div style="color:#B3B3B3;font-size:0.75rem;font-weight:600;'
            f'text-transform:uppercase;letter-spacing:0.06em;">Highest</div>'
            f'<div style="color:#1DB954;font-size:1.4rem;font-weight:800;">{int(max_pop)}</div></div>'
            f'<div><div style="color:#B3B3B3;font-size:0.75rem;font-weight:600;'
            f'text-transform:uppercase;letter-spacing:0.06em;">Lowest</div>'
            f'<div style="color:#AAAAAA;font-size:1.4rem;font-weight:800;">{int(min_pop)}</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<hr style='border-color:#282828;margin:16px 0;'>", unsafe_allow_html=True)

# ── Release timeline / Album release year ────────────────────────────────────
if "release_year" in sel_df.columns:
    yr_vals = sel_df["release_year"].dropna()

    if is_artist_mode:
        # ── Full timeline chart with click drill-down ──
        st.markdown("### 📅 Release Timeline")
        st.markdown(
            "<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>"
            "Click a bar to see the tracks from that year.</p>",
            unsafe_allow_html=True,
        )

        year_counts = (
            sel_df.dropna(subset=["release_year"])
            .groupby("release_year", observed=True)
            .size()
            .reset_index(name="count")
            .sort_values("release_year", ascending=False)
        )
        year_counts["release_year"] = year_counts["release_year"].astype("Int64")

        if year_counts.empty:
            st.info("No release year data available for this selection.")
        else:
            fig_time = go.Figure(
                go.Bar(
                    x=year_counts["count"],
                    y=year_counts["release_year"].astype(str),
                    orientation="h",
                    marker_color="#1DB954",
                    marker_line_width=0,
                    customdata=year_counts["release_year"].astype(int).tolist(),
                    hovertemplate="<b>%{y}</b><br>%{x} tracks<extra></extra>",
                )
            )
            fig_time.update_layout(
                **{
                    **_BASE_LAYOUT,
                    "xaxis": dict(
                        title="Tracks",
                        gridcolor="#333333",
                        tickfont=dict(color="#AAAAAA"),
                        tickformat="d",
                    ),
                    "yaxis": dict(
                        title="",
                        tickfont=dict(color="#AAAAAA"),
                        type="category",
                    ),
                    "bargap": 0.15,
                    "height": max(250, len(year_counts) * 28),
                }
            )

            sel_year = st.plotly_chart(fig_time, use_container_width=True, on_select="rerun", key=f"year_dist_chart_{mode_key}")

            if sel_year and sel_year.selection and sel_year.selection.points:
                clicked_year = int(sel_year.selection.points[0]["customdata"])
                yr_tracks = sel_df[sel_df["release_year"] == clicked_year].copy()

                yt_cols = ["track_name"]
                yt_rename = {"track_name": "Track"}
                if "album_name" in yr_tracks.columns:
                    yt_cols.append("album_name"); yt_rename["album_name"] = "Album"
                yt_cols.append("playlist_name"); yt_rename["playlist_name"] = "Playlist"
                if "popularity_raw" in yr_tracks.columns:
                    yt_cols.append("popularity_raw"); yt_rename["popularity_raw"] = "Popularity"
                if "duration_min" in yr_tracks.columns:
                    yr_tracks["_dur"] = yr_tracks["duration_min"].apply(
                        lambda x: fmt_duration(x) if pd.notna(x) else "—"
                    )
                    yt_cols.append("_dur"); yt_rename["_dur"] = "Duration"

                sort_yt = "popularity_raw" if "popularity_raw" in yr_tracks.columns else "track_name"
                yt_table = (
                    yr_tracks[yt_cols]
                    .rename(columns=yt_rename)
                    .sort_values(yt_rename[sort_yt], ascending=(sort_yt == "track_name"))
                    .reset_index(drop=True)
                )
                st.markdown(
                    f"<p style='color:#1DB954;font-weight:700;font-size:1rem;margin-bottom:4px;'>"
                    f"🎯 {len(yt_table)} track{'s' if len(yt_table) != 1 else ''} from {clicked_year}</p>",
                    unsafe_allow_html=True,
                )
                yt_col_config = {col: st.column_config.Column(width="auto") for col in yt_table.columns}
                st.dataframe(yt_table, use_container_width=True, hide_index=True, column_config=yt_col_config)

            # ── Artist: avg/oldest/newest/span stat card ──
            if not yr_vals.empty:
                avg_yr   = yr_vals.mean()
                oldest_y = int(yr_vals.min())
                newest_y = int(yr_vals.max())
                span_y   = newest_y - oldest_y
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown(
                    f'<div style="background:#282828;border-radius:12px;padding:16px 24px;'
                    f'display:flex;gap:40px;flex-wrap:wrap;">'
                    f'<div><div style="color:#B3B3B3;font-size:0.75rem;font-weight:600;'
                    f'text-transform:uppercase;letter-spacing:0.06em;">Avg Year</div>'
                    f'<div style="color:#FFFFFF;font-size:1.4rem;font-weight:800;">{avg_yr:.0f}</div></div>'
                    f'<div><div style="color:#B3B3B3;font-size:0.75rem;font-weight:600;'
                    f'text-transform:uppercase;letter-spacing:0.06em;">Oldest</div>'
                    f'<div style="color:#AAAAAA;font-size:1.4rem;font-weight:800;">{oldest_y}</div></div>'
                    f'<div><div style="color:#B3B3B3;font-size:0.75rem;font-weight:600;'
                    f'text-transform:uppercase;letter-spacing:0.06em;">Newest</div>'
                    f'<div style="color:#1DB954;font-size:1.4rem;font-weight:800;">{newest_y}</div></div>'
                    f'<div><div style="color:#B3B3B3;font-size:0.75rem;font-weight:600;'
                    f'text-transform:uppercase;letter-spacing:0.06em;">Span</div>'
                    f'<div style="color:#FFFFFF;font-size:1.4rem;font-weight:800;">{span_y} yrs</div></div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    else:
        # ── Album mode: single release year card ──
        st.markdown("### 📅 Release Year")
        if yr_vals.empty:
            st.info("No release year data available for this album.")
        else:
            album_year = int(yr_vals.mode().iloc[0])
            years_ago  = datetime.date.today().year - album_year
            ago_str    = f"{years_ago} years ago" if years_ago > 0 else "This year"
            st.markdown(
                f'<div style="background:#282828;border-radius:12px;padding:16px 24px;'
                f'display:flex;gap:40px;flex-wrap:wrap;">'
                f'<div><div style="color:#B3B3B3;font-size:0.75rem;font-weight:600;'
                f'text-transform:uppercase;letter-spacing:0.06em;">Released</div>'
                f'<div style="color:#1DB954;font-size:1.4rem;font-weight:800;">{album_year}</div></div>'
                f'<div><div style="color:#B3B3B3;font-size:0.75rem;font-weight:600;'
                f'text-transform:uppercase;letter-spacing:0.06em;">That was</div>'
                f'<div style="color:#FFFFFF;font-size:1.4rem;font-weight:800;">{ago_str}</div></div>'
                f'</div>',
                unsafe_allow_html=True,
            )