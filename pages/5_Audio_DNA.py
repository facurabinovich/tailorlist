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
import numpy as np
import plotly.graph_objects as go

from db.queries import get_tracks
from config import NORMALIZED_FEATURES, AUDIO_FEATURES
from utils import inject_global_css, inject_sidebar_nav, check_collection_mode, spotify_icon_html, page_brand_html

# ── Layout base ────────────────────────────────────────────────────────────────
_BL = dict(
    plot_bgcolor="#121212",
    paper_bgcolor="#121212",
    font_color="#B3B3B3",
    margin=dict(t=20, b=20, l=10, r=10),
)

def _layout(**overrides):
    return {**_BL, **overrides}

_PL_PALETTE = [
    "#1DB954", "#E8534A", "#4A90D9", "#F5A623", "#B97FE8",
    "#E8D44A", "#4AE8D4", "#E84A90", "#A8E84A", "#E8934A",
    "#7B9EA8", "#C0392B", "#8E44AD", "#2ECC71",
]

# ── Data ───────────────────────────────────────────────────────────────────────
def get_data():
    df = get_tracks()
    if "added_at" in df.columns:
        df["added_at"] = pd.to_datetime(df["added_at"])
    return df

# ── Helpers ────────────────────────────────────────────────────────────────────
def _playlist_color_map(playlists):
    return {pl: _PL_PALETTE[i % len(_PL_PALETTE)] for i, pl in enumerate(sorted(playlists))}

def _short_name(name: str, max_len: int = 22) -> str:
    return name if len(name) <= max_len else name[:max_len - 1] + "…"

def _hex_to_rgb(hex_color: str):
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

FEAT_LABELS = {
    "energy": "Energy", "acousticness": "Acousticness", "valence": "Valence",
    "danceability": "Danceability", "speechiness": "Speechiness",
    "instrumentalness": "Instrumentalness", "liveness": "Liveness",
    "loudness": "Loudness", "tempo": "Tempo",
}

RADAR_FEATS = ["energy", "acousticness", "valence", "danceability",
               "speechiness", "instrumentalness", "liveness"]

# ── Boilerplate ────────────────────────────────────────────────────────────────
inject_global_css()
inject_sidebar_nav("Audio DNA")
if not check_collection_mode():
    st.stop()

# Clear playlist filter when mode switches so stale keys don't corrupt the multiselect
_current_mode = st.session_state.get("mode", "🎵 Demo Collection")
if st.session_state.get("_audio_dna_mode") != _current_mode:
    st.session_state["_audio_dna_mode"] = _current_mode
    st.session_state.pop("global_filter_fc", None)
    st.session_state.pop("global_filter_yc", None)

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

is_yc = st.session_state.get("mode") == "🔗 Your Collection"
if is_yc:
    # Unique counts via set operations on Spotify track IDs
    _enriched_ids_dna = {t["id"] for t in st.session_state.get("uc_enriched", []) if t.get("id")}
    _unenriched_dna   = st.session_state.get("uc_skipped", []) + st.session_state.get("uc_failed", [])
    _unenriched_unique_dna = {t["id"] for t in _unenriched_dna if t.get("id")} - _enriched_ids_dna
    _n_unique_with_af  = len(_enriched_ids_dna)
    _n_unique_without_af = len(_unenriched_unique_dna)
    _n_unique_total    = _n_unique_with_af + _n_unique_without_af
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
_pl_key = "global_filter_yc" if _current_mode == "🔗 Your Collection" else "global_filter_fc"
with st.expander("🎛️ Filter playlists", expanded=False):
    selected_pl = st.multiselect(
        "Select playlists",
        options=playlists,
        default=playlists,
        key=_pl_key,
    )

# All sections use these two frames
df_flt = df_all[df_all["playlist_name"].isin(selected_pl)]
df     = df_flt.drop_duplicates(subset="track_id")

_has_audio_data = any(f in df.columns and df[f].notna().any() for f in RADAR_FEATS)
if not _has_audio_data:
    if is_yc:
        st.info(
            "Audio features aren't available for any of these tracks — "
            "none were found in the audio database during enrichment."
        )
    else:
        st.info("No audio feature data found for this collection.")
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
    size = (sub["popularity_raw"].astype(float).fillna(0.0) / 100 * 8 + 3).tolist() if "popularity_raw" in sub.columns else [6] * len(sub)
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

q_data = {
    "Happy 😄":     df_mood[(df_mood["valence"] >= 0.5) & (df_mood["energy"] >= 0.5)],
    "Turbulent ⚡": df_mood[(df_mood["valence"] < 0.5)  & (df_mood["energy"] >= 0.5)],
    "Peaceful 🌊":  df_mood[(df_mood["valence"] >= 0.5) & (df_mood["energy"] < 0.5)],
    "Dark 🌑":      df_mood[(df_mood["valence"] < 0.5)  & (df_mood["energy"] < 0.5)],
}
cols = st.columns(4)
for col, (label, sub) in zip(cols, q_data.items()):
    pct = len(sub) / len(df_mood) * 100 if len(df_mood) else 0
    col.markdown(f"""
    <div style='background:#282828;border-radius:14px;padding:16px 18px;border:1px solid #333;text-align:center;'>
      <div style='font-size:1.4rem;font-weight:700;color:#FFFFFF;'>{len(sub)}</div>
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
global_means  = [df[f].mean() for f in RADAR_FEATS]

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

dist_feats = [f for f in NORMALIZED_FEATURES + ["tempo"] if f in df.columns]
rows = [dist_feats[i:i + 4] for i in range(0, len(dist_feats), 4)]

for row_feats in rows:
    cols = st.columns(len(row_feats))
    for col, feat in zip(cols, row_feats):
        vals = df[feat].dropna()
        is_log = feat in ("instrumentalness", "speechiness")
        if is_log and (vals > 0).sum() > 10:
            log_vals = np.log10(vals[vals > 0] + 1e-4)
            bins = np.linspace(log_vals.min(), log_vals.max(), 30)
            hist_vals, bin_edges = np.histogram(log_vals, bins=bins)
        else:
            hist_vals, bin_edges = np.histogram(vals, bins=30)
        x_centers = [(bin_edges[i] + bin_edges[i + 1]) / 2 for i in range(len(bin_edges) - 1)]

        fig_h = go.Figure(go.Bar(
            x=x_centers, y=hist_vals,
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
    means = [sub[f].mean() for f in RADAR_FEATS]
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

_corr_feats  = [f for f in AUDIO_FEATURES if f in df.columns]
corr_matrix  = df[_corr_feats].dropna().corr(method="pearson").round(2)
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

corr_flat = (
    corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
    .stack().reset_index()
)
corr_flat.columns = ["feat_a", "feat_b", "r"]
top_corr = corr_flat.assign(abs_r=corr_flat["r"].abs()).sort_values("abs_r", ascending=False).head(3)

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

outlier_feats = [
    ("energy",           "Energy"),
    ("acousticness",     "Acousticness"),
    ("valence",          "Valence"),
    ("danceability",     "Danceability"),
    ("instrumentalness", "Instrumentalness"),
    ("liveness",         "Liveness"),
    ("loudness",         "Loudness (dB)"),
    ("tempo",            "Tempo (BPM)"),
    ("speechiness",      "Speechiness"),
]

for feat, label in outlier_feats:
    if feat not in df.columns:
        continue
    top5 = df.nlargest(5, feat)[["track_name", "artist_display", "playlist_name", feat]]
    if feat in ("instrumentalness", "speechiness"):
        non_zero = df[df[feat] > 0]
        bot5 = (non_zero.nsmallest(5, feat) if len(non_zero) >= 5 else df.nsmallest(5, feat))[
            ["track_name", "artist_display", "playlist_name", feat]
        ]
    else:
        bot5 = df.nsmallest(5, feat)[["track_name", "artist_display", "playlist_name", feat]]

    st.markdown(f"**{label}**")
    left, right = st.columns(2)

    for col, subset, extremity, icon in [
        (left, top5, "Highest", "⬆"),
        (right, bot5, "Lowest", "⬇"),
    ]:
        cards_html = f"<div style='font-size:0.72rem;color:#1DB954;font-weight:600;margin-bottom:8px;letter-spacing:0.05em;'>{icon} {extremity}</div>"
        for _, row in subset.iterrows():
            if feat == "tempo":
                val_display = f"{row[feat]:.1f}"
            elif feat == "loudness":
                val_display = f"{row[feat]:.1f}"
            elif feat in ("instrumentalness", "speechiness"):
                val_display = f"{row[feat]:.4f}"
            else:
                val_display = f"{row[feat]:.3f}"
            if val_display in ("0.000", "0.0000", "0.0001"):
                val_display = "< 0.001"
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