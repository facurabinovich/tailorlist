import pandas as pd
import streamlit as st
from db.connection import get_engine

# ---------------------------------------------------------------------------
# Base enriched tracks query — canonical flat view used across all pages
# ---------------------------------------------------------------------------

_SECONDARY_ARTISTS_SUBQUERY = """
    (
        SELECT GROUP_CONCAT(a2.name ORDER BY bsa2.artist_order SEPARATOR ', ')
        FROM bridge_song_artists bsa2
        JOIN dim_artist a2 ON bsa2.dim_artist_id = a2.id
        WHERE bsa2.dim_song_id = fs.dim_song_id
          AND bsa2.is_primary = FALSE
    ) AS secondary_artists"""

_BASE_SQL = """
SELECT
    s.spotify_id        AS track_id,
    s.name              AS track_name,
    art.name            AS artist_name,
    pl.name             AS playlist_name,
    al.name             AS album_name,
    af.energy, af.acousticness, af.valence, af.tempo, af.danceability,
    af.loudness, af.instrumentalness, af.speechiness, af.liveness, af.mode,
    fs.popularity_raw, fs.duration_raw,
    rd.year   AS release_year,
    rd.decade AS decade,
    art.genres AS artist_genres,
    fs.added_at,""" + _SECONDARY_ARTISTS_SUBQUERY + """
FROM fac_songs fs
JOIN dim_songs              s   ON fs.dim_song_id           = s.id
JOIN dim_playlist           pl  ON fs.dim_playlist_id       = pl.id
JOIN dim_audio_features     af  ON fs.dim_audio_features_id = af.id
JOIN bridge_song_artists    bsa ON fs.dim_song_id           = bsa.dim_song_id
JOIN dim_artist             art ON bsa.dim_artist_id        = art.id
JOIN dim_album              al  ON fs.dim_album_id          = al.id
LEFT JOIN dim_releasedate   rd  ON fs.dim_releasedate_id    = rd.id
WHERE bsa.is_primary = TRUE
  AND pl.is_personal = TRUE
  AND fs.dim_audio_features_id IS NOT NULL
"""


def _add_artist_display(df: pd.DataFrame) -> pd.DataFrame:
    """Add artist_display column: 'Primary feat. Secondary' when secondary artists exist."""
    if "secondary_artists" not in df.columns:
        df["artist_display"] = df["artist_name"]
        return df
    mask = df["secondary_artists"].notna() & (df["secondary_artists"] != "")
    df["artist_display"] = df["artist_name"].copy()
    df.loc[mask, "artist_display"] = (
        df.loc[mask, "artist_name"] + " feat. " + df.loc[mask, "secondary_artists"]
    )
    return df


@st.cache_data
def load_tracks() -> pd.DataFrame:
    """All personal playlist tracks, enriched. One row per track-per-playlist."""
    return _add_artist_display(pd.read_sql(_BASE_SQL, get_engine()))

_BASE_SQL_ALL = """
SELECT
    s.spotify_id        AS track_id,
    s.name              AS track_name,
    art.name            AS artist_name,
    pl.name             AS playlist_name,
    al.name             AS album_name,
    af.energy, af.acousticness, af.valence, af.tempo, af.danceability,
    af.loudness, af.instrumentalness, af.speechiness, af.liveness, af.mode,
    fs.popularity_raw, fs.duration_raw,
    rd.year   AS release_year,
    rd.decade AS decade,
    art.genres AS artist_genres,
    fs.added_at,""" + _SECONDARY_ARTISTS_SUBQUERY + """
FROM fac_songs fs
JOIN dim_songs              s   ON fs.dim_song_id           = s.id
JOIN dim_playlist           pl  ON fs.dim_playlist_id       = pl.id
LEFT JOIN dim_audio_features af  ON fs.dim_audio_features_id = af.id
JOIN bridge_song_artists    bsa ON fs.dim_song_id           = bsa.dim_song_id
JOIN dim_artist             art ON bsa.dim_artist_id        = art.id
LEFT JOIN dim_album         al  ON fs.dim_album_id          = al.id
LEFT JOIN dim_releasedate   rd  ON fs.dim_releasedate_id    = rd.id
WHERE bsa.is_primary = TRUE
  AND pl.is_personal = TRUE
"""

@st.cache_data
def load_all_tracks() -> pd.DataFrame:
    """All personal playlist tracks including those without audio features."""
    return _add_artist_display(pd.read_sql(_BASE_SQL_ALL, get_engine()))

def get_all_tracks() -> pd.DataFrame:
    """
    Universal loader for ALL tracks including those without audio features.
    Use this for Overview, Playlist Detail, Comparison — anywhere counts/stats matter.
    Use get_tracks() only where audio features are required (Audio DNA, Clusters).
    """
    if (st.session_state.get("mode") == "🔗 Your Collection"
            and st.session_state.get("uc_active")
            and st.session_state.get("uc_enriched")):
        enriched = pd.DataFrame(st.session_state["uc_enriched"])
        skipped  = pd.DataFrame(st.session_state.get("uc_skipped", []))
        failed   = pd.DataFrame(st.session_state.get("uc_failed", []))

        # Skipped/failed tracks carry real Spotify IDs — keep them.
        # Only generate a synthetic id for rows that genuinely lack one (defensive
        # fallback for any very old session data written before id was stored).
        for _df in [skipped, failed]:
            if not _df.empty and "id" not in _df.columns:
                _df["id"] = _df["name"] + "||" + _df.get("artists", pd.Series(dtype=str)).fillna("")

        frames = [enriched]
        if not skipped.empty:
            frames.append(skipped)
        if not failed.empty:
            frames.append(failed)

        df = pd.concat(frames, ignore_index=True)

        df = df.rename(columns={
            "id":          "track_id",
            "name":        "track_name",
            "artists":     "artist_name",
            "popularity":  "popularity_raw",
            "album":       "album_name",
            "duration_ms": "duration_raw",
        })

        if "release_date" in df.columns:
            df["release_year"] = _parse_release_year(df["release_date"])
            df["decade"] = (df["release_year"] // 10 * 10).where(
                df["release_year"].notna()
            )
        return _add_artist_display(df)
    return load_all_tracks()


@st.cache_data
def load_tracks_deduped() -> pd.DataFrame:
    """Unique tracks only (keep first occurrence per spotify_id)."""
    df = load_tracks()
    return df.drop_duplicates(subset="track_id").reset_index(drop=True)

def _parse_release_year(release_date_series: pd.Series) -> pd.Series:
    """
    Robustly extract year from Spotify release_date which can be:
    - "2014"          (year only)
    - "2014-03"       (year-month)
    - "2014-03-15"    (full date)
    """
    def _extract(val):
        if pd.isna(val) or val == "":
            return None
        val = str(val).strip()
        # Year only: "2014"
        if len(val) == 4 and val.isdigit():
            return int(val)
        # Year-month: "2014-03"
        if len(val) == 7:
            try:
                return int(val[:4])
            except ValueError:
                return None
        # Full date: "2014-03-15"
        try:
            return pd.to_datetime(val, errors="coerce").year
        except Exception:
            return None

    result = release_date_series.apply(_extract)
    # Replace implausible years with None
    return result.where(result > 1900, other=None)


def get_tracks() -> pd.DataFrame:
    """
    Universal data loader. Returns enriched tracks from session state
    when user collection is active, otherwise loads from DB.
    All pages should call this instead of load_tracks().
    """
    if (st.session_state.get("mode") == "🔗 Your Collection"
        and st.session_state.get("uc_active")
        and st.session_state.get("uc_enriched")):
        df = pd.DataFrame(st.session_state["uc_enriched"])
        df = df.rename(columns={
            "id":          "track_id",
            "name":        "track_name",
            "artists":     "artist_name",
            "popularity":  "popularity_raw",
            "album":       "album_name",
            "duration_ms": "duration_raw",
        })
        # Derive release_year and decade from release_date
        if "release_date" in df.columns:
            df["release_year"] = _parse_release_year(df["release_date"])
            df["decade"] = (df["release_year"] // 10 * 10).where(
                df["release_year"].notna()
            )
        return _add_artist_display(df)
    return load_tracks()


# ---------------------------------------------------------------------------
# Overview page queries
# ---------------------------------------------------------------------------

@st.cache_data
def load_playlist_track_counts() -> pd.DataFrame:
    sql = """
    SELECT pl.name AS playlist_name, COUNT(*) AS track_count
    FROM fac_songs fs
    JOIN dim_playlist pl ON fs.dim_playlist_id = pl.id
    WHERE pl.is_personal = TRUE
      AND fs.dim_audio_features_id IS NOT NULL
    GROUP BY pl.name
    ORDER BY track_count DESC
    """
    return pd.read_sql(sql, get_engine())


@st.cache_data
def load_top_artists(n: int = 20) -> pd.DataFrame:
    sql = """
    SELECT art.name AS artist_name, COUNT(DISTINCT fs.dim_song_id) AS track_count
    FROM fac_songs fs
    JOIN dim_playlist        pl  ON fs.dim_playlist_id  = pl.id
    JOIN bridge_song_artists bsa ON fs.dim_song_id      = bsa.dim_song_id
    JOIN dim_artist          art ON bsa.dim_artist_id   = art.id
    WHERE pl.is_personal = TRUE
      AND bsa.is_primary = TRUE
      AND fs.dim_audio_features_id IS NOT NULL
    GROUP BY art.name
    ORDER BY track_count DESC
    LIMIT %(n)s
    """
    return pd.read_sql(sql, get_engine(), params={"n": int(n)})

@st.cache_data
def load_additions_timeline() -> pd.DataFrame:
    sql = """
    SELECT
        dd.year        AS `year`,
        dd.month       AS `month`,
        dd.year_month_str AS `year_month`,
        COUNT(*)       AS tracks_added
    FROM fac_songs fs
    JOIN dim_playlist pl ON fs.dim_playlist_id    = pl.id
    JOIN dim_date     dd ON fs.dim_date_added_id  = dd.id
    WHERE pl.is_personal = TRUE
      AND fs.dim_audio_features_id IS NOT NULL
    GROUP BY dd.year, dd.month, dd.year_month_str
    ORDER BY dd.year, dd.month
    """
    return pd.read_sql(sql, get_engine())

# ---------------------------------------------------------------------------
# Audio DNA page queries
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def load_audio_features_by_playlist() -> pd.DataFrame:
    """Mean audio features per playlist — for radar/bar charts."""
    sql = """
    SELECT
        pl.name AS playlist_name,
        AVG(af.energy)          AS energy,
        AVG(af.acousticness)    AS acousticness,
        AVG(af.valence)         AS valence,
        AVG(af.tempo)           AS tempo,
        AVG(af.danceability)    AS danceability,
        AVG(af.loudness)        AS loudness,
        AVG(af.instrumentalness) AS instrumentalness,
        AVG(af.speechiness)     AS speechiness,
        AVG(af.liveness)        AS liveness
    FROM fac_songs fs
    JOIN dim_playlist       pl  ON fs.dim_playlist_id       = pl.id
    JOIN dim_audio_features af  ON fs.dim_audio_features_id = af.id
    WHERE pl.is_personal = TRUE
      AND fs.dim_audio_features_id IS NOT NULL
    GROUP BY pl.name
    """
    return pd.read_sql(sql, get_engine())

@st.cache_data
def load_playlist_meta() -> pd.DataFrame:
    sql = """
    SELECT
        name        AS playlist_name,
        total_tracks,
        followers,
        description
    FROM dim_playlist
    WHERE is_personal = TRUE
    """
    return pd.read_sql(sql, get_engine())

@st.cache_data(show_spinner=False)
def load_cluster_data() -> pd.DataFrame:
    """5 KMeans features + metadata for all personal tracks."""
    sql = """
    SELECT
        s.spotify_id        AS track_id,
        s.name              AS track_name,
        pl.name             AS playlist_name,
        art.name            AS artist_name,
        af.energy, af.acousticness, af.valence, af.tempo, af.danceability,
        af.speechiness,
        art.genres          AS artist_genres,
        rd.decade           AS decade,""" + _SECONDARY_ARTISTS_SUBQUERY + """
    FROM fac_songs fs
    JOIN dim_songs          s   ON fs.dim_song_id           = s.id
    JOIN dim_playlist       pl  ON fs.dim_playlist_id       = pl.id
    JOIN dim_audio_features af  ON fs.dim_audio_features_id = af.id
    JOIN bridge_song_artists bsa ON fs.dim_song_id          = bsa.dim_song_id
    JOIN dim_artist         art ON bsa.dim_artist_id        = art.id
    JOIN dim_releasedate    rd  ON fs.dim_releasedate_id    = rd.id
    WHERE bsa.is_primary = TRUE
      AND pl.is_personal  = TRUE
      AND fs.dim_audio_features_id IS NOT NULL
    """
    return _add_artist_display(pd.read_sql(sql, get_engine()))

@st.cache_data(show_spinner=False)
def load_all_tracks_for_grouping() -> pd.DataFrame:
    """All personal tracks regardless of audio features — for Genre & Decade grouping mode."""
    sql = """
    SELECT
        s.spotify_id        AS track_id,
        s.name              AS track_name,
        pl.name             AS playlist_name,
        art.name            AS artist_name,
        art.genres          AS artist_genres,
        rd.decade           AS decade,
        rd.year             AS release_year
    FROM fac_songs fs
    JOIN dim_songs           s   ON fs.dim_song_id        = s.id
    JOIN dim_playlist        pl  ON fs.dim_playlist_id    = pl.id
    JOIN bridge_song_artists bsa ON fs.dim_song_id        = bsa.dim_song_id
    JOIN dim_artist          art ON bsa.dim_artist_id     = art.id
    JOIN dim_releasedate     rd  ON fs.dim_releasedate_id = rd.id
    WHERE bsa.is_primary = TRUE
      AND pl.is_personal  = TRUE
    """
    return pd.read_sql(sql, get_engine())


def load_unmatched_tracks() -> pd.DataFrame:
    """Tracks with no audio features — for manual cluster assignment."""
    sql = """
    SELECT
        s.spotify_id        AS track_id,
        s.name              AS track_name,
        art.name            AS artist_name,
        rd.year             AS release_year,
        art.genres          AS artist_genres,
        pl.name             AS playlist_name,""" + _SECONDARY_ARTISTS_SUBQUERY + """
    FROM fac_songs fs
    JOIN dim_songs           s   ON fs.dim_song_id        = s.id
    JOIN dim_playlist        pl  ON fs.dim_playlist_id    = pl.id
    JOIN bridge_song_artists bsa ON fs.dim_song_id        = bsa.dim_song_id
    JOIN dim_artist          art ON bsa.dim_artist_id     = art.id
    JOIN dim_releasedate     rd  ON fs.dim_releasedate_id = rd.id
    WHERE bsa.is_primary = TRUE
      AND pl.is_personal  = TRUE
      AND fs.dim_audio_features_id IS NULL
    """
    return _add_artist_display(pd.read_sql(sql, get_engine()))


def get_cluster_data() -> pd.DataFrame:
    if (st.session_state.get("mode") == "🔗 Your Collection"
            and st.session_state.get("uc_active")
            and st.session_state.get("uc_enriched")):
        df = get_tracks()
        cols = [c for c in ["track_id", "track_name", "artist_name", "artist_display", "playlist_name",
                            "energy", "acousticness", "valence", "tempo", "danceability"] if c in df.columns]
        return df[cols].dropna(
                   subset=["energy", "acousticness", "valence", "tempo", "danceability"])
    st.cache_data.clear()  # bust cache when switching back to Demo Collection
    return load_cluster_data()

def get_audio_features_by_playlist() -> pd.DataFrame:
    """Routes to session state or DB based on mode."""
    if (st.session_state.get("mode") == "🔗 Your Collection"
            and st.session_state.get("uc_active")
            and st.session_state.get("uc_enriched")):
        df = get_tracks()
        return df.groupby("playlist_name")[
            ["energy","acousticness","valence","tempo",
             "danceability","loudness","instrumentalness",
             "speechiness","liveness"]
        ].mean().reset_index()
    return load_audio_features_by_playlist()

@st.cache_data
def load_top_artists_by_popularity(n: int = 5, min_tracks: int = 5) -> pd.DataFrame:
    sql = """
    SELECT art.name AS artist_name,
           COUNT(DISTINCT fs.dim_song_id)        AS track_count,
           AVG(fs.popularity_raw)                AS avg_popularity
    FROM fac_songs fs
    JOIN dim_playlist        pl  ON fs.dim_playlist_id  = pl.id
    JOIN bridge_song_artists bsa ON fs.dim_song_id      = bsa.dim_song_id
    JOIN dim_artist          art ON bsa.dim_artist_id   = art.id
    WHERE pl.is_personal = TRUE
      AND bsa.is_primary = TRUE
      AND fs.dim_audio_features_id IS NOT NULL
    GROUP BY art.name
    HAVING COUNT(DISTINCT fs.dim_song_id) >= %(min_tracks)s
    ORDER BY avg_popularity DESC
    LIMIT %(n)s
    """
    return pd.read_sql(sql, get_engine(), params={"n": int(n), "min_tracks": int(min_tracks)})


@st.cache_data
def load_top_albums(n: int = 5) -> pd.DataFrame:
    sql = """
    SELECT al.name                               AS album_name,
           art.name                              AS artist_name,
           COUNT(DISTINCT fs.dim_song_id)        AS track_count,
           AVG(fs.popularity_raw)                AS avg_popularity
    FROM fac_songs fs
    JOIN dim_playlist        pl  ON fs.dim_playlist_id  = pl.id
    JOIN dim_album           al  ON fs.dim_album_id     = al.id
    JOIN bridge_song_artists bsa ON fs.dim_song_id      = bsa.dim_song_id
    JOIN dim_artist          art ON bsa.dim_artist_id   = art.id
    WHERE pl.is_personal = TRUE
      AND bsa.is_primary = TRUE
      AND fs.dim_audio_features_id IS NOT NULL
    GROUP BY al.name, art.name
    ORDER BY track_count DESC, avg_popularity DESC
    LIMIT %(n)s
    """
    return pd.read_sql(sql, get_engine(), params={"n": int(n)})

@st.cache_data
def load_tracks_added_by_month(playlist_name: str) -> pd.DataFrame:
    sql = """
    SELECT
        DATE_FORMAT(fs.added_at, '%%Y-%%m') AS `year_month`,
        COUNT(*)                          AS track_count
    FROM fac_songs fs
    JOIN dim_playlist pl ON fs.dim_playlist_id = pl.id
    WHERE pl.is_personal = TRUE
      AND fs.dim_audio_features_id IS NOT NULL
      AND pl.name = %(playlist_name)s
    GROUP BY 1
    ORDER BY 1 ASC
    """
    return pd.read_sql(sql, get_engine(), params={"playlist_name": playlist_name})


# ── Persistence helpers ───────────────────────────────────────────────────────
import json as _json
from sqlalchemy import text as _text


def _ensure_tables():
    """Create persistence tables if they don't exist."""
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