"""Analytics identity + event instrumentation.

Covers three fixes:
  1. pages/0_home.py used os.getenv() before `import os`, so the YC
     session-restore path raised NameError and touch_uc_session() never ran
     (uc_sessions.last_seen_at stayed NULL for every row in production).
  2. visitor_id was a per-session UUID, making "returned visitors"
     structurally 0. It now comes from a long-lived first-party cookie.
  3. The real CSV exports were untracked, while the mark-done button emitted
     an event misleadingly named "export_click".

No test here may touch a database: get_engine is stubbed out so every DB call
fails inside the app's own try/except, whatever DEV_MODE the developer has set.
"""
import os
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# spotify_client calls load_dotenv(override=True) at import time, which would
# stamp the local .env's DEV_MODE over anything the tests set. Import it here,
# once, so the per-test monkeypatch.setenv below is the last word.
import spotify_client  # noqa: F401

from streamlit.testing.v1 import AppTest

_ROOT = Path(__file__).resolve().parent.parent
RESULTS_PAGE = str(_ROOT / "pages" / "_Cluster_Results.py")
HOME_PAGE = str(_ROOT / "pages" / "0_home.py")

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I
)
VID = "11111111-2222-4333-8444-555555555555"
SID = "12345678-1234-4123-8123-123456789abc"


@pytest.fixture(autouse=True)
def _no_db_no_dev_mode(monkeypatch):
    """Analytics fire only outside DEV_MODE; the DB must stay unreachable."""
    monkeypatch.setenv("DEV_MODE", "0")

    def _refuse(*_a, **_kw):
        raise RuntimeError("DB access is not allowed in tests")

    monkeypatch.setattr("db.connection.get_engine", _refuse)
    yield


# ── Fix 3 — export instrumentation on the results page ───────────────────────
def _df():
    """Two clusters, three tracks, category mode."""
    return pd.DataFrame({
        "track_id":        ["t1", "t2", "t3"],
        "track_name":      ["Song A", "Song B", "Song C"],
        "artist_name":     ["Artist 1", "Artist 2", "Artist 3"],
        "playlist_name":   ["PL 1", "PL 1", "PL 2"],
        "cluster":         [0, 0, 1],
        "cluster_name":    ["Rock · 1990s", "Rock · 1990s", "Jazz · 2000s"],
        "energy":          [0.8, 0.7, 0.3],
        "acousticness":    [0.1, 0.2, 0.9],
        "valence":         [0.6, 0.5, 0.4],
        "tempo":           [120.0, 128.0, 90.0],
        "danceability":    [0.7, 0.6, 0.4],
        "speechiness_log": [0.05, 0.04, 0.03],
        "release_year":    [1995, 1998, 2004],
        "artist_genres":   ["rock", "rock", "jazz"],
    })


def _results():
    df = _df()
    return {
        "df_clust": df,
        "name_map": {0: "Rock · 1990s", 1: "Jazz · 2000s"},
        "centroids_scaled": None, "var1": 0.0, "var2": 0.0,
        "scaler_used": None, "pc1_label": "", "pc2_label": "",
        "metrics_df": None, "best_k_sil": None, "best_k_elbow": None,
        "optimal_k": 2, "fc_override": False,
        "n_tracks": df["track_id"].nunique(),
        "selected_playlists": ["PL 1", "PL 2"],
        "k": 2, "k_mode": "Manual",
        "selected_decades": ["1990s", "2000s"],
        "selected_families": ["Rock", "Jazz"],
        "decade_options": ["1990s", "2000s"],
        "track_ids": ("t1", "t2", "t3"),
        "grouping_mode": "🗂️ By category",
        "group_by_decade": True, "group_by_genre": True,
        "df_unmatched_cat": pd.DataFrame(),
        "total_playlists": 2,
    }


@pytest.fixture
def results_app():
    at = AppTest.from_file(RESULTS_PAGE, default_timeout=60)
    at.session_state["mode"] = "🎵 Demo Collection"
    at.session_state["visitor_id"] = VID
    at.session_state["clustering_results"] = _results()
    return at


def _events(mock):
    return [c.kwargs.get("event") or c.args[0] for c in mock.call_args_list]


def _event(mock, name):
    return next(c for c in mock.call_args_list
                if (c.kwargs.get("event") or c.args[0]) == name)


class TestExportInstrumentation:
    def test_page_renders(self, results_app):
        results_app.run()
        assert not results_app.exception, results_app.exception

    def test_both_csv_buttons_are_present(self, results_app):
        results_app.run()
        labels = [b.label for b in results_app.download_button]
        assert any("Download CSV" in l for l in labels), labels
        assert any("Download as CSV" in l for l in labels), labels

    def test_rendering_logs_nothing(self, results_app):
        with patch("db.queries.track_event") as tev:
            results_app.run()
            assert tev.call_count == 0

    def test_cluster_csv_download_is_tracked(self, results_app):
        with patch("db.queries.track_event") as tev:
            results_app.run()
            btn = next(b for b in results_app.download_button
                       if "Download CSV" in b.label)
            btn.click().run()

            assert _events(tev).count("export_download") == 1, _events(tev)
            call = _event(tev, "export_download")
            props = call.kwargs["properties"]
            assert call.kwargs["page"] == "Cluster Results"
            assert call.kwargs["visitor_id"] == VID
            assert props["kind"] == "cluster"
            assert props["mode"] == "🗂️ By category"
            assert props["n_tracks"] > 0
            assert props["cluster_name"] in ("Rock · 1990s", "Jazz · 2000s")

    def test_spotlistr_csv_download_is_tracked(self, results_app):
        """The CSV button inside render_export_to_spotify — the prod path."""
        with patch("db.queries.track_event") as tev:
            results_app.run()
            btn = next(b for b in results_app.download_button
                       if "Download as CSV" in b.label)
            btn.click().run()

            assert _events(tev).count("export_download") == 1, _events(tev)
            props = _event(tev, "export_download").kwargs["properties"]
            assert props["kind"] == "spotlistr_csv"
            assert props["n_tracks"] > 0

    def test_event_fires_once_not_on_later_reruns(self, results_app):
        with patch("db.queries.track_event") as tev:
            results_app.run()
            results_app.download_button[0].click().run()
            after_click = len(tev.call_args_list)
            results_app.run()
            assert len(tev.call_args_list) == after_click

    def test_properties_are_json_serialisable(self, results_app):
        """track_event json.dumps()es properties — numpy types would blow up."""
        import json
        with patch("db.queries.track_event") as tev:
            results_app.run()
            results_app.download_button[0].click().run()
            for c in tev.call_args_list:
                json.dumps(c.kwargs["properties"])

    def test_kwargs_match_track_event_signature(self, results_app):
        import inspect
        from db.queries import track_event
        with patch("db.queries.track_event") as tev:
            results_app.run()
            results_app.download_button[0].click().run()
            sig = inspect.signature(track_event)
            for c in tev.call_args_list:
                sig.bind(*c.args, **c.kwargs)

    def test_mark_done_uses_the_renamed_event(self, results_app):
        with patch("db.queries.track_event") as tev:
            results_app.run()
            btn = next(b for b in results_app.button
                       if (b.key or "").startswith("mark_done"))
            btn.click().run()
            if not _events(tev):        # unassigned tracks -> confirm step first
                confirm = next(b for b in results_app.button
                               if (b.key or "").startswith("confirm_yes"))
                confirm.click().run()

            assert _events(tev).count("mark_done_click") == 1, _events(tev)
            assert "export_click" not in _events(tev), "old event name emitted"


# ── Fix 2 — visitor id comes from a cookie, stable across sessions ───────────
class _FakeContext:
    def __init__(self, cookie=None):
        self._cookie = cookie

    @property
    def cookies(self):
        return {"tailorlist_vid": self._cookie} if self._cookie else {}


class _RaisingContext:
    @property
    def cookies(self):
        raise RuntimeError("st.context missing on this Streamlit version")


def _resolve_vid(cookie=None, context=None):
    """Runs the real inject_sidebar_nav visitor-id block and returns the id."""
    import streamlit as st
    import utils

    state = {}
    ctx = context if context is not None else _FakeContext(cookie)
    with patch.object(st, "context", ctx), \
         patch.object(st, "session_state", state), \
         patch.object(st, "query_params", {}), \
         patch.object(st, "sidebar", MagicMock()), \
         patch.object(st, "components", MagicMock()):
        # everything after the visitor-id block needs a live script context
        try:
            utils.inject_sidebar_nav("Home")
        except Exception:
            pass
    return state.get("visitor_id")


class TestVisitorIdentity:
    def test_new_visitor_gets_a_valid_v4(self):
        vid = _resolve_vid()
        assert UUID_RE.match(vid or ""), vid

    def test_returning_visitor_keeps_the_cookie_id(self):
        assert _resolve_vid(cookie=VID) == VID

    def test_malformed_cookie_is_replaced(self):
        vid = _resolve_vid(cookie="garbage-not-a-uuid")
        assert UUID_RE.match(vid or ""), vid
        assert vid != "garbage-not-a-uuid"

    def test_missing_st_context_does_not_break(self):
        """Older Streamlit without st.context must still yield an id."""
        vid = _resolve_vid(context=_RaisingContext())
        assert UUID_RE.match(vid or ""), vid

    def test_id_is_not_put_in_the_url(self):
        """It lives in a cookie; a ?vid= would leak identity via shared links."""
        import streamlit as st
        import utils
        state, qp = {}, {}
        with patch.object(st, "context", _FakeContext(VID)), \
             patch.object(st, "session_state", state), \
             patch.object(st, "query_params", qp), \
             patch.object(st, "sidebar", MagicMock()), \
             patch.object(st, "components", MagicMock()):
            try:
                utils.inject_sidebar_nav("Home")
            except Exception:
                pass
        assert state.get("visitor_id") == VID, "block did not run"
        assert "vid" not in qp


# ── Fix 1 — YC session restore no longer raises NameError ────────────────────
FAKE_SESSION = {
    "enriched": [], "skipped": [], "failed": [],
    "playlists": [{"id": "pl1", "name": "PL 1", "track_count": 3}],
}


@pytest.fixture
def home_app():
    at = AppTest.from_file(HOME_PAGE, default_timeout=90)
    at.query_params["sid"] = SID
    return at


class TestYcSessionRestore:
    def test_restore_runs_and_touches_last_seen(self, home_app):
        with patch("db.queries.load_uc_session", return_value=FAKE_SESSION), \
             patch("db.queries.touch_uc_session") as touch, \
             patch("utils.inject_sidebar_nav"):
            home_app.run()
            assert not home_app.exception, home_app.exception
            assert touch.call_count == 1, "touch_uc_session was not called"
            assert touch.call_args.args[0] == SID

    def test_session_lands_in_state(self, home_app):
        with patch("db.queries.load_uc_session", return_value=FAKE_SESSION), \
             patch("db.queries.touch_uc_session"), \
             patch("utils.inject_sidebar_nav"):
            home_app.run()
            assert home_app.session_state["uc_active"] is True
            assert home_app.session_state["uc_session_id"] == SID

    def test_dev_mode_writes_nothing(self, home_app, monkeypatch):
        monkeypatch.setenv("DEV_MODE", "1")
        with patch("db.queries.load_uc_session", return_value=FAKE_SESSION), \
             patch("db.queries.touch_uc_session") as touch, \
             patch("utils.inject_sidebar_nav"):
            home_app.run()
            assert not home_app.exception, home_app.exception
            assert touch.call_count == 0
