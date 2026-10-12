from typing import Iterable
import pandas as pd
import streamlit as st
from db.connection import get_engine
from sqlalchemy import text as _text


_tables_ensured = False

def _ensure_tables():
    """Create persistence tables if they don't exist. Runs once per process."""
    global _tables_ensured
    if _tables_ensured:
        return
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(_text("""
            CREATE TABLE IF NOT EXISTS user_cluster_progress (
                id           INT AUTO_INCREMENT PRIMARY KEY,
                user_key     VARCHAR(100) NOT NULL,
                track_id     VARCHAR(50) NOT NULL,
                status       ENUM('done', 'manual') NOT NULL,
                cluster_name VARCHAR(100),
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_user_track (user_key, track_id)
            )
        """))
        conn.execute(_text("""
            CREATE TABLE IF NOT EXISTS user_progress_meta (
                user_key  VARCHAR(100) NOT NULL PRIMARY KEY,
                reset_at  DATETIME     NOT NULL
            )
        """))
        conn.execute(_text("""
            CREATE TABLE IF NOT EXISTS uc_sessions (
                id             INT AUTO_INCREMENT PRIMARY KEY,
                session_id     VARCHAR(36) NOT NULL UNIQUE,
                enriched_json  LONGTEXT NOT NULL,
                skipped_json   LONGTEXT,
                failed_json    LONGTEXT,
                playlists_json LONGTEXT,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                KEY idx_session_id (session_id),
                KEY idx_created_at (created_at)
            )
        """))
    _tables_ensured = True


def load_cluster_progress(user_key: str) -> dict:
    """
    Returns {track_id: {"status": "done"|"manual", "cluster_name": str|None}}
    Filters out records saved before the last reset_at (if any).
    Returns empty dict if no progress exists or on any error.
    """
    try:
        _ensure_tables()
        engine = get_engine()
        with engine.connect() as conn:
            meta = conn.execute(
                _text("SELECT reset_at FROM user_progress_meta WHERE user_key = :uk"),
                {"uk": user_key}
            ).fetchone()
            reset_at = meta[0] if meta else None

            rows = conn.execute(
                _text("""
                    SELECT track_id, status, cluster_name, updated_date
                    FROM user_cluster_progress
                    WHERE user_key = :uk
                """),
                {"uk": user_key}
            ).fetchall()

        result = {}
        for r in rows:
            if reset_at and r[3] and r[3] <= reset_at:
                continue
            result[r[0]] = {"status": r[1], "cluster_name": r[2]}
        return result
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("load_cluster_progress failed: %s", exc)
        return {}


def reset_cluster_progress(user_key: str) -> bool:
    """
    Resets all cluster progress for a user.
    Attempts DELETE first; always writes reset_at so load_cluster_progress
    returns empty even if DELETE failed or the page is hard-refreshed.
    Returns True on full success, False if any step errored.
    """
    try:
        _ensure_tables()
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                _text("DELETE FROM user_cluster_progress WHERE user_key = :uk"),
                {"uk": user_key}
            )
            conn.execute(
                _text("""
                    INSERT INTO user_progress_meta (user_key, reset_at)
                    VALUES (:uk, NOW())
                    ON DUPLICATE KEY UPDATE reset_at = NOW()
                """),
                {"uk": user_key}
            )
        return True
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("reset_cluster_progress failed: %s", exc)
        return False


def save_cluster_progress(user_key: str, track_id: str,
                          status: str, cluster_name: str = None):
    """Upsert a single track's clustering progress."""
    try:
        _ensure_tables()
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(_text("""
                INSERT INTO user_cluster_progress
                    (user_key, track_id, status, cluster_name)
                VALUES
                    (:uk, :tid, :st, :cn)
                ON DUPLICATE KEY UPDATE
                    status       = VALUES(status),
                    cluster_name = VALUES(cluster_name),
                    updated_date = CURRENT_TIMESTAMP
            """), {"uk": user_key, "tid": track_id, "st": status, "cn": cluster_name})
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("save_cluster_progress failed: %s", exc)


def save_cluster_progress_bulk(user_key: str, track_ids: list[str],
                               status: str, cluster_name: str = None):
    """Upsert many tracks in one DB round-trip (executemany)."""
    if not track_ids:
        return
    try:
        _ensure_tables()
        engine = get_engine()
        params = [{"uk": user_key, "tid": tid, "st": status, "cn": cluster_name}
                  for tid in track_ids]
        with engine.begin() as conn:
            conn.execute(_text("""
                INSERT INTO user_cluster_progress
                    (user_key, track_id, status, cluster_name)
                VALUES
                    (:uk, :tid, :st, :cn)
                ON DUPLICATE KEY UPDATE
                    status       = VALUES(status),
                    cluster_name = VALUES(cluster_name),
                    updated_date = CURRENT_TIMESTAMP
            """), params)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("save_cluster_progress_bulk failed: %s", exc)


def delete_done_progress(user_key: str, track_ids: Iterable[str]) -> None:
    """Delete 'done' progress rows for the given tracks (re-open clusters)."""
    track_ids = tuple(track_ids)
    if not track_ids:
        return
    with get_engine().begin() as conn:
        conn.execute(
            _text("DELETE FROM user_cluster_progress "
                  "WHERE user_key = :uk AND status = 'done' "
                  "AND track_id IN :tids"),
            {"uk": user_key, "tids": track_ids},
        )


def delete_progress_for_tracks(user_key: str, track_ids: Iterable[str]) -> None:
    """Delete progress rows (any status) for the given tracks (keep visible)."""
    track_ids = tuple(track_ids)
    if not track_ids:
        return
    with get_engine().begin() as conn:
        conn.execute(
            _text("DELETE FROM user_cluster_progress "
                  "WHERE user_key = :uk AND track_id IN :tids"),
            {"uk": user_key, "tids": track_ids},
        )
