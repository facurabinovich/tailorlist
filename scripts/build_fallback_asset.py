"""
Rebuild data/audio_fallback.db into a compact release asset.

The original table is a rowid table plus a separate non-unique index on
spotify_id. Rebuilding it WITHOUT ROWID with spotify_id as the primary key
drops that second B-tree and the rowid indirection: 469 MB -> ~360 MB, with
identical table and column names, so spotify.reccobeats.fetch_fallback_features() reads
it unchanged.

Run once, locally, then upload the output as a GitHub Release asset and point
FALLBACK_DB_URL at it. Read-only on the source file.

    python scripts/build_fallback_asset.py [--src PATH] [--out PATH]
"""

import argparse
import os
import sqlite3
import sys
import time

_COLUMNS = (
    "spotify_id, danceability, energy, loudness, mode, speechiness, "
    "acousticness, instrumentalness, liveness, valence, tempo, duration_ms"
)

_SCHEMA = """
CREATE TABLE audio_features (
  spotify_id TEXT PRIMARY KEY,
  danceability REAL, energy REAL, loudness REAL, mode INTEGER,
  speechiness REAL, acousticness REAL, instrumentalness REAL,
  liveness REAL, valence REAL, tempo REAL, duration_ms INTEGER
) WITHOUT ROWID;
"""

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(_ROOT, "data", "audio_fallback.db"))
    ap.add_argument("--out", default=os.path.join(_ROOT, "data", "audio_fallback_compact.db"))
    ap.add_argument("--chunk", type=int, default=50_000)
    args = ap.parse_args()

    if not os.path.exists(args.src):
        sys.exit(f"ERROR: source not found: {args.src}")
    if os.path.exists(args.out):
        sys.exit(f"ERROR: output already exists, refusing to overwrite: {args.out}")

    src = sqlite3.connect(f"file:{args.src}?mode=ro", uri=True)
    expected = src.execute("SELECT COUNT(*) FROM audio_features").fetchone()[0]
    print(f"source: {args.src}  ({expected:,} rows, "
          f"{os.path.getsize(args.src) / 1024 / 1024:.1f} MB)")

    out = sqlite3.connect(args.out)
    out.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;" + _SCHEMA)

    t0 = time.time()
    # ORDER BY the primary key so inserts append in B-tree order — much less
    # page splitting than random order on a WITHOUT ROWID table.
    cur = src.execute(f"SELECT {_COLUMNS} FROM audio_features ORDER BY spotify_id")
    copied = 0
    while True:
        rows = cur.fetchmany(args.chunk)
        if not rows:
            break
        out.executemany(
            "INSERT OR IGNORE INTO audio_features VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows
        )
        copied += len(rows)
        print(f"\r  {copied:,} / {expected:,} rows", end="", flush=True)
    out.commit()
    print(f"\n  copied in {time.time() - t0:.0f}s")

    out.execute("VACUUM")
    actual = out.execute("SELECT COUNT(*) FROM audio_features").fetchone()[0]
    out.close()
    src.close()

    size = os.path.getsize(args.out)
    print(f"output: {args.out}  ({actual:,} rows, {size / 1024 / 1024:.1f} MB)")

    if actual != expected:
        sys.exit(f"ERROR: row count mismatch — source {expected:,}, output {actual:,}")
    print(f"OK — row counts match ({actual:,}). Upload this file as a release asset.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
