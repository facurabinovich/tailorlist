"""
pipeline/load.py
Load transformed DataFrames into MySQL, resolving all FK mappings.

Loading order (respects foreign-key dependency):
  1. dim_artist
  2. dim_playlist
  3. dim_album
  4. dim_releasedate
  5. dim_date
  6. dim_popularity + dim_duration  (pre-populated; queried, not inserted)
  7. dim_songs
  8. bridge_song_artists
  9. fac_songs

dim_audio_features is intentionally excluded — populated by enrich.py.
"""

import logging
import os
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


# ── Engine ────────────────────────────────────────────────────────────────────

def _create_engine(env_path: str | Path | None = None) -> Engine:
    load_dotenv(env_path)

    raw = os.getenv("DATABASE_URL")
    if raw:
        url = raw.replace("mysql://", "mysql+pymysql://", 1)
        if "charset=" not in url:
            sep = "&" if "?" in url else "?"
            url += f"{sep}charset=utf8mb4"
    else:
        host = os.getenv("DB_HOST", "localhost")
        port = int(os.getenv("DB_PORT", 3307))
        user = os.getenv("DB_USER")
        password = os.getenv("DB_PASSWORD")
        database = os.getenv("DB_NAME", "spotify_analytics")
        if not all([user, password]):
            raise EnvironmentError("Missing DB_USER or DB_PASSWORD environment variables")
        url = (
            f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
            "?charset=utf8mb4"
        )

    engine = create_engine(url, echo=False)

    with engine.connect() as conn:
        version = conn.execute(text("SELECT VERSION()")).fetchone()[0]
        logger.info("Connected to MySQL %s — %s", version, url.split("@")[-1])

    return engine


# ── ID-map initialisation ─────────────────────────────────────────────────────

def _init_id_maps() -> dict[str, Any]:
    return {
        "artist":          {},   # internal_id (int) -> db_id
        "songs":           {},   # SongID (int)      -> db_id
        "songs_by_spotid": {},   # spotify_id (str)  -> db_id
        "releasedate":     {},   # date obj          -> db_id
        "date":            {},   # date obj          -> db_id
        "popularity":      [],   # [(id, name, min, max), ...]
        "duration":        [],   # [(id, name, min_min, max_min), ...]
    }


# ── Range helpers ─────────────────────────────────────────────────────────────

def _map_popularity(value: Any, ranges: list) -> int | None:
    if pd.isna(value):
        value = 0
    value = int(value)
    for rid, _name, lo, hi in ranges:
        if lo <= value <= hi:
            return rid
    return None


def _map_duration(value: Any, ranges: list) -> int | None:
    if pd.isna(value):
        value = 3.0
    value = float(value)
    last_id = None
    for rid, _name, lo, hi in ranges:
        # Track the last range whose min is <= value (handles open upper bound)
        if value >= lo:
            last_id = rid
        if lo <= value < hi:
            return rid
    return last_id


# ── Loaders ───────────────────────────────────────────────────────────────────

def _load_artists(engine: Engine, df: pd.DataFrame, id_maps: dict) -> int:
    logger.info("Loading dim_artist: %d rows", len(df))
    df = df.copy()

    # Build internal_id → spotify_id before dedup so every SongID can resolve
    internal_to_spotid: dict[int, str] = {
        int(row["internal_id"]): row["spotify_id"]
        for _, row in df.iterrows()
        if pd.notna(row.get("spotify_id"))
    }

    null_mask = df["spotify_id"].isna()
    df_dedup = pd.concat([
        df[~null_mask].drop_duplicates(subset=["spotify_id"], keep="first"),
        df[null_mask],
    ]).reset_index(drop=True)

    df_dedup["popularity"] = df_dedup["popularity"].fillna(0).astype(int)
    df_dedup["genres"]     = df_dedup["genres"].fillna("")
    df_dedup["spotify_id"] = df_dedup["spotify_id"].where(df_dedup["spotify_id"].notna(), None)

    params = [
        {
            "name":       row["name"],
            "spotify_id": row["spotify_id"],
            "popularity": int(row["popularity"]),
            "genres":     row["genres"],
        }
        for _, row in df_dedup.iterrows()
    ]

    sql = text("""
        INSERT INTO dim_artist (name, spotify_id, popularity, genres)
        VALUES (:name, :spotify_id, :popularity, :genres)
        ON DUPLICATE KEY UPDATE
            name       = VALUES(name),
            popularity = VALUES(popularity),
            genres     = VALUES(genres)
    """)

    with engine.begin() as conn:
        conn.execute(sql, params)

    # Rebuild id_maps via SELECT (avoids needing per-row lastrowid)
    with engine.connect() as conn:
        spotid_to_db: dict[str, int] = {
            r[1]: r[0]
            for r in conn.execute(text("SELECT id, spotify_id FROM dim_artist WHERE spotify_id IS NOT NULL")).fetchall()
        }
    for internal_id, spotid in internal_to_spotid.items():
        if spotid in spotid_to_db:
            id_maps["artist"][internal_id] = spotid_to_db[spotid]

    count = len(params)
    logger.info("dim_artist: %d rows loaded", count)
    return count


def _load_playlists(engine: Engine, df: pd.DataFrame, id_maps: dict) -> int:
    logger.info("Loading dim_playlist: %d rows", len(df))
    df = df.copy()

    df = df.drop_duplicates(subset=["spotify_id"], keep="first")
    df["description"]      = df["description"].fillna("")
    df["owner_id"]         = df["owner_id"].fillna("")
    df["owner_name"]       = df["owner_name"].fillna("")
    df["is_public"]        = df["is_public"].fillna(False).astype(bool)
    df["is_collaborative"] = df["is_collaborative"].fillna(False).astype(bool)
    df["is_personal"]      = df["is_personal"].fillna(True).astype(bool)
    df["total_tracks"]     = df["total_tracks"].fillna(0).astype(int)
    df["followers"]        = df["followers"].fillna(0).astype(int)
    df["snapshot_id"]      = df["snapshot_id"].fillna("")

    params = [
        {
            "name":             row["name"],
            "spotify_id":       row["spotify_id"],
            "description":      row.get("description", ""),
            "owner_id":         row.get("owner_id", ""),
            "owner_name":       row.get("owner_name", ""),
            "is_public":        bool(row.get("is_public", False)),
            "is_collaborative": bool(row.get("is_collaborative", False)),
            "total_tracks":     int(row.get("total_tracks", 0)),
            "followers":        int(row.get("followers", 0)),
            "snapshot_id":      row.get("snapshot_id", ""),
            "is_personal":      bool(row.get("is_personal", True)),
        }
        for _, row in df.iterrows()
    ]

    sql = text("""
        INSERT INTO dim_playlist
            (name, spotify_id, description, owner_id, owner_name,
             is_public, is_collaborative, total_tracks, followers,
             snapshot_id, is_personal)
        VALUES
            (:name, :spotify_id, :description, :owner_id, :owner_name,
             :is_public, :is_collaborative, :total_tracks, :followers,
             :snapshot_id, :is_personal)
        ON DUPLICATE KEY UPDATE
            name             = VALUES(name),
            description      = VALUES(description),
            total_tracks     = VALUES(total_tracks),
            followers        = VALUES(followers),
            snapshot_id      = VALUES(snapshot_id),
            is_public        = VALUES(is_public),
            is_collaborative = VALUES(is_collaborative),
            is_personal      = VALUES(is_personal)
    """)

    with engine.begin() as conn:
        conn.execute(sql, params)
    count = len(params)

    logger.info("dim_playlist: %d rows loaded", count)
    return count


def _load_albums(engine: Engine, df: pd.DataFrame, id_maps: dict) -> int:
    logger.info("Loading dim_album: %d rows", len(df))
    df = df.copy()

    df["name"]       = df["name"].fillna("Unknown Album")
    df["spotify_id"] = df["spotify_id"].where(df["spotify_id"].notna(), None)
    if "release_date" in df.columns:
        df["release_date"] = pd.to_datetime(df["release_date"], errors="coerce").dt.date
    else:
        df["release_date"] = None
    df = df.drop_duplicates(subset=["name"], keep="first")

    with engine.connect() as conn:
        existing: set[str] = {
            row[0] for row in conn.execute(text("SELECT name FROM dim_album")).fetchall()
        }

    new_rows = df[~df["name"].isin(existing)]
    if not new_rows.empty:
        params = [
            {
                "name":         row["name"],
                "spotify_id":   row.get("spotify_id"),
                "release_date": row.get("release_date") if pd.notna(row.get("release_date")) else None,
            }
            for _, row in new_rows.iterrows()
        ]
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO dim_album (name, spotify_id, release_date)
                VALUES (:name, :spotify_id, :release_date)
                ON DUPLICATE KEY UPDATE release_date = VALUES(release_date)
            """), params)

    count = len(new_rows)
    logger.info("dim_album: %d new rows inserted", count)
    return count


def _load_releasedates(engine: Engine, df: pd.DataFrame, id_maps: dict) -> int:
    logger.info("Loading dim_releasedate: %d rows", len(df))
    df = df.copy()

    df["full_date"] = pd.to_datetime(df["full_date"], errors="coerce").dt.date
    df = df.dropna(subset=["full_date"]).drop_duplicates(subset=["full_date"])
    for col in ("year", "month", "day", "decade", "year_half", "quarter"):
        df[col] = df[col].astype(int)

    params = [
        {
            "full_date": row["full_date"],
            "year":      int(row["year"]),
            "month":     int(row["month"]),
            "day":       int(row["day"]),
            "decade":    int(row["decade"]),
            "year_half": int(row["year_half"]),
            "quarter":   int(row["quarter"]),
        }
        for _, row in df.iterrows()
    ]

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO dim_releasedate
                (full_date, year, month, day, decade, year_half, quarter)
            VALUES
                (:full_date, :year, :month, :day, :decade, :year_half, :quarter)
            ON DUPLICATE KEY UPDATE
                year      = VALUES(year),
                month     = VALUES(month),
                day       = VALUES(day),
                decade    = VALUES(decade),
                year_half = VALUES(year_half),
                quarter   = VALUES(quarter)
        """), params)

    # Rebuild id_maps via SELECT
    with engine.connect() as conn:
        for r in conn.execute(text("SELECT id, full_date FROM dim_releasedate")).fetchall():
            id_maps["releasedate"][r[1]] = r[0]

    count = len(params)
    logger.info("dim_releasedate: %d rows loaded", count)
    return count


def _load_dates(engine: Engine, df: pd.DataFrame, id_maps: dict) -> int:
    logger.info("Loading dim_date: %d rows", len(df))
    df = df.copy()

    df["full_date"] = pd.to_datetime(df["full_date"], errors="coerce").dt.date
    df = df.dropna(subset=["full_date"]).drop_duplicates(subset=["full_date"])
    for col in ("day_of_month", "month", "year", "day_of_week",
                "quarter", "week_of_year", "day_of_year"):
        df[col] = df[col].astype(int)
    df["is_weekend"] = df["is_weekend"].astype(bool)
    df["is_holiday"] = df["is_holiday"].fillna(False).astype(bool)

    params = [
        {
            "full_date":      row["full_date"],
            "day_of_month":   int(row["day_of_month"]),
            "month":          int(row["month"]),
            "year":           int(row["year"]),
            "day_of_week":    int(row["day_of_week"]),
            "day_name":       row["day_name"],
            "month_name":     row["month_name"],
            "quarter":        int(row["quarter"]),
            "year_month_str": row["year_month_str"],
            "week_of_year":   int(row["week_of_year"]),
            "is_weekend":     bool(row["is_weekend"]),
            "is_holiday":     bool(row["is_holiday"]),
            "holiday_name":   row.get("holiday_name") if pd.notna(row.get("holiday_name")) else None,
            "season":         row.get("season"),
            "day_of_year":    int(row["day_of_year"]),
        }
        for _, row in df.iterrows()
    ]

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO dim_date
                (full_date, day_of_month, month, year, day_of_week, day_name,
                 month_name, quarter, year_month_str, week_of_year, is_weekend,
                 is_holiday, holiday_name, season, day_of_year)
            VALUES
                (:full_date, :day_of_month, :month, :year, :day_of_week, :day_name,
                 :month_name, :quarter, :year_month_str, :week_of_year, :is_weekend,
                 :is_holiday, :holiday_name, :season, :day_of_year)
            ON DUPLICATE KEY UPDATE
                day_of_month   = VALUES(day_of_month),
                month          = VALUES(month),
                year           = VALUES(year),
                day_of_week    = VALUES(day_of_week),
                day_name       = VALUES(day_name),
                month_name     = VALUES(month_name),
                quarter        = VALUES(quarter),
                year_month_str = VALUES(year_month_str),
                week_of_year   = VALUES(week_of_year),
                is_weekend     = VALUES(is_weekend),
                is_holiday     = VALUES(is_holiday),
                holiday_name   = VALUES(holiday_name),
                season         = VALUES(season),
                day_of_year    = VALUES(day_of_year)
        """), params)

    # Rebuild id_maps via SELECT
    with engine.connect() as conn:
        for r in conn.execute(text("SELECT id, full_date FROM dim_date")).fetchall():
            id_maps["date"][r[1]] = r[0]

    count = len(params)
    logger.info("dim_date: %d rows loaded", count)
    return count


def _load_range_mappings(engine: Engine, id_maps: dict) -> None:
    """
    Query pre-populated dim_popularity and dim_duration.
    These tables are seeded by the DB schema script — we never INSERT into them.
    """
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, range_name, min_value, max_value "
            "FROM dim_popularity ORDER BY min_value"
        )).fetchall()
        id_maps["popularity"] = [(r[0], r[1], r[2], r[3]) for r in rows]
        logger.info("Loaded %d popularity ranges", len(id_maps["popularity"]))

        rows = conn.execute(text(
            "SELECT id, range_name, min_minutes, max_minutes "
            "FROM dim_duration ORDER BY min_minutes"
        )).fetchall()
        id_maps["duration"] = [(r[0], r[1], float(r[2]), float(r[3])) for r in rows]
        logger.info("Loaded %d duration ranges", len(id_maps["duration"]))


def _load_songs(engine: Engine, df: pd.DataFrame, id_maps: dict) -> int:
    logger.info("Loading dim_songs: %d rows (%d unique spotify_ids)",
                len(df), df["spotify_id"].nunique())
    df = df.copy()
    df["name"]               = df["name"].fillna("Unknown Song")
    df["spotify_id"]         = df["spotify_id"].fillna("")
    df["is_local"]           = df["is_local"].fillna(False).astype(bool)
    df["has_audio_features"] = df["has_audio_features"].fillna(False).astype(bool)

    # Build SongID -> spotify_id before dedup so all SongIDs resolve after insert
    song_id_to_spotid: dict[int, str] = {
        int(row["SongID"]): row["spotify_id"]
        for _, row in df.iterrows()
    }

    df_dedup = df.drop_duplicates(subset=["spotify_id"], keep="first")
    params = [
        {
            "name":               row["name"],
            "spotify_id":         row["spotify_id"],
            "is_local":           bool(row["is_local"]),
            "has_audio_features": bool(row["has_audio_features"]),
        }
        for _, row in df_dedup.iterrows()
    ]

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO dim_songs (name, spotify_id, is_local, has_audio_features)
            VALUES (:name, :spotify_id, :is_local, :has_audio_features)
            ON DUPLICATE KEY UPDATE
                name               = VALUES(name),
                is_local           = VALUES(is_local)
        """), params)

    # Rebuild id_maps via SELECT
    with engine.connect() as conn:
        spotid_to_db: dict[str, int] = {
            r[1]: r[0]
            for r in conn.execute(text("SELECT id, spotify_id FROM dim_songs")).fetchall()
        }
    for song_id, spotify_id in song_id_to_spotid.items():
        db_id = spotid_to_db.get(spotify_id)
        if db_id:
            id_maps["songs"][song_id] = db_id
    id_maps["songs_by_spotid"] = spotid_to_db

    count = len(params)
    logger.info("dim_songs: %d unique rows loaded, %d SongID mappings",
                count, len(id_maps["songs"]))
    return count


def _load_bridge(engine: Engine, df: pd.DataFrame, id_maps: dict) -> int:
    logger.info("Loading bridge_song_artists: %d rows", len(df))
    df = df.copy()

    df["spotify_artist_id"] = df["spotify_artist_id"].fillna("")
    df["is_primary"]        = df["is_primary"].fillna(False).astype(bool)
    df["artist_order"]      = df["artist_order"].fillna(1).astype(int)

    with engine.connect() as conn:
        artist_spotid_to_db: dict[str, int] = {
            r[1]: r[0]
            for r in conn.execute(text(
                "SELECT id, spotify_id FROM dim_artist WHERE spotify_id IS NOT NULL"
            )).fetchall()
        }

    skipped = 0
    params = []
    for _, row in df.iterrows():
        raw_song_id   = int(row["dim_song_id"])
        raw_artist_id = int(row["dim_artist_id"])
        sp_artist_id  = row.get("spotify_artist_id", "") or ""

        db_song_id = id_maps["songs"].get(raw_song_id)
        if db_song_id is None:
            skipped += 1
            continue

        if sp_artist_id and sp_artist_id in artist_spotid_to_db:
            db_artist_id = artist_spotid_to_db[sp_artist_id]
        else:
            db_artist_id = id_maps["artist"].get(raw_artist_id)

        if db_artist_id is None:
            skipped += 1
            continue

        params.append({
            "dim_song_id":       db_song_id,
            "dim_artist_id":     db_artist_id,
            "spotify_artist_id": sp_artist_id or None,
            "is_primary":        bool(row["is_primary"]),
            "artist_order":      int(row["artist_order"]),
        })

    if params:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT IGNORE INTO bridge_song_artists
                    (dim_song_id, dim_artist_id, spotify_artist_id, is_primary, artist_order)
                VALUES
                    (:dim_song_id, :dim_artist_id, :spotify_artist_id, :is_primary, :artist_order)
            """), params)

    if skipped:
        logger.warning("bridge_song_artists: %d rows skipped (unmapped IDs)", skipped)
    count = len(params)
    logger.info("bridge_song_artists: %d rows loaded", count)
    return count


def _load_fact(engine: Engine, df: pd.DataFrame, id_maps: dict) -> int:
    """
    INSERT fac_songs with all FK IDs resolved.

    FK resolution:
      - dim_song_id:         spotify_id (SpotifyID col) -> db_id, fallback dim_song_id
      - dim_playlist_id:     playlist_name -> id  (queried from DB)
      - dim_album_id:        album_name -> id     (queried from DB)
      - dim_releasedate_id:  release_date date    -> id_maps['releasedate']
      - dim_date_added_id:   added_at date        -> id_maps['date']
      - dim_popularity_id:   popularity_raw       -> _map_popularity()
      - dim_duration_id:     duration_raw         -> _map_duration()
      - dim_audio_features_id: NULL (enrich.py will backfill)
    """
    logger.info("Loading fac_songs: %d rows", len(df))
    df = df.copy()

    df["added_at"] = pd.to_datetime(df.get("added_at"), errors="coerce")
    df["added_by"] = df.get("added_by", pd.Series(dtype=str)).fillna("")

    with engine.connect() as conn:
        playlist_name_to_id: dict[str, int] = {
            r[1]: r[0]
            for r in conn.execute(text("SELECT id, name FROM dim_playlist")).fetchall()
        }
        album_name_to_id: dict[str, int] = {
            r[1]: r[0]
            for r in conn.execute(text("SELECT id, name FROM dim_album")).fetchall()
        }

    # Resolve all FKs in Python, collect valid rows, then bulk INSERT once
    skipped = 0
    params = []
    for _, row in df.iterrows():
        spotify_id = row.get("SpotifyID", "") or ""
        db_song_id = id_maps["songs_by_spotid"].get(spotify_id)
        if db_song_id is None:
            raw_sid = row.get("dim_song_id")
            if pd.notna(raw_sid):
                db_song_id = id_maps["songs"].get(int(raw_sid))

        db_playlist_id = playlist_name_to_id.get(row.get("playlist_name", ""))
        db_album_id    = album_name_to_id.get(row.get("album_name", ""))

        if None in (db_song_id, db_playlist_id, db_album_id):
            logger.debug("fac_songs skip: song=%r playlist=%r album=%r",
                         spotify_id, row.get("playlist_name"), row.get("album_name"))
            skipped += 1
            continue

        release_date = row.get("release_date")
        db_releasedate_id = id_maps["releasedate"].get(pd.to_datetime(release_date).date()) \
            if pd.notna(release_date) else None

        added_at = row.get("added_at")
        db_date_added_id = id_maps["date"].get(pd.to_datetime(added_at).date()) \
            if pd.notna(added_at) else None

        pop_raw = row.get("popularity_raw")
        dur_raw = row.get("duration_raw")

        params.append({
            "dim_song_id":           db_song_id,
            "dim_playlist_id":       db_playlist_id,
            "dim_album_id":          db_album_id,
            "dim_releasedate_id":    db_releasedate_id,
            "dim_date_added_id":     db_date_added_id,
            "dim_popularity_id":     _map_popularity(pop_raw, id_maps["popularity"]),
            "dim_duration_id":       _map_duration(dur_raw, id_maps["duration"]),
            "dim_audio_features_id": None,
            "popularity_raw":        int(pop_raw) if pd.notna(pop_raw) else None,
            "duration_raw":          float(dur_raw) if pd.notna(dur_raw) else None,
            "added_at":              added_at if pd.notna(added_at) else None,
            "added_by":              row.get("added_by", "") or "",
        })

    if params:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT IGNORE INTO fac_songs
                    (dim_song_id, dim_playlist_id, dim_album_id, dim_releasedate_id,
                     dim_date_added_id, dim_popularity_id, dim_duration_id,
                     dim_audio_features_id, popularity_raw, duration_raw, added_at, added_by)
                VALUES
                    (:dim_song_id, :dim_playlist_id, :dim_album_id, :dim_releasedate_id,
                     :dim_date_added_id, :dim_popularity_id, :dim_duration_id,
                     :dim_audio_features_id, :popularity_raw, :duration_raw, :added_at, :added_by)
            """), params)

    count = len(params)
    if skipped:
        logger.warning("fac_songs: %d rows skipped (unmapped required FKs)", skipped)
    logger.info("fac_songs: %d rows loaded", count)
    return count


# ── Post-load verification ────────────────────────────────────────────────────

def _row_counts(engine: Engine) -> dict[str, int]:
    tables = [
        "dim_artist", "dim_playlist", "dim_album", "dim_releasedate",
        "dim_date", "dim_songs", "bridge_song_artists", "fac_songs",
    ]
    with engine.connect() as conn:
        return {
            t: conn.execute(text(f"SELECT COUNT(*) FROM {t}")).fetchone()[0]
            for t in tables
        }


# ── Public API ────────────────────────────────────────────────────────────────

def load(
    transformed: dict[str, pd.DataFrame],
    env_path: str | Path | None = None,
) -> dict[str, int]:
    """
    Load all transformed DataFrames into MySQL.

    Args:
        transformed: Dict returned by pipeline.transform.transform().
        env_path:    Path to .env with DB_HOST/PORT/USER/PASSWORD/NAME.
                     Defaults to standard dotenv search.

    Returns:
        Dict mapping table name -> number of rows loaded in this call
        (not total DB count — use this to detect unexpected drops to zero).
    """
    logger.info("Load pipeline started")

    engine  = _create_engine(env_path)
    id_maps = _init_id_maps()

    counts: dict[str, int] = {}

    # ── Dimensions (independent of each other) ────────────────────────────────
    counts["dim_artist"]      = _load_artists(engine, transformed["dim_artist"], id_maps)
    counts["dim_playlist"]    = _load_playlists(engine, transformed["dim_playlist"], id_maps)
    counts["dim_album"]       = _load_albums(engine, transformed["dim_album"], id_maps)
    counts["dim_releasedate"] = _load_releasedates(engine, transformed["dim_releasedate"], id_maps)
    counts["dim_date"]        = _load_dates(engine, transformed["dim_date"], id_maps)

    # ── Range mappings from pre-populated tables ──────────────────────────────
    _load_range_mappings(engine, id_maps)

    # ── Songs (depends on nothing above for FK, but must precede bridge/fact) ─
    counts["dim_songs"] = _load_songs(engine, transformed["dim_songs"], id_maps)

    # ── Bridge and fact (depend on all dims above) ────────────────────────────
    counts["bridge_song_artists"] = _load_bridge(
        engine, transformed["bridge_song_artists"], id_maps
    )
    counts["fac_songs"] = _load_fact(engine, transformed["fac_songs"], id_maps)

    logger.info("Load complete — rows loaded: %s", counts)
    return counts, engine
