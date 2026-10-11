import json as _json
from db.connection import get_engine
from db.progress import _ensure_tables
from sqlalchemy import text as _text


def save_uc_session(session_id: str, enriched: list, skipped: list,
                    failed: list, playlists: list):
    """Upsert a YC session to MySQL."""
    try:
        _ensure_tables()
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(_text("""
                INSERT INTO uc_sessions
                    (session_id, enriched_json, skipped_json, failed_json, playlists_json)
                VALUES
                    (:sid, :enr, :skp, :fld, :pl)
                ON DUPLICATE KEY UPDATE
                    enriched_json  = VALUES(enriched_json),
                    skipped_json   = VALUES(skipped_json),
                    failed_json    = VALUES(failed_json),
                    playlists_json = VALUES(playlists_json),
                    updated_at     = CURRENT_TIMESTAMP
            """), {
                "sid": session_id,
                "enr": _json.dumps(enriched, default=str),
                "skp": _json.dumps(skipped, default=str),
                "fld": _json.dumps(failed, default=str),
                "pl":  _json.dumps(playlists, default=str),
            })
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("save_uc_session failed: %s", exc)


def touch_uc_session(session_id: str):
    """Update last_seen_at on a YC session — called every time the session is restored."""
    _migrate_analytics_schema()
    try:
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(_text("""
                UPDATE uc_sessions
                SET last_seen_at = CURRENT_TIMESTAMP
                WHERE session_id = :sid
            """), {"sid": session_id})
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("touch_uc_session failed: %s", exc)


def load_uc_session(session_id: str) -> dict | None:
    """
    Load a YC session by session_id.
    Returns None if not found, expired (older than 7 days), or on error.
    """
    try:
        _ensure_tables()
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(_text("""
                SELECT enriched_json, skipped_json, failed_json, playlists_json
                FROM uc_sessions
                WHERE session_id = :sid
                  AND created_at > NOW() - INTERVAL 7 DAY
            """), {"sid": session_id}).fetchone()
        if row is None:
            return None
        return {
            "enriched":  _json.loads(row[0]),
            "skipped":   _json.loads(row[1]) if row[1] else [],
            "failed":    _json.loads(row[2]) if row[2] else [],
            "playlists": _json.loads(row[3]) if row[3] else [],
        }
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("load_uc_session failed: %s", exc)
        return None


def delete_session_data(session_id: str) -> None:
    """Delete a YC session and its cluster progress in one transaction."""
    with get_engine().begin() as conn:
        conn.execute(
            _text("DELETE FROM uc_sessions WHERE session_id = :sid"),
            {"sid": session_id}
        )
        conn.execute(
            _text("DELETE FROM user_cluster_progress WHERE user_key = :uk"),
            {"uk": session_id}
        )
