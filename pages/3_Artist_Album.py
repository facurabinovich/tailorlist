import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import datetime

from ui.theme import inject_global_css, spotify_icon_html, page_brand_html
from ui.nav import inject_sidebar_nav, check_collection_mode
from core import artist_album as aa
from core.formatting import fmt_duration
from app_state.collection import get_all_tracks

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

def genre_pills_html(genres_series: pd.Series) -> str:
    """Build HTML genre pill string from a column of comma-separated genres."""
    top = aa.top_genre_tags(genres_series)
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
MIN_TRACKS_ARTIST = aa.MIN_TRACKS_ARTIST
MIN_TRACKS_ALBUM = aa.MIN_TRACKS_ALBUM

if is_artist_mode:
    choices = aa.artist_choices(df)
    if not choices.options_raw:
        st.info(
            f"No artists meet the minimum track threshold yet. "
            "Try adding more playlists to your collection."
        )
        st.stop()
    label = "Select an artist"
    threshold_note = (
        f"Only artists with {MIN_TRACKS_ARTIST}+ tracks in your collection are shown. "
        "Add more playlists to unlock more artists."
    )
else:
    choices = aa.album_choices(df)
    if choices is None:
        st.warning("Album data is not available in your collection.")
        st.stop()
    if not choices.options_raw:
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
options_raw = choices.options_raw
options = choices.options

_pinned = st.session_state.get("_pinned_selection")
default_index = aa.default_option_index(choices, None if is_artist_mode else _pinned)

st.caption(f"ℹ️ {threshold_note}")

selected_display = st.selectbox(label, options=options, index=default_index, label_visibility="visible")
selected = options_raw[options.index(selected_display)]

# ── Filter df to selection ────────────────────────────────────────────────────
if is_artist_mode:
    sel_df = aa.artist_rows(df, selected)
else:
    # Resolve back to album_name + artist_name from the pair lookup
    pair_album, pair_artist = aa.album_pair(choices, selected)
    sel_df = aa.album_rows(df, pair_album, pair_artist)

kpis = aa.selection_kpis(sel_df, MIN_TRACKS_ARTIST if is_artist_mode else MIN_TRACKS_ALBUM)
track_count = kpis.track_count
playlist_count = kpis.playlist_count
enough = kpis.enough

# ── Header card ───────────────────────────────────────────────────────────────
display_name = selected if is_artist_mode else f"{pair_album} · {pair_artist}"
genre_html = ""
if is_artist_mode and aa.selection_genres(sel_df):
    genre_html = genre_pills_html(sel_df["artist_genres"])

st.markdown(header_card_html(display_name, track_count, playlist_count, genre_html),
            unsafe_allow_html=True)

st.markdown("<hr style='border-color:#282828;margin:16px 0;'>", unsafe_allow_html=True)

# ── Tracks table ──────────────────────────────────────────────────────────────
st.markdown("### 🎵 Tracks")
st.caption("Sorted by popularity — most streamed tracks first. The same track may appear more than once if you saved it across multiple playlists.")

table_df = aa.track_table(sel_df, include_album=is_artist_mode)

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

    album_counts = aa.album_breakdown(sel_df)

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
    named_albums = aa.deep_dive_albums(album_counts)

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

ext = aa.track_extremes(sel_df, include_years=is_artist_mode)

# Duration extremes
if ext.longest is not None:
    longest, shortest = ext.longest, ext.shortest
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
if ext.most_popular is not None:
    most_pop, least_pop = ext.most_popular, ext.least_popular
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
if ext.oldest is not None:
    oldest, newest = ext.oldest, ext.newest
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

    pl_counts = aa.playlist_distribution(sel_df)

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
        pl_table = aa.track_table(pl_tracks, include_album=is_artist_mode, include_playlist=False)

        st.markdown(
            f"<p style='color:#1DB954;font-weight:700;font-size:1rem;margin-bottom:4px;'>"
            f"🎯 {len(pl_table)} track{'s' if len(pl_table) != 1 else ''} in <b>{clicked_playlist}</b></p>",
            unsafe_allow_html=True,
        )
        pl_col_config = {col: st.column_config.Column(width="auto") for col in pl_table.columns}
        st.dataframe(pl_table, use_container_width=True, hide_index=True, column_config=pl_col_config)

    st.markdown("<hr style='border-color:#282828;margin:16px 0;'>", unsafe_allow_html=True)

# ── Audio fingerprint (radar) ─────────────────────────────────────────────────
radar = aa.audio_radar(sel_df, df)
available_radar = radar.features
n_enriched = radar.n_enriched

if len(available_radar) >= 3:
    st.markdown("### 🎛️ Audio Fingerprint")

    if not enough:
        st.info("Not enough tracks to show audio analysis — add more playlists to get richer insights.")
    elif n_enriched == 0:
        st.info(
            "Audio features aren't available for these tracks — "
            "they weren't found in the audio database during enrichment."
        )
    else:
        if n_enriched < len(sel_df):
            st.caption(f"ℹ️ Based on {n_enriched} of {len(sel_df)} tracks — the rest haven't been enriched yet.")
        hover_texts = [
            f"{f.capitalize()}: {m:.2f}" for f, m in zip(available_radar, radar.feature_means)
        ]
        if radar.mean_tempo_bpm is not None:
            hover_texts = hover_texts + [f"Tempo: {radar.mean_tempo_bpm:.0f} BPM"]

        # Close the polygon
        radar_labels_closed = radar.axis_labels + [radar.axis_labels[0]]
        radar_values_closed = radar.axis_values + [radar.axis_values[0]]
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
        BIN_SIZE = aa.POPULARITY_BIN_SIZE
        pop_dist = aa.popularity_distribution(sel_df)
        nz_labels = pop_dist.bin_labels
        nz_counts = pop_dist.counts
        nz_bins   = pop_dist.bin_starts

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
            pop_tracks = aa.popularity_bin_tracks(sel_df, bin_min)
            pt_table = aa.track_table(pop_tracks, include_album=is_artist_mode)

            st.markdown(
                f"<p style='color:#1DB954;font-weight:700;font-size:1rem;margin-bottom:4px;'>"
                f"🎯 {len(pt_table)} track{'s' if len(pt_table) != 1 else ''} "
                f"— popularity {bin_min}–{bin_max - 1}</p>",
                unsafe_allow_html=True,
            )
            pt_col_config = {col: st.column_config.Column(width="auto") for col in pt_table.columns}
            st.dataframe(pt_table, use_container_width=True, hide_index=True, column_config=pt_col_config)

        # ── Popularity avg stat card ──
        avg_pop  = pop_dist.average
        med_pop  = pop_dist.median
        max_pop  = pop_dist.highest
        min_pop  = pop_dist.lowest
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
    if is_artist_mode:
        # ── Full timeline chart with click drill-down ──
        st.markdown("### 📅 Release Timeline")
        st.markdown(
            "<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>"
            "Click a bar to see the tracks from that year.</p>",
            unsafe_allow_html=True,
        )

        year_counts = aa.release_year_counts(sel_df)

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

                yt_table = aa.track_table(yr_tracks, include_album=True, include_year=False)
                st.markdown(
                    f"<p style='color:#1DB954;font-weight:700;font-size:1rem;margin-bottom:4px;'>"
                    f"🎯 {len(yt_table)} track{'s' if len(yt_table) != 1 else ''} from {clicked_year}</p>",
                    unsafe_allow_html=True,
                )
                yt_col_config = {col: st.column_config.Column(width="auto") for col in yt_table.columns}
                st.dataframe(yt_table, use_container_width=True, hide_index=True, column_config=yt_col_config)

            # ── Artist: avg/oldest/newest/span stat card ──
            yr_sum = aa.year_summary(sel_df)
            if yr_sum is not None:
                avg_yr   = yr_sum.average
                oldest_y = yr_sum.oldest
                newest_y = yr_sum.newest
                span_y   = yr_sum.span
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
        album_rel = aa.album_release(sel_df, datetime.date.today().year)
        if album_rel is None:
            st.info("No release year data available for this album.")
        else:
            album_year = album_rel.year
            years_ago  = album_rel.years_ago
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