"""Smoke tests: every page under pages/ renders (or redirects) without an exception.

Safety net for the architecture refactor: these run the REAL page scripts through
``AppTest`` and fail if a page crashes or silently renders nothing.

Data and modes
  * Your Collection (YC): the real ``db.queries.get_all_tracks/get_tracks`` code
    path, fed from ``data/dev_collection.json`` placed in session state.
  * Demo Collection (FC): the DB loaders in ``db.queries`` are patched with frames
    derived from the same JSON, exactly where the pages look them up. No fake DB.

AppTest quirks handled here (see ``app`` fixture):
  * ``st.context.cookies`` is a MagicMock inside AppTest, which breaks
    ``utils.inject_sidebar_nav`` / ``resolve_sid`` -> replaced by a plain dict.
  * ``st.page_link`` needs the multipage registry, absent in a single-file AppTest
    -> no-op. Everything else in ``inject_sidebar_nav`` still runs for real.
  * Unpatched, ``st.switch_page`` raises "Could not find page" in AppTest (it is
    not a redirect there), so redirects are asserted via ``redirects`` below.
"""
import ast
import json
import types
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.runtime.scriptrunner_utils.exceptions import StopException
from streamlit.testing.v1 import AppTest

import db.queries as q
import app_state.collection as collection


ROOT = Path(__file__).resolve().parent.parent
PAGES_DIR = ROOT / "pages"
COLLECTION = json.loads((ROOT / "data" / "dev_collection.json").read_text(encoding="utf-8"))

FC = "🎵 Demo Collection"
YC = "🔗 Your Collection"
KMEANS = "🔬 By audio similarity (KMeans)"
CATEGORY = "🗂️ By category"

_FEATURES = ["energy", "acousticness", "valence", "tempo", "danceability",
             "loudness", "instrumentalness", "speechiness", "liveness"]


# ── Mock data ────────────────────────────────────────────────────────────────
def _to_frame(rows: list[dict]) -> pd.DataFrame:
    """Same column mapping as db.queries.get_all_tracks (YC branch)."""
    df = pd.DataFrame(rows).rename(columns={
        "id": "track_id", "name": "track_name", "artists": "artist_name",
        "popularity": "popularity_raw", "album": "album_name",
        "duration_ms": "duration_raw"})
    df["release_year"] = q._parse_release_year(df["release_date"])
    df["decade"] = (df["release_year"] // 10 * 10).where(df["release_year"].notna())
    return q._add_artist_display(df)


def _patch_fc_loaders(mp: pytest.MonkeyPatch) -> None:
    """Patch the DB loaders the pages import from db.queries (Demo Collection)."""
    c = COLLECTION
    all_tracks = _to_frame(c["enriched"] + c["skipped"] + c["failed"])
    with_af = _to_frame(c["enriched"])
    meta = pd.DataFrame(c["playlists"]).rename(
        columns={"name": "playlist_name", "track_count": "total_tracks"})
    meta["description"] = ""

    def added_by_month(playlist_name):
        d = all_tracks[all_tracks["playlist_name"] == playlist_name]
        month = pd.to_datetime(d["added_at"]).dt.strftime("%Y-%m")
        return d.groupby(month).size().rename_axis("year_month").reset_index(name="track_count")

    cluster_cols = ["track_id", "track_name", "playlist_name", "artist_name", "energy",
                    "acousticness", "valence", "tempo", "danceability", "speechiness",
                    "artist_genres", "decade", "artist_display"]
    patches = {
        "load_all_tracks": lambda: all_tracks,
        "load_tracks": lambda: with_af,
        "load_audio_features_by_playlist":
            lambda: with_af.groupby("playlist_name")[_FEATURES].mean().reset_index(),
        "load_playlist_meta": lambda: meta,
        "load_playlist_track_counts":
            lambda: with_af.groupby("playlist_name").size().reset_index(name="track_count"),
        "load_tracks_added_by_month": added_by_month,
        "load_cluster_data": lambda: with_af[cluster_cols],
        "load_unmatched_tracks": lambda: _to_frame(c["skipped"]),
        "load_all_tracks_for_grouping": lambda: all_tracks,
        "load_cluster_progress": lambda user_key: {},
    }
    for name, fn in patches.items():
        mp.setattr(q, name, fn)
    # The session-aware wrappers (get_tracks, get_all_tracks, ...) look their DB loaders up
    # in app_state.collection, so patch the loaders they use there too.
    for name, fn in patches.items():
        if hasattr(collection, name):
            mp.setattr(collection, name, fn)


def _yc_state(at: AppTest) -> None:
    """Session state a user has after enriching their own playlists."""
    c = COLLECTION
    at.session_state["uc_active"] = True
    at.session_state["uc_enriched"] = c["enriched"]
    at.session_state["uc_skipped"] = c["skipped"]
    at.session_state["uc_failed"] = c["failed"]
    at.session_state["uc_playlists"] = c["playlists"]


# ── Fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def app(monkeypatch):
    """AppTest workarounds + FC loader patches (see module docstring)."""
    monkeypatch.setattr(st, "context", types.SimpleNamespace(cookies={}))
    monkeypatch.setattr(st, "page_link", lambda *a, **k: None)
    _patch_fc_loaders(monkeypatch)


@pytest.fixture
def redirects(monkeypatch):
    """Record ``st.switch_page`` targets and halt the script like a real redirect.

    The real switch_page raises a rerun control exception; StopException is the
    inert equivalent for AppTest (ends the run, no exception element, no rerun loop).
    """
    targets: list[str] = []

    def fake_switch_page(page, **_kw):
        targets.append(str(page))
        raise StopException()

    monkeypatch.setattr(st, "switch_page", fake_switch_page)
    return targets


def _page(name: str, mode: str | None = None) -> AppTest:
    at = AppTest.from_file(str(PAGES_DIR / f"{name}.py"), default_timeout=120)
    if mode is not None:
        at.session_state["mode"] = mode
    if mode == YC:
        _yc_state(at)
    return at


def _md(at: AppTest) -> str:
    return "\n".join(m.value for m in at.markdown)


def _plotly(at: AppTest) -> int:
    return len(at.get("plotly_chart"))


# ── The 9 regular pages, in both modes ───────────────────────────────────────
# (page, markdown snippets that must be present, min plotly charts)
PAGE_EXPECTATIONS = [
    ("0_home", ["Your Collection"], 0),
    ("1_Overview", ["Tailorlist", "## Tracks per Playlist", "## Top 20 Artists"], 1),
    ("2_Playlist_Detail", ["## Track Highlights", "## Averages", "## All Tracks"], 1),
    ("3_Artist_Album", ["Tailorlist", "### 🎵 Tracks"], 1),
    ("4_Playlist_Comparison", ["## Size", "## Audio Feature Leaders"], 1),
    ("5_Audio_DNA", ["## Mood Map", "## Global Fingerprint"], 1),
    ("6_My_Clusters", ["My Clusters", "Configure"], 0),
    ("7_Glossary", ["Glossary"], 0),
    ("8_Contact", ["Contact"], 0),
]


@pytest.mark.parametrize("mode", [FC, YC], ids=["FC", "YC"])
@pytest.mark.parametrize("page,snippets,min_charts", PAGE_EXPECTATIONS,
                         ids=[p[0] for p in PAGE_EXPECTATIONS])
def test_page_renders(page, snippets, min_charts, mode):
    at = _page(page, mode).run()
    assert not at.exception, at.exception
    text = _md(at)
    for snippet in snippets:
        assert snippet in text, f"{page}/{mode}: {snippet!r} missing - page rendered nothing?"
    assert _plotly(at) >= min_charts, f"{page}/{mode}: expected charts, got {_plotly(at)}"


# Home, Glossary and Contact do not call check_collection_mode, so they never gate.
@pytest.mark.parametrize("page", [p[0] for p in PAGE_EXPECTATIONS
                                  if p[0] not in ("0_home", "7_Glossary", "8_Contact")])
def test_yc_without_collection_shows_prompt(page):
    """YC mode with nothing enriched: the page stops at the 'No collection yet' prompt."""
    at = _page(page)
    at.session_state["mode"] = YC
    at.run()
    assert not at.exception, at.exception
    assert "No collection yet" in _md(at)
    assert _plotly(at) == 0


def test_my_clusters_run_redirects_to_results(redirects):
    """Click Run on the real KMeans path: results land in state, then redirect."""
    at = _page("6_My_Clusters", FC).run()
    at.button(key="run_clustering_btn").click()
    at.run()
    assert not at.exception, at.exception
    assert redirects == ["pages/_Cluster_Results.py"]
    assert at.session_state["clustering_results"]["df_clust"]["cluster"].nunique() >= 2


# ── Redirect-only pages ──────────────────────────────────────────────────────
def test_album_goto_redirects_to_artist_album(redirects):
    at = _page("_album_goto").run()
    assert not at.exception, at.exception
    assert redirects == ["pages/3_Artist_Album.py"]


def test_enrich_without_playlists_redirects_home(redirects):
    """No uc_playlists queued: reset enrichment state and go back to Home."""
    at = _page("_Enrich").run()
    assert not at.exception, at.exception
    assert redirects == ["pages/0_home.py"]
    assert at.session_state["uc_enrichment_state"] == "idle"


def test_cluster_results_without_results_offers_way_back(redirects):
    at = _page("_Cluster_Results", FC).run()
    assert not at.exception, at.exception
    assert at.warning and "No clustering results" in at.warning[0].value
    assert redirects == []                       # nothing redirects by itself
    at.button[0].click()
    at.run()
    assert redirects == ["pages/6_My_Clusters.py"]


# ── _Cluster_Results with real results ───────────────────────────────────────
def _category_results() -> dict:
    """Minimal 'By category' results (shape used by tests/test_analytics_identity.py)."""
    df = pd.DataFrame({
        "track_id": ["t1", "t2", "t3"],
        "track_name": ["Song A", "Song B", "Song C"],
        "artist_name": ["Artist 1", "Artist 2", "Artist 3"],
        "playlist_name": ["PL 1", "PL 1", "PL 2"],
        "cluster": [0, 0, 1],
        "cluster_name": ["Rock · 1990s", "Rock · 1990s", "Jazz · 2000s"],
        "energy": [0.8, 0.7, 0.3], "acousticness": [0.1, 0.2, 0.9],
        "valence": [0.6, 0.5, 0.4], "tempo": [120.0, 128.0, 90.0],
        "danceability": [0.7, 0.6, 0.4], "speechiness_log": [0.05, 0.04, 0.03],
        "release_year": [1995, 1998, 2004], "artist_genres": ["rock", "rock", "jazz"],
    })
    return {
        "df_clust": df, "name_map": {0: "Rock · 1990s", 1: "Jazz · 2000s"},
        "centroids_scaled": None, "var1": 0.0, "var2": 0.0, "scaler_used": None,
        "pc1_label": "", "pc2_label": "", "metrics_df": None,
        "best_k_sil": None, "best_k_elbow": None, "optimal_k": 2, "fc_override": False,
        "n_tracks": 3, "selected_playlists": ["PL 1", "PL 2"], "k": 2, "k_mode": "Manual",
        "selected_decades": ["1990s", "2000s"], "selected_families": ["Rock", "Jazz"],
        "decade_options": ["1990s", "2000s"], "track_ids": ("t1", "t2", "t3"),
        "grouping_mode": CATEGORY, "group_by_decade": True, "group_by_genre": True,
        "df_unmatched_cat": pd.DataFrame(), "total_playlists": 2,
    }


def _kmeans_results(mode: str, redirects: list[str]) -> dict:
    """Produce genuine KMeans results by running My Clusters and clicking Run."""
    at = _page("6_My_Clusters", mode).run()
    at.button(key="run_clustering_btn").click()
    at.run()
    assert not at.exception, at.exception
    assert redirects, "My Clusters did not finish clustering"
    return at.session_state["clustering_results"]


@pytest.mark.parametrize("mode", [FC, YC], ids=["FC", "YC"])
@pytest.mark.parametrize("grouping", [KMEANS, CATEGORY], ids=["kmeans", "category"])
def test_cluster_results_renders(grouping, mode, redirects):
    results = _kmeans_results(mode, redirects) if grouping == KMEANS else _category_results()
    at = _page("_Cluster_Results", mode)
    at.session_state["clustering_results"] = results
    at.run()
    assert not at.exception, at.exception
    text = _md(at)
    for name in results["name_map"].values():
        assert name in text, f"cluster {name!r} not shown on the results page"
    assert len(at.button) > 0
    if grouping == KMEANS:
        assert _plotly(at) >= 1


# ── Pages must not import each other ─────────────────────────────────────────
def _imported_modules(path: Path) -> set[str]:
    mods: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mods.add(node.module or "")
            mods.update(f"{node.module or ''}.{a.name}" for a in node.names)
    return mods


@pytest.mark.parametrize("path", sorted(PAGES_DIR.glob("*.py")), ids=lambda p: p.stem)
def test_page_does_not_import_other_pages(path):
    stems = {p.stem for p in PAGES_DIR.glob("*.py")}
    for mod in _imported_modules(path):
        parts = mod.split(".")
        assert parts[0] != "pages", f"{path.name} imports {mod}"
        assert not stems & set(parts), f"{path.name} imports page module via {mod}"
