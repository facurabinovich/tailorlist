"""
4_Audio_DNA.py — Audio Feature Analysis
Sections:
  1. Mood Map (valence × energy scatter)
  2. Global Fingerprint (radar)
  3. Feature Distributions (histograms)
  4. Playlist Radar Comparison
  5. Correlation Heatmap
  6. Outlier Tracks
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from app_state.collection import get_tracks
from ui.theme import inject_global_css, spotify_icon_html, page_brand_html
from ui.nav import inject_sidebar_nav, check_collection_mode
from ui.charts import layout as _layout, playlist_color_map as _playlist_color_map, hex_to_rgb as _hex_to_rgb
from core.formatting import short_name as _short_name
from core import audio_dna as dna

# ── Data ───────────────────────────────────────────────────────────────────────
def get_data():
    df = get_tracks()
    if "added_at" in df.columns:
        df["added_at"] = pd.to_datetime(df["added_at"])
    return df

# ── Helpers ────────────────────────────────────────────────────────────────────
FEAT_LABELS = dna.FEATURE_LABELS

RADAR_FEATS = dna.RADAR_FEATURES

# ── Boilerplate ────────────────────────────────────────────────────────────────
inject_global_css()
inject_sidebar_nav("Audio DNA")
if not check_collection_mode():
    st.stop()

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown(page_brand_html(), unsafe_allow_html=True)
st.markdown(
    f"<div style='display:flex;align-items:center;gap:14px;margin-bottom:4px;'>"
    f"{spotify_icon_html(36)}"
    f"<h1 style='margin:0;font-size:1.9rem;color:#FFFFFF;'>Audio DNA</h1>"
    f"</div>"
    f"<p style='color:#B3B3B3;margin-top:0;font-size:0.9rem;margin-bottom:24px;'>"
    f"Deep dive into the sonic fingerprint of your collection — feature distributions, playlist comparisons, and mood mapping."
    f"</p>",
    unsafe_allow_html=True,
)

# ── Load ───────────────────────────────────────────────────────────────────────
with st.spinner("Loading audio data…"):
    df_all = get_data()

playlists = sorted(df_all["playlist_name"].unique())
pl_colors = _playlist_color_map(playlists)

# Unique counts via set operations on Spotify track IDs
_enrich = dna.enrichment_stats(
    st.session_state.get("uc_enriched", []),
    st.session_state.get("uc_skipped", []),
    st.session_state.get("uc_failed", []),
)
_n_unique_with_af  = _enrich.with_audio_features
_n_unique_without_af = _enrich.without_audio_features
_n_unique_total    = _enrich.total
_n_pl = df_all["playlist_name"].nunique() if not df_all.empty else 0
if _n_unique_without_af > 0:
    st.warning(
        f"🎵 **Your Collection** — {_n_unique_with_af} of {_n_unique_total} unique tracks across "
        f"{_n_pl} playlist(s) have audio features and appear in this analysis. "
        f"**{_n_unique_without_af} unique track(s) could not be enriched** (API lookup failed or track not found) "
        f"and are excluded from all charts."
    )
else:
    st.info(
        f"🎵 **Your Collection** — {_n_unique_with_af} unique tracks across {_n_pl} playlist(s) · "
        f"all tracks successfully enriched."
    )

# ── Global filter — drives ALL sections ───────────────────────────────────────
_pl_key = "global_filter_yc"
with st.expander("🎛️ Filter playlists", expanded=False):
    selected_pl = st.multiselect(
        "Select playlists",
        options=playlists,
        default=playlists,
        key=_pl_key,
    )

# All sections use these two frames
_sel   = dna.select_playlists(df_all, selected_pl)
df_flt = _sel.rows
df     = _sel.unique

if not dna.has_audio_data(df):
    st.info(
        "Audio features aren't available for any of these tracks — "
        "none were found in the audio database during enrichment."
    )
    st.stop()

# ── Feature legend ─────────────────────────────────────────────────────────────
with st.expander("📖 What do these features mean?", expanded=False):
    _FEAT_DESCRIPTIONS = [
        ("Energy",           "0 – 1", "#E8534A",
         "Perceptual intensity and activity. High energy = fast, loud, noisy (e.g. death metal). Low = slow and quiet."),
        ("Acousticness",     "0 – 1", "#4A90D9",
         "Confidence that the track is acoustic (no electronic processing). 1.0 = highly acoustic."),
        ("Valence",          "0 – 1", "#F5A623",
         "Musical positiveness. High = happy, cheerful, euphoric. Low = sad, depressed, angry."),
        ("Danceability",     "0 – 1", "#1DB954",
         "How suitable a track is for dancing based on tempo, rhythm stability, beat strength and regularity."),
        ("Speechiness",      "0 – 1", "#B97FE8",
         "Presence of spoken words. >0.66 = likely spoken word. 0.33–0.66 = music+speech. <0.33 = mostly music."),
        ("Instrumentalness", "0 – 1", "#4AE8D4",
         "Probability that the track has NO vocals. Values near 1.0 = purely instrumental. Near 0 = has singing."),
        ("Liveness",         "0 – 1", "#E8D44A",
         "Detects presence of a live audience. >0.8 = strong likelihood the track was recorded live."),
        ("Loudness",         "dB",    "#E8934A",
         "Overall loudness in decibels (dB), averaged across the track. Typical range: −60 to 0 dB."),
        ("Tempo",            "BPM",   "#7B9EA8",
         "Estimated tempo in beats per minute (BPM). The speed or pace of the track."),
    ]
    cols = st.columns(3)
    for i, (name, scale, color, desc) in enumerate(_FEAT_DESCRIPTIONS):
        cols[i % 3].markdown(f"""
        <div style='background:#1a1a1a;border-radius:10px;padding:12px 14px;border-left:3px solid {color};margin-bottom:10px;'>
          <div style='display:flex;align-items:center;gap:8px;margin-bottom:4px;'>
            <span style='font-size:0.85rem;font-weight:700;color:#FFFFFF;'>{name}</span>
            <span style='font-size:0.7rem;color:{color};background:rgba(255,255,255,0.06);padding:1px 6px;border-radius:4px;'>{scale}</span>
          </div>
          <div style='font-size:0.75rem;color:#B3B3B3;line-height:1.4;'>{desc}</div>
        </div>""", unsafe_allow_html=True)

st.markdown("<hr style='border-color:#333;margin-top:16px;margin-bottom:28px;'>", unsafe_allow_html=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 1 — MOOD MAP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.markdown("## Mood Map")
st.markdown("<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>Every track plotted by valence (happiness) vs energy. Size = popularity. Double-click a playlist in the legend to isolate it.</p>", unsafe_allow_html=True)

df_mood = df  # already deduped

fig_mood = go.Figure()

for x0, x1, y0, y1, color in [
    (0, 0.5, 0.5, 1.0, "rgba(231,76,60,0.06)"),
    (0.5, 1.0, 0.5, 1.0, "rgba(29,185,84,0.06)"),
    (0, 0.5, 0, 0.5, "rgba(100,100,200,0.06)"),
    (0.5, 1.0, 0, 0.5, "rgba(74,144,217,0.06)"),
]:
    fig_mood.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                       fillcolor=color, line_width=0)

for x, y, label in [
    (0.25, 0.93, "Turbulent"), (0.75, 0.93, "Happy"),
    (0.25, 0.07, "Dark"),      (0.75, 0.07, "Peaceful"),
]:
    fig_mood.add_annotation(
        x=x, y=y, text=label, showarrow=False,
        font=dict(color="#FFFFFF", size=11, family="Plus Jakarta Sans"),
        bgcolor="rgba(0,0,0,0.55)",
        bordercolor="rgba(255,255,255,0.08)",
        borderwidth=1,
        borderpad=4,
        xref="x", yref="y",
    )

fig_mood.add_shape(type="line", x0=0.5, x1=0.5, y0=0, y1=1,
                   line=dict(color="#333333", width=1, dash="dot"))
fig_mood.add_shape(type="line", x0=0, x1=1, y0=0.5, y1=0.5,
                   line=dict(color="#333333", width=1, dash="dot"))

for pl in sorted(selected_pl):
    sub = df_mood[df_mood["playlist_name"] == pl]
    if sub.empty:
        continue
    size = dna.marker_sizes(sub)
    has_pop = "popularity_raw" in sub.columns
    customdata = sub[["track_name", "playlist_name", "artist_display", "popularity_raw"]].values if has_pop else sub[["track_name", "playlist_name", "artist_display"]].assign(popularity_raw="N/A").values
    fig_mood.add_trace(go.Scatter(
        x=sub["valence"], y=sub["energy"],
        mode="markers", name=pl,
        marker=dict(color=pl_colors[pl], size=size, opacity=0.5, line=dict(width=0)),
        customdata=customdata,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "<span style='color:#1DB954'>%{customdata[1]}</span><br>"
            "%{customdata[2]}<br>"
            "Valence: %{x:.2f} · Energy: %{y:.2f}<br>"
            + ("Popularity: %{customdata[3]:.0f}" if has_pop else "Popularity: N/A")
            + "<extra></extra>"
        ),
    ))

fig_mood.update_layout(**_layout(
    height=500,
    margin=dict(t=30, b=50, l=50, r=20),
    xaxis=dict(title="Valence →  (Sad to Happy)", range=[0, 1], gridcolor="#1e1e1e", zeroline=False),
    yaxis=dict(title="Energy →", range=[0, 1], gridcolor="#1e1e1e", zeroline=False),
    legend=dict(bgcolor="#181818", bordercolor="#333", borderwidth=1,
                font=dict(size=11), itemsizing="constant", orientation="v", x=1.01, y=1,
                itemclick="toggle", itemdoubleclick="toggleothers"),
    showlegend=True,
))
st.plotly_chart(fig_mood, width='stretch')

_MOOD_EMOJI = {"Happy": "😄", "Turbulent": "⚡", "Peaceful": "🌊", "Dark": "🌑"}
cols = st.columns(4)
for col, q in zip(cols, dna.mood_summary(df_mood)):
    label = f"{q.name} {_MOOD_EMOJI[q.name]}"
    pct = q.pct
    col.markdown(f"""
    <div style='background:#282828;border-radius:14px;padding:16px 18px;border:1px solid #333;text-align:center;'>
      <div style='font-size:1.4rem;font-weight:700;color:#FFFFFF;'>{q.count}</div>
      <div style='font-size:0.78rem;color:#B3B3B3;margin-top:2px;'>{label}</div>
      <div style='font-size:0.72rem;color:#1DB954;margin-top:4px;'>{pct:.1f}% of tracks</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<hr style='border-color:#333;margin-top:32px;margin-bottom:32px;'>", unsafe_allow_html=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 2 — GLOBAL FINGERPRINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.markdown("## Global Fingerprint")
st.markdown("<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>The average sonic profile of the selected playlists — 7 normalized audio features.</p>", unsafe_allow_html=True)

radar_labels  = [FEAT_LABELS[f] for f in RADAR_FEATS]
global_means  = dna.feature_means(df)

fig_radar = go.Figure()
fig_radar.add_trace(go.Scatterpolar(
    r=global_means + [global_means[0]],
    theta=radar_labels + [radar_labels[0]],
    fill="toself",
    fillcolor="rgba(29,185,84,0.15)",
    line=dict(color="#1DB954", width=2),
    hovertemplate="%{theta}: %{r:.3f}<extra></extra>",
))
fig_radar.update_layout(**_layout(
    height=420,
    margin=dict(t=30, b=30, l=60, r=60),
    polar=dict(
        bgcolor="#181818",
        radialaxis=dict(visible=True, range=[0, 1], gridcolor="#333",
                        tickfont=dict(color="#B3B3B3", size=10), tickvals=[0.2, 0.4, 0.6, 0.8]),
        angularaxis=dict(gridcolor="#333", tickfont=dict(color="#FFFFFF", size=12)),
    ),
    showlegend=False,
))
st.plotly_chart(fig_radar, width='stretch')

pill_cols = st.columns(len(RADAR_FEATS))
for col, feat, val in zip(pill_cols, RADAR_FEATS, global_means):
    col.markdown(f"""
    <div style='background:#282828;border-radius:10px;padding:10px 8px;border:1px solid #333;text-align:center;'>
      <div style='font-size:1.1rem;font-weight:700;color:#1DB954;'>{val:.2f}</div>
      <div style='font-size:0.7rem;color:#B3B3B3;margin-top:2px;'>{FEAT_LABELS[feat]}</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<hr style='border-color:#333;margin-top:32px;margin-bottom:32px;'>", unsafe_allow_html=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 3 — FEATURE DISTRIBUTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.markdown("## Feature Distributions")
st.markdown("<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>How the selected tracks spread across each audio feature. Log scale applied to zero-heavy features.</p>", unsafe_allow_html=True)

dist_feats = dna.distribution_features(df)
rows = [dist_feats[i:i + 4] for i in range(0, len(dist_feats), 4)]

for row_feats in rows:
    cols = st.columns(len(row_feats))
    for col, feat in zip(cols, row_feats):
        vals = df[feat].dropna()
        hist = dna.feature_histogram(vals, feat)

        fig_h = go.Figure(go.Bar(
            x=hist.centers, y=hist.counts,
            marker=dict(color="#1DB954", line_width=0, opacity=0.85),
            hovertemplate="%{x:.3f}<br>Count: %{y}<extra></extra>",
        ))
        fig_h.update_layout(**_layout(
            height=180,
            margin=dict(t=24, b=10, l=10, r=10),
            xaxis=dict(showgrid=False, zeroline=False, tickfont=dict(size=9)),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            bargap=0.05,
        ))
        fig_h.add_annotation(
            text=FEAT_LABELS.get(feat, feat),
            x=0.5, y=1.0, xref="paper", yref="paper",
            showarrow=False, font=dict(size=11, color="#FFFFFF"),
            xanchor="center", yanchor="bottom",
        )
        col.plotly_chart(fig_h, width='stretch')

st.markdown("<hr style='border-color:#333;margin-top:32px;margin-bottom:32px;'>", unsafe_allow_html=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 4 — PLAYLIST RADAR COMPARISON
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.markdown("## Playlist Radar Comparison")
st.markdown("<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>One polygon per selected playlist — outlier playlists stand out immediately.</p>", unsafe_allow_html=True)

fig_prc = go.Figure()
for pl in sorted(selected_pl):
    sub = df_flt[df_flt["playlist_name"] == pl].drop_duplicates(subset="track_id")
    if sub.empty:
        continue
    means = dna.feature_means(sub)
    color = pl_colors[pl]
    r, g, b = _hex_to_rgb(color)
    fig_prc.add_trace(go.Scatterpolar(
        r=means + [means[0]],
        theta=radar_labels + [radar_labels[0]],
        fill="toself",
        fillcolor=f"rgba({r},{g},{b},0.07)",
        line=dict(color=f"rgba({r},{g},{b},0.85)", width=1.5),
        name=pl,
        hovertemplate=pl + " · %{theta}: %{r:.3f}<extra></extra>",
    ))

fig_prc.update_layout(**_layout(
    height=520,
    margin=dict(t=30, b=30, l=60, r=160),
    polar=dict(
        bgcolor="#181818",
        radialaxis=dict(visible=True, range=[0, 1], gridcolor="#2a2a2a",
                        tickfont=dict(color="#666", size=9), tickvals=[0.25, 0.5, 0.75]),
        angularaxis=dict(gridcolor="#2a2a2a", tickfont=dict(color="#FFFFFF", size=11)),
    ),
    legend=dict(bgcolor="#181818", bordercolor="#333", borderwidth=1,
                font=dict(size=10), orientation="v", x=1.02, y=1),
))
st.plotly_chart(fig_prc, width='stretch')

st.markdown("<hr style='border-color:#333;margin-top:32px;margin-bottom:32px;'>", unsafe_allow_html=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 5 — CORRELATION HEATMAP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.markdown("## Feature Correlation")
st.markdown("<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>Pearson correlation across all audio features for the selected playlists.</p>", unsafe_allow_html=True)

_corr_feats  = dna.correlation_features(df)
corr_matrix  = dna.correlation_matrix(df, _corr_feats)
feat_display = [FEAT_LABELS.get(f, f.capitalize()) for f in _corr_feats]

fig_heat = go.Figure(go.Heatmap(
    z=corr_matrix.values,
    x=feat_display, y=feat_display,
    colorscale=[[0.0, "#C0392B"], [0.5, "#1e1e1e"], [1.0, "#1DB954"]],
    zmin=-1, zmax=1,
    text=corr_matrix.values.round(2),
    texttemplate="%{text}",
    textfont=dict(size=11, color="#FFFFFF"),
    hovertemplate="<b>%{x}</b> × <b>%{y}</b><br>r = %{z:.2f}<extra></extra>",
    colorbar=dict(bgcolor="#181818", bordercolor="#333",
                  tickfont=dict(color="#B3B3B3"),
                  title=dict(text="r", font=dict(color="#B3B3B3"))),
))
fig_heat.update_layout(**_layout(
    height=480,
    margin=dict(t=20, b=80, l=100, r=20),
    xaxis=dict(tickangle=-35, tickfont=dict(size=11)),
    yaxis=dict(tickfont=dict(size=11)),
))
st.plotly_chart(fig_heat, width='stretch')

top_corr = dna.top_correlations(corr_matrix)

insight_cols = st.columns(3)
for col, (_, row) in zip(insight_cols, top_corr.iterrows()):
    color = "#1DB954" if row["r"] > 0 else "#E8534A"
    sign  = "+" if row["r"] > 0 else ""
    fa, fb = FEAT_LABELS.get(row["feat_a"], row["feat_a"]), FEAT_LABELS.get(row["feat_b"], row["feat_b"])
    col.markdown(f"""
    <div style='background:#282828;border-radius:14px;padding:16px 18px;border:1px solid #333;text-align:center;'>
      <div style='font-size:1.3rem;font-weight:700;color:{color};'>{sign}{row["r"]:.2f}</div>
      <div style='font-size:0.78rem;color:#FFFFFF;margin-top:4px;'>{fa} × {fb}</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<hr style='border-color:#333;margin-top:32px;margin-bottom:32px;'>", unsafe_allow_html=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 6 — EXTREME TRACKS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.markdown("## Extreme Tracks")
st.markdown("<p style='color:#B3B3B3;margin-top:-8px;font-size:0.85rem;'>The most extreme values for each audio feature within the selected playlists.</p>", unsafe_allow_html=True)

for feat, label in dna.EXTREME_FEATURES:
    if feat not in df.columns:
        continue
    top5, bot5 = dna.extreme_tracks(df, feat)

    st.markdown(f"**{label}**")
    left, right = st.columns(2)

    for col, subset, extremity, icon in [
        (left, top5, "Highest", "⬆"),
        (right, bot5, "Lowest", "⬇"),
    ]:
        cards_html = f"<div style='font-size:0.72rem;color:#1DB954;font-weight:600;margin-bottom:8px;letter-spacing:0.05em;'>{icon} {extremity}</div>"
        for _, row in subset.iterrows():
            val_display = dna.format_extreme_value(row[feat], feat)
            pl_color = pl_colors.get(row["playlist_name"], "#1DB954")
            r, g, b = _hex_to_rgb(pl_color)
            cards_html += f"""
            <div style='background:#282828;border-radius:10px;padding:10px 14px;border:1px solid #333;margin-bottom:6px;display:flex;align-items:center;gap:12px;'>
              <div style='background:rgba({r},{g},{b},0.18);border-radius:8px;padding:6px 10px;min-width:54px;text-align:center;'>
                <span style='font-size:1.0rem;font-weight:700;color:{pl_color};'>{val_display}</span>
              </div>
              <div>
                <div style='font-size:0.82rem;font-weight:600;color:#FFFFFF;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:220px;'>{_short_name(row["track_name"])}</div>
                <div style='font-size:0.72rem;color:#B3B3B3;margin-top:2px;'>{_short_name(row["artist_display"], 18)} · <span style='color:{pl_color};'>{row["playlist_name"]}</span></div>
              </div>
            </div>"""
        col.markdown(cards_html, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom:20px;'></div>", unsafe_allow_html=True)