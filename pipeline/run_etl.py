"""
pipeline/run_etl.py
ETL orchestrator: extract → transform → load → enrich.

Usage:
    python -m pipeline.run_etl                  # full pipeline
    python -m pipeline.run_etl --skip-enrich    # extract/transform/load only
    python -m pipeline.run_etl --enrich-only    # ReccoBeats backfill only
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Logging setup (before any pipeline imports so all modules inherit it) ─────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("etl")

# ── Pipeline imports ──────────────────────────────────────────────────────────

from pipeline.extract import authenticate_spotify, load_playlists_config, \
    extract_playlist_metadata, extract_tracks_and_artists  # noqa: E402
from pipeline.transform import transform                                        # noqa: E402
from pipeline.load import load                                                  # noqa: E402
from pipeline.enrich import enrich                                              # noqa: E402

# ── Paths (relative to this file's directory) ─────────────────────────────────

_PIPELINE_DIR = Path(__file__).parent
_PROJECT_ROOT = _PIPELINE_DIR.parent
_ENV_PATH      = _PROJECT_ROOT / ".env"
_PLAYLISTS_CFG = _PROJECT_ROOT / "playlists.yaml"
_CACHE_PATH    = _PROJECT_ROOT / ".spotify_token_cache"

# Overridden by --config CLI arg
_active_playlists_cfg = _PLAYLISTS_CFG


# ── Stage runners ─────────────────────────────────────────────────────────────

def _run_extract() -> dict:
    """Authenticate, read config, pull data from Spotify API."""
    logger.info("── EXTRACT ──────────────────────────────────────────────────")

    sp        = authenticate_spotify(env_path=_ENV_PATH, cache_path=_CACHE_PATH)
    playlists = load_playlists_config(_active_playlists_cfg)

    playlist_df              = extract_playlist_metadata(sp, playlists)
    songs_df, bridge_df, artists_df = extract_tracks_and_artists(sp, playlists)

    summary = {
        "playlists": len(playlist_df),
        "songs":     len(songs_df),
        "bridge":    len(bridge_df),
        "artists":   len(artists_df),
    }
    logger.info("Extract summary: %s", summary)
    return {
        "summary":    summary,
        "playlist_df": playlist_df,
        "songs_df":    songs_df,
        "bridge_df":   bridge_df,
        "artists_df":  artists_df,
        "sp":          sp,
        "playlists":   playlists,
    }


def _run_transform(extract_result: dict) -> dict:
    """Apply all transformations; return dict of DataFrames keyed by table name."""
    logger.info("── TRANSFORM ────────────────────────────────────────────────")

    tables = transform(
        playlist_df = extract_result["playlist_df"],
        songs_df    = extract_result["songs_df"],
        bridge_df   = extract_result["bridge_df"],
        artists_df  = extract_result["artists_df"],
    )

    summary = {name: len(df) for name, df in tables.items()}
    logger.info("Transform summary: %s", summary)
    return {"summary": summary, "tables": tables}


def _run_load(transform_result: dict) -> dict:
    """Bulk-insert all tables into MySQL; return row-count summary and engine."""
    logger.info("── LOAD ─────────────────────────────────────────────────────")

    counts, engine = load(transform_result["tables"], env_path=_ENV_PATH)
    logger.info("Load summary: %s", counts)
    return {"counts": counts, "engine": engine}


def _run_sync(sp, playlists: dict, engine) -> dict:
    """
    Sync step: remove tracks and playlists from DB that no longer exist in Spotify.
    Runs after load, before enrich.
    """
    from sqlalchemy import text
    stats = {"deleted_tracks": 0, "deleted_playlists": 0, "orphaned_songs": 0}

    logger.info("── SYNC ─────────────────────────────────────────────────────────────")

    # ── 1. Playlists removed from YAML config ─────────────────────────────────
    yaml_playlist_names = set(playlists.keys())

    with engine.connect() as conn:
        db_playlists = conn.execute(text(
            "SELECT name FROM dim_playlist WHERE is_personal = TRUE"
        )).fetchall()
    db_playlist_names = {r[0] for r in db_playlists}

    removed_playlists = db_playlist_names - yaml_playlist_names
    if removed_playlists:
        logger.info("Playlists removed from config: %s", removed_playlists)
        for pl_name in removed_playlists:
            with engine.begin() as conn:
                result = conn.execute(text(
                    "DELETE FROM dim_playlist WHERE name = :name AND is_personal = TRUE"
                ), {"name": pl_name})
                stats["deleted_playlists"] += result.rowcount
                logger.info("  Deleted playlist: %s", pl_name)
    else:
        logger.info("No playlists removed from config.")

    # ── 2. Tracks removed from Spotify playlists ──────────────────────────────
    for pl_name, pl_info in playlists.items():
        pl_id  = pl_info["id"]             if isinstance(pl_info, dict) else pl_info
        market = pl_info.get("market", "US") if isinstance(pl_info, dict) else "US"

        # Fetch current track IDs from Spotify
        try:
            current_spotify_ids: set[str] = set()
            results = sp.playlist_tracks(
                pl_id,
                limit=100,
                market=market,
                fields="items(track(id)),next",
            )
            while results:
                for item in results.get("items", []):
                    track = item.get("track")
                    if track and track.get("id"):
                        current_spotify_ids.add(track["id"])
                results = sp.next(results) if results.get("next") else None
        except Exception:
            logger.exception(
                "Failed to fetch current tracks for playlist %s — skipping sync for this playlist",
                pl_name
            )
            continue

        # Fetch track IDs currently in DB for this playlist
        with engine.connect() as conn:
            db_rows = conn.execute(text("""
                SELECT s.spotify_id, fs.id AS fac_song_id
                FROM fac_songs fs
                JOIN dim_songs    s  ON fs.dim_song_id    = s.id
                JOIN dim_playlist pl ON fs.dim_playlist_id = pl.id
                WHERE pl.name = :pl_name
                  AND pl.is_personal = TRUE
            """), {"pl_name": pl_name}).fetchall()

        db_track_map = {r[0]: r[1] for r in db_rows}  # spotify_id -> fac_song_id
        removed_ids  = set(db_track_map.keys()) - current_spotify_ids

        if removed_ids:
            logger.info(
                "Playlist %s: %d track(s) removed from Spotify",
                pl_name, len(removed_ids)
            )
            for spotify_id in removed_ids:
                fac_song_id = db_track_map[spotify_id]
                with engine.begin() as conn:
                    conn.execute(text(
                        "DELETE FROM fac_songs WHERE id = :id"
                    ), {"id": fac_song_id})
                stats["deleted_tracks"] += 1
                logger.info("  Removed track spotify_id=%s from playlist %s", spotify_id, pl_name)
        else:
            logger.info("Playlist %s: no removed tracks.", pl_name)

    # ── 3. Orphaned dim_songs (no fac_songs row references them) ─────────────
    with engine.begin() as conn:
        result = conn.execute(text("""
            DELETE ds FROM dim_songs ds
            LEFT JOIN fac_songs fs ON fs.dim_song_id = ds.id
            WHERE fs.id IS NULL
              AND ds.is_local = 0
        """))
        stats["orphaned_songs"] = result.rowcount
        if stats["orphaned_songs"]:
            logger.info("Deleted %d orphaned dim_songs rows", stats["orphaned_songs"])

    logger.info(
        "Sync complete — deleted_tracks=%d  deleted_playlists=%d  orphaned_songs=%d",
        stats["deleted_tracks"], stats["deleted_playlists"], stats["orphaned_songs"]
    )
    return stats


def _run_enrich() -> dict:
    """Fetch ReccoBeats audio features for un-enriched tracks."""
    logger.info("── ENRICH ───────────────────────────────────────────────────")

    stats = enrich(env_path=_ENV_PATH)
    logger.info("Enrich summary: %s", stats)
    return stats


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Spotify ETL pipeline orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help="Path to playlists YAML config (default: playlists.yaml next to project root). "
             "Use playlists_demo.yaml to seed the demo/production collection.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--skip-enrich",
        action="store_true",
        help="Run extract / transform / load but skip ReccoBeats enrichment.",
    )
    group.add_argument(
        "--enrich-only",
        action="store_true",
        help="Skip extract / transform / load; only run ReccoBeats enrichment.",
    )
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="Skip the sync step (do not remove deleted tracks/playlists from DB).",
    )
    return parser.parse_args()


def main() -> None:
    global _active_playlists_cfg
    args       = _parse_args()
    if args.config:
        _active_playlists_cfg = Path(args.config).resolve()
        logger.info("Using playlists config: %s", _active_playlists_cfg)
    started_at = datetime.now()
    t0         = time.monotonic()

    logger.info("═" * 60)
    logger.info("ETL pipeline started at %s", started_at.strftime("%Y-%m-%d %H:%M:%S"))
    logger.info(
        "Mode: %s",
        "enrich-only" if args.enrich_only
        else "skip-enrich" if args.skip_enrich
        else "full",
    )
    logger.info("═" * 60)

    try:
        if not args.enrich_only:
            # ── Extract ───────────────────────────────────────────────────────
            t_stage = time.monotonic()
            extract_result = _run_extract()
            logger.info("Extract completed in %.1fs", time.monotonic() - t_stage)

            # ── Transform ─────────────────────────────────────────────────────
            t_stage = time.monotonic()
            transform_result = _run_transform(extract_result)
            logger.info("Transform completed in %.1fs", time.monotonic() - t_stage)

            # ── Load ──────────────────────────────────────────────────────────
            t_stage = time.monotonic()
            load_result = _run_load(transform_result)
            engine   = load_result["engine"]
            sp       = extract_result["sp"]
            playlists = extract_result["playlists"]
            logger.info("Load completed in %.1fs", time.monotonic() - t_stage)

            # ── Sync ──────────────────────────────────────────────────────────
            if not args.skip_sync:
                t_stage = time.monotonic()
                sync_result = _run_sync(
                    sp        = extract_result["sp"],
                    playlists = extract_result["playlists"],
                    engine    = load_result["engine"],
                )
                logger.info(
                    "Sync — deleted_tracks=%d  deleted_playlists=%d  orphaned_songs=%d",
                    sync_result["deleted_tracks"],
                    sync_result["deleted_playlists"],
                    sync_result["orphaned_songs"],
                )
                logger.info("Sync completed in %.1fs", time.monotonic() - t_stage)

        if not args.skip_enrich:
            # ── Enrich ────────────────────────────────────────────────────────
            t_stage = time.monotonic()
            _run_enrich()
            logger.info("Enrich completed in %.1fs", time.monotonic() - t_stage)

    except Exception:
        elapsed = time.monotonic() - t0
        logger.exception("Pipeline failed after %.1fs — exiting with code 1", elapsed)
        sys.exit(1)

    elapsed    = time.monotonic() - t0
    ended_at   = datetime.now()
    logger.info("═" * 60)
    logger.info("ETL pipeline finished at %s", ended_at.strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("Total elapsed: %.1fs", elapsed)
    logger.info("═" * 60)


if __name__ == "__main__":
    main()
