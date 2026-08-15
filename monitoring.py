"""
TailorList — local monitoring dashboard.
Run with:  streamlit run monitoring.py
"""

import os
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from dotenv import load_dotenv

load_dotenv()
os.environ["DEV_MODE"] = "0"  # monitoring always reads production DB

st.set_page_config(
    page_title="TailorList Monitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
/* ── Base ───────────────────────────────────────────────────── */
[data-testid="stAppViewContainer"],
[data-testid="stHeader"],
[data-testid="stSidebar"] { background: #0d0d0d; }
[data-testid="block-container"] { padding: 2rem 3rem 4rem; max-width: 1400px; }
footer, #MainMenu { display: none; }
[data-testid="stExpander"] { background: #111; border: 1px solid #222 !important; border-radius: 10px !important; }

/* ── KPI cards ──────────────────────────────────────────────── */
.kpi { background:#111; border:1px solid #222; border-radius:14px;
       padding:20px 22px 18px; position:relative; overflow:hidden; height:100%; }
.kpi::before { content:''; position:absolute; top:0; left:0; right:0;
               height:2px; background:var(--kpi-accent,#333); }
.kpi-icon  { font-size:1.3rem; margin-bottom:10px; line-height:1; }
.kpi-label { color:#555; font-size:0.68rem; letter-spacing:.1em;
             text-transform:uppercase; font-weight:700; }
.kpi-val   { color:#fff; font-size:2.4rem; font-weight:900;
             line-height:1; margin:6px 0 5px; }
.kpi-sub   { color:#444; font-size:0.72rem; }
.kpi-live  { color:#1DB954 !important; }

/* Pulse dot for "active now" */
@keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.5;transform:scale(.85)} }
.dot-live { display:inline-block; width:7px; height:7px; border-radius:50%;
            background:#1DB954; margin-right:5px; animation:pulse 1.8s ease-in-out infinite; }

/* ── Section headers ────────────────────────────────────────── */
.sec { display:flex; align-items:center; gap:10px; margin:0 0 18px; }
.sec-dot { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
.sec-label { color:#fff; font-size:1rem; font-weight:700; }
.sec-cap { color:#444; font-size:0.78rem; margin-left:auto; }

/* ── Conversion rate chips ──────────────────────────────────── */
.conv { background:#111; border:1px solid #222; border-radius:10px;
        padding:14px 18px; text-align:center; }
.conv-solo { border-style:dashed; }
.conv-arrow { color:#666; font-size:0.72rem; margin-bottom:6px; line-height:1.3; }
.conv-pct { color:#fff; font-size:1.5rem; font-weight:800; }
.conv-abs { color:#444; font-size:0.72rem; margin-top:3px; }
.conv-label { color:#555; font-size:0.65rem; letter-spacing:.08em;
              text-transform:uppercase; font-weight:700; margin-bottom:2px; }

/* ── Feed table ─────────────────────────────────────────────── */
[data-testid="stDataFrame"] { background: #111 !important; }

/* ── Divider ────────────────────────────────────────────────── */
.div { border:none; border-top:1px solid #1a1a1a; margin:32px 0; }

/* ── Empty state ────────────────────────────────────────────── */
.empty { text-align:center; padding:40px 20px; color:#333;
         border:1px dashed #1e1e1e; border-radius:12px; font-size:0.85rem; }
</style>
""", unsafe_allow_html=True)


# ── DB helpers ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def _q(sql: str) -> pd.DataFrame:
    try:
        from db.connection import get_engine
        with get_engine().connect() as conn:
            return pd.read_sql(sql, conn)
    except Exception as exc:
        return pd.DataFrame({"_error": [str(exc)]})

def _scalar(sql: str, default=0):
    df = _q(sql)
    if df.empty or "_error" in df.columns:
        return default
    return df.iloc[0, 0] or default

def _ok(df: pd.DataFrame) -> bool:
    return not df.empty and "_error" not in df.columns


# ── Chart base ────────────────────────────────────────────────────────────────
_B = dict(
    plot_bgcolor="#0d0d0d", paper_bgcolor="#111",
    font_color="#666",
    margin=dict(t=36, b=28, l=8, r=8),
)

def _ax(color="#222"):
    return dict(gridcolor=color, zeroline=False, linecolor="#1a1a1a",
                tickfont=dict(color="#555", size=11))

def _empty(msg="No data yet"):
    st.markdown(f"<div class='empty'>— {msg} —</div>", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────
def kpi(icon, label, value, sub="", accent="#333", live=False):
    val_cls = "kpi-val kpi-live" if live else "kpi-val"
    pulse   = "<span class='dot-live'></span>" if live and int(str(value) or 0) > 0 else ""
    return (
        f"<div class='kpi' style='--kpi-accent:{accent}'>"
        f"<div class='kpi-icon'>{icon}</div>"
        f"<div class='kpi-label'>{label}</div>"
        f"<div class='{val_cls}'>{pulse}{value}</div>"
        f"<div class='kpi-sub'>{sub}</div>"
        f"</div>"
    )

def section(label, dot_color="#1DB954", caption=""):
    cap = f"<span class='sec-cap'>{caption}</span>" if caption else ""
    st.markdown(
        f"<div class='sec'>"
        f"<span class='sec-dot' style='background:{dot_color}'></span>"
        f"<span class='sec-label'>{label}</span>{cap}"
        f"</div>",
        unsafe_allow_html=True,
    )

def div():
    st.markdown("<hr class='div'>", unsafe_allow_html=True)


# ── Header ────────────────────────────────────────────────────────────────────
h1, h2, h3 = st.columns([7, 2, 1])
with h1:
    st.markdown(
        "<h2 style='margin:0;color:#fff;font-weight:900;letter-spacing:-.02em;'>"
        "TailorList <span style='color:#1DB954;'>Monitor</span></h2>",
        unsafe_allow_html=True,
    )
with h2:
    st.markdown(
        f"<p style='color:#333;font-size:0.78rem;margin:12px 0 0;text-align:right;'>"
        f"auto-refresh 60s &nbsp;·&nbsp; {pd.Timestamp.now().strftime('%H:%M:%S')}</p>",
        unsafe_allow_html=True,
    )
with h3:
    if st.button("↺ Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.components.v1.html(
    "<script>setTimeout(()=>window.parent.location.reload(),60000)</script>",
    height=0,
)

div()

# ── Section 1 — Live KPIs ─────────────────────────────────────────────────────
section("Live", "#1DB954",
        caption="visitor ids are per-browser from 2026-08-15 on · earlier rows were per-session")

active_now   = _scalar("SELECT COUNT(DISTINCT visitor_id) FROM app_analytics WHERE created_at > NOW() - INTERVAL 10 MINUTE AND visitor_id IS NOT NULL")
active_today = _scalar("SELECT COUNT(DISTINCT visitor_id) FROM app_analytics WHERE DATE(created_at) = CURDATE() AND visitor_id IS NOT NULL")
visits_week  = _scalar("SELECT COUNT(DISTINCT visitor_id) FROM app_analytics WHERE event='site_visit' AND created_at > NOW() - INTERVAL 7 DAY AND visitor_id IS NOT NULL")
total_visits = _scalar("SELECT COUNT(DISTINCT visitor_id) FROM app_analytics WHERE event='site_visit' AND visitor_id IS NOT NULL")
total_yc     = _scalar("SELECT COUNT(*) FROM uc_sessions")
active_yc    = _scalar("SELECT COUNT(*) FROM uc_sessions WHERE last_seen_at > NOW() - INTERVAL 7 DAY OR (last_seen_at IS NULL AND created_at > NOW() - INTERVAL 7 DAY)")
# Returned visitors — only meaningful for traffic after the persistent-visitor-id
# fix (before it, visitor_id was regenerated on every page load, so this was
# structurally 0). The YC-session count below is the pre-fix-proof signal.
returned     = _scalar("""
    SELECT COUNT(*) FROM (
        SELECT visitor_id FROM app_analytics
        WHERE event='site_visit' AND visitor_id IS NOT NULL
        GROUP BY visitor_id HAVING COUNT(DISTINCT DATE(created_at)) >= 2
    ) t
""")
returned_yc  = _scalar("""
    SELECT COUNT(*) FROM (
        SELECT session_id FROM app_analytics
        WHERE session_id IS NOT NULL AND session_id <> 'fc_user'
        GROUP BY session_id HAVING COUNT(DISTINCT DATE(created_at)) >= 2
    ) t
""")

c1, c2, c3, c4, c5, c6 = st.columns(6)
for col, args in zip([c1,c2,c3,c4,c5,c6], [
    ("🟢", "Active now",       str(active_now),   "last 10 min",         "#1DB954", bool(active_now)),
    ("👤", "Active today",     str(active_today),  "unique sessions",     "#4A90D9", False),
    ("📅", "This week",        str(visits_week),   "unique visitors",     "#4A90D9", False),
    ("🌍", "All-time visitors",str(total_visits),  "since launch",        "#B97FE8", False),
    ("🔗", "YC users",         str(total_yc),      "completed enrichment","#F5A623", False),
    ("✨", "YC active 7d",     str(active_yc),     "seen in last 7 days", "#E8534A", False),
]):
    col.markdown(kpi(*args), unsafe_allow_html=True)

r1, r2, _ = st.columns([1, 1, 4])
r1.markdown(kpi("🔁", "Returned visitors", str(returned),
                "same browser, 2+ different days", "#1DB954"), unsafe_allow_html=True)
r2.markdown(kpi("🔗", "Returned YC sessions", str(returned_yc),
                "same collection link, 2+ days", "#B97FE8"), unsafe_allow_html=True)

div()

# ── Section 2 — Funnel ────────────────────────────────────────────────────────
section("Conversion Funnel", "#4A90D9")

funnel_df = _q("""
    SELECT event, COUNT(DISTINCT visitor_id) AS users
    FROM app_analytics WHERE visitor_id IS NOT NULL
    GROUP BY event
""")

_FUNNEL = [
    ("site_visit",          "Visited",            "#1DB954"),
    ("enrichment_start",    "Started enrichment", "#4A90D9"),
    ("enrichment_complete", "Enriched",           "#B97FE8"),
    ("clustering_run",      "Clustered",          "#F5A623"),
    ("export_download",     "Exported CSV",       "#E8534A"),
    ("mark_done_click",     "Marked done",        "#8FBF7A"),
]

if _ok(funnel_df):
    fmap = dict(zip(funnel_df["event"], funnel_df["users"]))
    rows = [(lbl, fmap.get(ev, 0), clr) for ev, lbl, clr in _FUNNEL]

    fcol, ccol = st.columns([2, 3])
    with fcol:
        fig_f = go.Figure(go.Funnel(
            y=[r[0] for r in rows],
            x=[r[1] for r in rows],
            textposition="inside",
            textinfo="value+percent initial",
            textfont=dict(color="#fff", size=12),
            marker=dict(color=[r[2] for r in rows]),
            connector=dict(line=dict(color="#1a1a1a", width=2)),
        ))
        fig_f.update_layout(
            **{**_B, "margin": dict(t=10, b=10, l=130, r=20)},
            height=290,
        )
        st.plotly_chart(fig_f, use_container_width=True)

    with ccol:
        # First 3 stages are the real-user funnel (enrichment path)
        # The rest are also reachable via demo, so show as % of visitors
        seq        = rows[:3]   # Visited, Started enrichment, Enriched
        standalone = rows[3:]   # Clustered, Exported CSV, Marked done
        v_visited  = rows[0][1]

        chip_cols = st.columns(2 + len(standalone))

        # Sequential step-to-step chips
        for ci in range(len(seq) - 1):
            lbl_from, v_from, _ = seq[ci]
            lbl_to,   v_to,   clr = seq[ci + 1]
            pct = v_to / v_from * 100 if v_from else 0
            chip_cols[ci].markdown(
                f"<div class='conv'>"
                f"<div class='conv-arrow'>{lbl_from}<br>↓<br>{lbl_to}</div>"
                f"<div class='conv-pct' style='color:{clr}'>{pct:.0f}%</div>"
                f"<div class='conv-abs'>{v_to} of {v_from}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Standalone % of all visitors (demo + real users merged)
        for si, (lbl, val, clr) in enumerate(standalone):
            pct = val / v_visited * 100 if v_visited else 0
            chip_cols[2 + si].markdown(
                f"<div class='conv conv-solo'>"
                f"<div class='conv-label'>% of visitors</div>"
                f"<div class='conv-arrow'>{lbl}</div>"
                f"<div class='conv-pct' style='color:{clr}'>{pct:.0f}%</div>"
                f"<div class='conv-abs'>{val} of {v_visited}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
else:
    _empty("No funnel data yet")

div()

# ── Section 3 — Traffic + Feature usage ──────────────────────────────────────
section("Traffic & Features", "#B97FE8")

tcol, ucol = st.columns(2, gap="large")

with tcol:
    daily_df = _q("""
        SELECT DATE(created_at) AS day, COUNT(DISTINCT visitor_id) AS sessions
        FROM app_analytics
        WHERE event='site_visit' AND created_at > NOW() - INTERVAL 30 DAY
          AND visitor_id IS NOT NULL
        GROUP BY day ORDER BY day
    """)
    if _ok(daily_df) and len(daily_df):
        fig_d = go.Figure(go.Bar(
            x=daily_df["day"], y=daily_df["sessions"],
            marker=dict(
                color="#1DB954",
                opacity=0.85,
                line=dict(width=0),
            ),
            hovertemplate="%{x}<br><b>%{y} sessions</b><extra></extra>",
        ))
        fig_d.update_layout(
            **{**_B, "margin": dict(t=36, b=28, l=40, r=8)},
            height=260,
            title=dict(text="Daily visitors — last 30 days",
                       font=dict(color="#aaa", size=12), x=0),
            xaxis={**_ax(), "tickformat": "%b %d"},
            yaxis={**_ax(), "tickformat": "d"},
            bargap=0.3,
        )
        st.plotly_chart(fig_d, use_container_width=True)
    else:
        _empty("No traffic data yet")

with ucol:
    mode_df = _q("""
        SELECT
            COALESCE(JSON_UNQUOTE(JSON_EXTRACT(properties,'$.mode')),'Unknown') AS mode,
            COUNT(*) AS runs,
            ROUND(AVG(CAST(JSON_EXTRACT(properties,'$.k') AS UNSIGNED)),1) AS avg_k,
            ROUND(AVG(CAST(JSON_EXTRACT(properties,'$.n_tracks') AS UNSIGNED)),0) AS avg_tracks
        FROM app_analytics
        WHERE event='clustering_run' AND properties IS NOT NULL
        GROUP BY mode ORDER BY runs DESC
    """)
    if _ok(mode_df) and len(mode_df):
        _clrs = {"KMeans": "#1DB954", "By category": "#4A90D9",
                 "By specific genre": "#B97FE8"}
        fig_m = go.Figure()
        for _, row in mode_df.iterrows():
            fig_m.add_trace(go.Bar(
                name=row["mode"],
                x=[row["mode"]], y=[row["runs"]],
                marker_color=_clrs.get(row["mode"], "#888"),
                text=[str(int(row["runs"]))],
                textposition="outside",
                textfont=dict(color="#aaa", size=11),
                hovertemplate=f"<b>{row['mode']}</b><br>%{{y}} runs<extra></extra>",
            ))
        fig_m.update_layout(
            **{**_B, "margin": dict(t=36, b=28, l=40, r=8)},
            height=260,
            showlegend=False,
            title=dict(text="Clustering runs by mode",
                       font=dict(color="#aaa", size=12), x=0),
            xaxis={**_ax(), "tickfont": dict(color="#aaa", size=11)},
            yaxis={**_ax(), "tickformat": "d"},
            bargap=0.5,
        )
        st.plotly_chart(fig_m, use_container_width=True)

        # Mini stats per mode
        mc = st.columns(len(mode_df))
        for ci, (_, mrow) in enumerate(mode_df.iterrows()):
            clr = _clrs.get(mrow["mode"], "#888")
            mc[ci].markdown(
                f"<div style='background:#111;border:1px solid #1e1e1e;border-left:2px solid {clr};"
                f"border-radius:8px;padding:10px 14px;'>"
                f"<div style='color:#555;font-size:0.68rem;letter-spacing:.06em;text-transform:uppercase'>{mrow['mode']}</div>"
                f"<div style='color:#aaa;font-size:0.78rem;margin-top:4px;'>"
                f"avg k <b style='color:#fff'>{mrow['avg_k'] or '—'}</b> &nbsp;·&nbsp; "
                f"avg <b style='color:#fff'>{int(mrow['avg_tracks'] or 0)}</b> tracks"
                f"</div></div>",
                unsafe_allow_html=True,
            )
    else:
        _empty("No clustering runs yet")

div()

# ── Section 4 — Pages + YC users ─────────────────────────────────────────────
section("Pages & YC Users", "#F5A623")

pcol, ycol = st.columns(2, gap="large")

with pcol:
    pages_df = _q("""
        SELECT page, COUNT(*) AS views,
               COUNT(DISTINCT visitor_id) AS unique_sessions
        FROM app_analytics
        WHERE event='page_view' AND page IS NOT NULL
        GROUP BY page ORDER BY views DESC
    """)
    if _ok(pages_df) and len(pages_df):
        fig_p = go.Figure(go.Bar(
            x=pages_df["views"],
            y=pages_df["page"],
            orientation="h",
            marker=dict(
                color=pages_df["views"],
                colorscale=[[0, "#1a2e1a"], [1, "#1DB954"]],
                line=dict(width=0),
            ),
            text=pages_df["views"],
            textposition="outside",
            textfont=dict(color="#555", size=11),
            hovertemplate="%{y}<br><b>%{x} views</b><extra></extra>",
        ))
        fig_p.update_layout(
            **{**_B, "margin": dict(t=36, b=12, l=10, r=50)},
            height=max(240, len(pages_df) * 34 + 60),
            title=dict(text="Page views", font=dict(color="#aaa", size=12), x=0),
            xaxis={**_ax(), "tickformat": "d"},
            yaxis=dict(tickfont=dict(color="#aaa", size=11), gridcolor="#0d0d0d"),
            bargap=0.35,
        )
        st.plotly_chart(fig_p, use_container_width=True)
    else:
        _empty("No page view data yet")

with ycol:
    yc_df = _q("""
        SELECT DATE(created_at) AS day, COUNT(*) AS new_users
        FROM uc_sessions
        WHERE created_at > NOW() - INTERVAL 30 DAY
        GROUP BY day ORDER BY day
    """)
    if _ok(yc_df) and len(yc_df):
        fig_y = go.Figure(go.Bar(
            x=yc_df["day"], y=yc_df["new_users"],
            marker=dict(
                color="#B97FE8",
                opacity=0.85,
                line=dict(width=0),
            ),
            text=yc_df["new_users"],
            textposition="outside",
            textfont=dict(color="#555", size=11),
            hovertemplate="%{x}<br><b>%{y} new users</b><extra></extra>",
        ))
        fig_y.update_layout(
            **{**_B, "margin": dict(t=36, b=28, l=40, r=8)},
            height=260,
            title=dict(text="New YC users — last 30 days",
                       font=dict(color="#aaa", size=12), x=0),
            xaxis={**_ax(), "tickformat": "%b %d"},
            yaxis={**_ax(), "tickformat": "d"},
            bargap=0.3,
        )
        st.plotly_chart(fig_y, use_container_width=True)
    else:
        _empty("No YC user data yet")

div()

# ── Section 5 — Live feed ─────────────────────────────────────────────────────
with st.expander("⬤  Live event feed", expanded=False):
    feed_df = _q("""
        SELECT created_at,
               event,
               COALESCE(page, '—')                          AS page,
               COALESCE(LEFT(visitor_id, 8), '—')           AS visitor,
               COALESCE(JSON_UNQUOTE(JSON_EXTRACT(properties,'$.mode')),'') AS mode,
               COALESCE(CAST(JSON_EXTRACT(properties,'$.n_tracks') AS CHAR),'') AS tracks
        FROM app_analytics
        ORDER BY created_at DESC LIMIT 50
    """)
    if _ok(feed_df) and len(feed_df):
        import datetime as _dt
        _tz = _dt.timezone(_dt.timedelta(hours=-3))
        feed_df["created_at"] = (
            pd.to_datetime(feed_df["created_at"])
            .dt.tz_localize("UTC")
            .dt.tz_convert(_tz)
            .dt.strftime("%d/%m %H:%M:%S")
        )
        st.dataframe(
            feed_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "created_at": st.column_config.TextColumn("Time",     width="small"),
                "event":      st.column_config.TextColumn("Event",    width="medium"),
                "page":       st.column_config.TextColumn("Page",     width="small"),
                "visitor":    st.column_config.TextColumn("Visitor",  width="small"),
                "mode":       st.column_config.TextColumn("Mode",     width="small"),
                "tracks":     st.column_config.TextColumn("Tracks",   width="small"),
            },
        )
    else:
        _empty("No events yet")
