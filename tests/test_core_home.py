"""Characterization tests of core/home.py and the app_state/home.py + session restore glue."""
import pytest
import streamlit as st
from unittest.mock import patch

from core import home as H


def test_parse_playlist_param():
    assert H.parse_playlist_param("") == []
    assert H.parse_playlist_param(" a, ,b,,") == ["a", "b"]
    assert H.parse_playlist_param("a,a") == ["a", "a"]


def test_missing_playlist_ids():
    assert H.missing_playlist_ids(["a", "b"], [{"id": "a"}]) == ["b"]
    assert H.missing_playlist_ids([], [{"id": "a"}]) == []


def test_playlist_entry_followers_default_and_query_value():
    e = H.playlist_entry("p", {"name": "N", "tracks": {"total": 5}})
    assert e == {"id": "p", "name": "N", "track_count": 5, "followers": 0}
    assert H.playlist_entry("p", {"name": "N", "tracks": {"total": 5},
                                  "followers": {"total": 9}})["followers"] == 9
    assert H.playlists_query_value([{"id": "a"}, {"id": "b"}]) == "a,b"
    assert H.playlists_query_value([]) == ""


def test_add_playlist_error():
    assert "not found" in H.add_playlist_error(404)
    assert H.add_playlist_error(500) == H.add_playlist_error(None) == "❌ Could not load playlist. Please try again."


def test_active_names_purge_and_count():
    en, sk, fa = [{"playlist_name": "A"}], [{"playlist_name": "B"}, {}], [{"playlist_name": ""}]
    names = H.active_playlist_names(en, sk, fa)
    assert names == {"A", "B"}
    pls = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
    assert H.purge_unenriched_playlists(pls, names) == pls[:2]
    assert H.playlist_count(names, pls) == 2
    # nothing processed: playlists untouched, count = queued
    assert H.purge_unenriched_playlists(pls, set()) is pls
    assert H.playlist_count(set(), pls) == 3


def test_summarize_empty_collection():
    s = H.summarize_collection([], [], [], [])
    assert (s.total, s.n_raw, s.total_dupes) == (0, 0, 0)


def test_summarize_dupes_cross_and_intra():
    en = [{"id": "1"}, {"id": "1"}, {"id": "2"}]            # one cross-playlist repeat
    sk = [{"id": "2"}, {"id": "3"}]                          # id 2 also enriched
    fa = [{"id": "3"}, {}]                                   # id-less record ignored in uniques
    s = H.summarize_collection(en, sk, fa, [{"track_count": 10}, {}])
    assert (s.n_unique_with_af, s.n_unique_without_af, s.total) == (2, 1, 3)
    assert s.n_raw == 7 and s.cross_dupes == 4 and s.intra_dupes == 3 and s.total_dupes == 7


def test_summarize_never_negative():
    s = H.summarize_collection([{"id": "1"}], [], [], [{"track_count": 0}])
    assert s.cross_dupes == 0 and s.intra_dupes == 0


def test_duplicate_note_and_missing_note():
    assert H.duplicate_note(0, 0) == ""
    assert H.duplicate_note(2, 0) == "2 duplicate(s) not counted (2 across playlists)"
    assert H.duplicate_note(0, 1) == "1 duplicate(s) not counted (1 within same playlist)"
    assert H.duplicate_note(2, 1) == \
        "3 duplicate(s) not counted (2 across playlists, 1 within same playlist)"
    assert H.missing_features_note(0, 0) == ""
    assert H.missing_features_note(2, 1) == " · 3 without audio features"


@pytest.mark.parametrize("n,lvl", [(0, "strong"), (99, "strong"), (100, "mild"),
                                   (199, "mild"), (200, None)])
def test_enrich_tip_level(n, lvl):
    assert H.enrich_tip_level(n) == lvl


def test_confirm_estimate():
    pls = [{"track_count": 30}, {"track_count": 30}]
    e = H.confirm_estimate(pls, [{"id": "a"}, {"track_id": "b"}, {}])
    assert (e.n_playlists, e.total_tracks, e.new_tracks, e.est_min) == (2, 60, 57, 3)  # quirk kept: an id-less record counts as one "already enriched" None entry


def test_confirm_estimate_floors_at_one_track():
    e = H.confirm_estimate([], [{"id": "a"}])
    assert (e.total_tracks, e.new_tracks, e.est_min) == (0, 1, 1)


def test_dev_collection_state():
    d = H.dev_collection_state({"enriched": [1], "skipped": [2], "playlists": [3]})
    assert d["failed"] == []
    with pytest.raises(KeyError):
        H.dev_collection_state({"enriched": []})


# ── session restore helpers ─────────────────────────────────────────────────
SID = "12345678-1234-4234-8234-123456789abc"
SESSION = {"enriched": [1], "skipped": [2], "failed": [3], "playlists": [4]}


def test_needs_restore_conditions():
    from app_state.session import needs_restore
    with patch.object(st, "session_state", {}):
        assert needs_restore(SID) and not needs_restore("")
    for flag in ("uc_active", "_dev_loaded", "_adding_playlist"):
        with patch.object(st, "session_state", {flag: True}):
            assert not needs_restore(SID)


def test_home_restore_touch_only_outside_dev_mode(monkeypatch):
    from app_state.home import restore_from_sid
    for dev, touched in (("0", 1), ("1", 0)):
        monkeypatch.setenv("DEV_MODE", dev)
        state = {}
        with patch.object(st, "session_state", state), \
             patch("db.sessions.load_uc_session", return_value=SESSION), \
             patch("db.sessions.touch_uc_session") as touch:
            restore_from_sid(SID)
        assert state["uc_active"] and state["uc_session_id"] == SID and state["uc_enriched"] == [1]
        assert touch.call_count == touched


def test_home_restore_expired_sets_flag_and_unavailable():
    from app_state.home import restore_from_sid
    state, params = {}, {"sid": SID}
    with patch.object(st, "session_state", state), patch.object(st, "query_params", params), \
         patch("db.sessions.load_uc_session", return_value=None):
        restore_from_sid(SID)
    assert state["_session_expired"] and state["_sid_unavailable"] and "sid" not in params


def test_remove_playlist_last_vs_remaining():
    from app_state.home import remove_playlist
    class QP(dict):
        def clear(self):
            super().clear(); self["cleared"] = 1
    state = {"uc_playlists": [{"id": "a"}, {"id": "b"}], "uc_active": True, "uc_enriched": [1]}
    qp = QP()
    with patch.object(st, "session_state", state), patch.object(st, "query_params", qp):
        remove_playlist("a", deactivate_if_remaining=True)
        assert qp["playlists"] == "b" and state["uc_active"] is False
        remove_playlist("b", deactivate_if_remaining=True)
    assert state["uc_playlists"] == [] and "uc_enriched" not in state
    assert state["_sid_forgotten"] and qp == {"cleared": 1}
