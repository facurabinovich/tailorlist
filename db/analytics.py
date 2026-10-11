from db.connection import get_engine
from sqlalchemy import text as _text


_analytics_migrated = False

def _migrate_analytics_schema():
    """Add new analytics columns to existing tables if not present. Runs once per process."""
    global _analytics_migrated
    if _analytics_migrated:
        return
    _analytics_migrated = True  # set early so a failure doesn't retry every call
    try:
        engine = get_engine()
        migrations = [
            "ALTER TABLE app_analytics ADD COLUMN visitor_id VARCHAR(36)",
            "ALTER TABLE app_analytics ADD COLUMN properties JSON",
            "ALTER TABLE app_analytics ADD INDEX idx_visitor_id (visitor_id)",
            "ALTER TABLE uc_sessions ADD COLUMN last_seen_at TIMESTAMP NULL",
        ]
        for sql in migrations:
            try:
                with engine.begin() as conn:
                    conn.execute(_text(sql))
            except Exception:
                pass  # column / index already exists
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("_migrate_analytics_schema failed: %s", exc)


def track_event(event: str, page: str = None, session_id: str = None,
                visitor_id: str = None, properties: dict = None):
    """
    Log an analytics event to app_analytics table.
    Fails silently — never crashes the app.
    """
    _migrate_analytics_schema()
    try:
        import json as _json_local
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(_text("""
                CREATE TABLE IF NOT EXISTS app_analytics (
                    id          INT AUTO_INCREMENT PRIMARY KEY,
                    event       VARCHAR(50) NOT NULL,
                    page        VARCHAR(50),
                    session_id  VARCHAR(36),
                    visitor_id  VARCHAR(36),
                    properties  JSON,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    KEY idx_event      (event),
                    KEY idx_created_at (created_at),
                    KEY idx_session_id (session_id),
                    KEY idx_visitor_id (visitor_id)
                )
            """))
            conn.execute(_text("""
                INSERT INTO app_analytics (event, page, session_id, visitor_id, properties)
                VALUES (:event, :page, :sid, :vid, :props)
            """), {
                "event": event,
                "page":  page,
                "sid":   session_id,
                "vid":   visitor_id,
                "props": _json_local.dumps(properties) if properties else None,
            })
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("track_event failed: %s", exc)


def backfill_enrichment_session(session_id: str, proxy: str) -> None:
    """Replace the proxy session_id on the latest enrichment_start row with the real one."""
    with get_engine().begin() as conn:
        conn.execute(_text("""
            UPDATE app_analytics
            SET session_id = :sid
            WHERE event = 'enrichment_start'
              AND session_id = :proxy
            ORDER BY created_at DESC
            LIMIT 1
        """), {"sid": session_id, "proxy": proxy})
