"""Exact SQL + params + call order for the write functions moved out of pages (T13)."""
from unittest.mock import MagicMock

import pytest


def _norm(sql) -> str:
    return " ".join(str(sql).split())


@pytest.fixture
def engine(patch_get_engine):
    eng = MagicMock()
    conn = eng.begin.return_value.__enter__.return_value
    patch_get_engine(lambda: eng)
    return eng, conn


def _calls(conn):
    return [(_norm(c.args[0]), c.args[1]) for c in conn.execute.call_args_list]


def test_delete_session_data(engine):
    from db.sessions import delete_session_data
    eng, conn = engine
    delete_session_data("sid-1")
    eng.begin.assert_called_once()
    assert _calls(conn) == [
        ("DELETE FROM uc_sessions WHERE session_id = :sid", {"sid": "sid-1"}),
        ("DELETE FROM user_cluster_progress WHERE user_key = :uk", {"uk": "sid-1"}),
    ]


def test_touch_uc_session(engine, monkeypatch):
    # Regression: the db split left _migrate_analytics_schema unimported here (NameError).
    monkeypatch.setattr("db.analytics._analytics_migrated", True)
    from db.sessions import touch_uc_session
    eng, conn = engine
    touch_uc_session("sid-1")
    assert _calls(conn) == [
        ("UPDATE uc_sessions SET last_seen_at = CURRENT_TIMESTAMP WHERE session_id = :sid",
         {"sid": "sid-1"}),
    ]


def test_delete_done_progress(engine):
    from db.progress import delete_done_progress
    eng, conn = engine
    delete_done_progress("u1", {"t1"})
    eng.begin.assert_called_once()
    assert _calls(conn) == [(
        "DELETE FROM user_cluster_progress WHERE user_key = :uk AND status = 'done' "
        "AND track_id IN :tids", {"uk": "u1", "tids": ("t1",)})]


def test_delete_progress_for_tracks(engine):
    from db.progress import delete_progress_for_tracks
    eng, conn = engine
    delete_progress_for_tracks("u1", ["a", "b"])
    eng.begin.assert_called_once()
    assert _calls(conn) == [(
        "DELETE FROM user_cluster_progress WHERE user_key = :uk AND track_id IN :tids",
        {"uk": "u1", "tids": ("a", "b")})]


def test_backfill_enrichment_session(engine):
    from db.analytics import backfill_enrichment_session
    eng, conn = engine
    backfill_enrichment_session("real", "proxy")
    eng.begin.assert_called_once()
    assert _calls(conn) == [(
        "UPDATE app_analytics SET session_id = :sid WHERE event = 'enrichment_start' "
        "AND session_id = :proxy ORDER BY created_at DESC LIMIT 1",
        {"sid": "real", "proxy": "proxy"})]


def test_errors_propagate(patch_get_engine):
    from db.progress import delete_done_progress
    eng = MagicMock()
    eng.begin.side_effect = RuntimeError("boom")
    patch_get_engine(lambda: eng)
    with pytest.raises(RuntimeError):
        delete_done_progress("u", [])
