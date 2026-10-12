"""Characterization tests of core/enrichment.py and the app_state/enrichment.py glue."""
import pytest
import streamlit as st
from unittest.mock import patch

from core import enrichment as E


def _t(i, **kw):
    return {"id": f"id{i}", "name": f"n{i}", "artists": "a", "playlist_name": "P", **kw}


# ── pending_tracks ──────────────────────────────────────────────────────────
def test_pending_excludes_enriched_and_skipped_but_not_failed():
    tracks = [_t(1), _t(2), _t(3), _t(4)]
    out = E.pending_tracks(tracks, enriched=[{"id": "id1"}], skipped=[{"track_id": "id2"}])
    assert [t["id"] for t in out] == ["id3", "id4"]


def test_pending_legacy_track_id_and_idless_records_ignored():
    out = E.pending_tracks([_t(1)], enriched=[{"track_id": "id1"}, {}], skipped=[{"name": "x"}])
    assert out == []
    assert E.pending_tracks([_t(1)], [{}], [{"name": "x"}]) == [_t(1)]


def test_pending_empty_inputs():
    assert E.pending_tracks([], [], []) == []


# ── records ─────────────────────────────────────────────────────────────────
def test_unenriched_record_defaults():
    assert E.unenriched_record({}) == {
        "name": "", "artists": "", "playlist_name": "", "id": "", "added_at": "",
        "popularity": 0, "album": "", "release_date": "", "duration_ms": 0}


def test_unenriched_record_drops_extra_keys_and_does_not_mutate():
    tr = {"id": "x", "name": "n", "extra": 1}
    rec = E.unenriched_record(tr)
    assert "extra" not in rec and rec["id"] == "x" and tr == {"id": "x", "name": "n", "extra": 1}


def test_enriched_record_merge_and_drop():
    tr = {"id": "x", "energy": 0}
    assert E.enriched_record(tr, {"energy": 0.5, "spotify_id": "x"}, drop_keys=("spotify_id",)) \
        == {"id": "x", "energy": 0.5}
    assert E.enriched_record(tr, {"spotify_id": "x"}) == {"id": "x", "energy": 0, "spotify_id": "x"}


@pytest.mark.parametrize("status,raw,expected", [
    ("skip", None, "skip"), ("skip", {"a": 1}, "skip"),
    ("fail", {"a": 1}, "fail"), ("ok", None, "fail"), (None, None, "fail"),
    ("ok", {"a": 1}, "map"), (None, {}, "map"),
])
def test_classify_fetch(status, raw, expected):
    assert E.classify_fetch(status, raw) == expected


# ── ETA / progress ──────────────────────────────────────────────────────────
def test_eta_no_start_time_or_no_progress_is_estimating():
    for eta in (E.estimate_eta(0, 10, 5.0), E.estimate_eta(3, 10, None)):
        assert eta.label == "estimating…" and eta.seconds_left is None


def test_eta_seconds_and_minutes_format():
    assert E.estimate_eta(10, 20, 10.0).label == "~10s left"        # 1 track/s, 10 left
    e = E.estimate_eta(1, 101, 1.0)                                  # 100 s left
    assert e.label == "~1m 40s left" and e.seconds_left == 100.0


def test_eta_all_done_is_zero_seconds():
    assert E.estimate_eta(5, 5, 2.0).label == "~0s left"


def test_eta_zero_elapsed_with_progress_raises_like_original():
    with pytest.raises(ZeroDivisionError):
        E.estimate_eta(1, 2, 0.0)


def test_remaining_minutes_observed_vs_fallback():
    assert E.estimated_remaining_min(1, 101, E.estimate_eta(1, 101, 1.0)) == pytest.approx(100 / 60)
    assert E.estimated_remaining_min(0, 52, E.estimate_eta(0, 52, None)) == 2.0


@pytest.mark.parametrize("mins,tier", [(0, "short"), (14.99, "short"), (15, "medium"),
                                       (29.99, "medium"), (30, "long"), (500, "long")])
def test_wait_tier(mins, tier):
    assert E.wait_tier(mins) == tier


def test_rotation_index():
    assert E.rotation_index(0, 4, 8, 8) == 0
    assert E.rotation_index(59, 4, 8, 8) == 0
    assert E.rotation_index(60, 4, 8, 8) == 1
    assert E.rotation_index(60 * 8, 4, 8, 8) == 0


def test_progress_and_retry_note():
    assert E.progress_fraction(1, 4) == 0.25
    assert E.retry_note(0) == "" and E.retry_note(3) == " (includes 3 retried)"


# ── snapshot / proxy key ────────────────────────────────────────────────────
def test_pre_enrich_snapshot_keeps_only_old_playlists_and_copies_enriched():
    enriched = [{"id": "e"}]
    snap = E.pre_enrich_snapshot(
        [_t(1, playlist_name="New")], [{"name": "Old"}, {"name": "New"}], enriched, "sid")
    assert snap == {"enriched": [{"id": "e"}], "playlists": [{"name": "Old"}], "session_id": "sid"}
    assert snap["enriched"] is not enriched


def test_pre_enrich_snapshot_empty():
    assert E.pre_enrich_snapshot([], [], [], None) == {
        "enriched": [], "playlists": [], "session_id": None}


def test_playlist_set_key_depends_on_ids_in_order():
    a, b = [{"id": "1"}, {"id": "2"}], [{"id": "2"}, {"id": "1"}]
    assert E.playlist_set_key(a) == E.playlist_set_key(list(a))
    assert E.playlist_set_key(a) != E.playlist_set_key(b)
    assert E.playlist_set_key([]) == str(hash(()))


# ── app_state glue (outcome routing) ────────────────────────────────────────
@pytest.fixture
def state():
    s = {"uc_enriched": [], "uc_skipped": [], "uc_failed": []}
    with patch.object(st, "session_state", s):
        yield s


def _run(track, fetch, fallback=None, mapped=None):
    from app_state.enrichment import process_track
    with patch("pipeline.enrich._fetch", fetch), \
         patch("pipeline.enrich._fetch_fallback", lambda sid: fallback), \
         patch("pipeline.enrich._map_fields", lambda sid, raw: mapped):
        process_track(track)


def _boom(sid):
    raise RuntimeError("x")


def test_process_track_routes_every_outcome(state):
    tr = _t(1)
    _run(tr, _boom)
    _run(tr, lambda sid: (None, "skip"))
    _run(tr, lambda sid: (None, "skip"), fallback={"energy": 1.0})
    _run(tr, lambda sid: ({"d": 1}, "ok"), mapped=None)
    _run(tr, lambda sid: ({"d": 1}, "ok"), mapped={"spotify_id": "id1", "energy": 2.0})
    _run(tr, lambda sid: (None, "fail"))
    assert len(state["uc_failed"]) == 3 and len(state["uc_skipped"]) == 1
    assert state["uc_enriched"] == [{**tr, "energy": 1.0}, {**tr, "energy": 2.0}]
    assert state["uc_failed"][0] == E.unenriched_record(tr)


def test_set_pending_tracks_resets_cursor(state):
    from app_state.enrichment import set_pending_tracks
    state["uc_enriched"] = [{"id": "id1"}]
    set_pending_tracks([_t(1), _t(2)])
    assert [t["id"] for t in state["uc_all_tracks"]] == ["id2"]
    assert state["uc_enrichment_cursor"] == 0 and state["_enrich_start_time"] > 0


def test_init_run_state_resets_skipped_failed_once(state):
    from app_state.enrichment import init_run_state
    state["uc_skipped"], state["uc_failed"] = [1], [2]
    init_run_state()
    assert state["uc_skipped"] == [] and state["uc_failed"] == []
    state["uc_failed"] = [3]
    init_run_state()
    assert state["uc_failed"] == [3]
