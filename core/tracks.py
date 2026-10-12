"""Pure track-frame logic (no Streamlit): release-year parsing, artist display and
the normalization of in-session "Your Collection" (YC) records into a DataFrame."""
from __future__ import annotations

import pandas as pd

from core.grouping import release_date_to_decade

# Raw Spotify/enrichment field -> canonical column used by every page.
YC_COLUMN_RENAMES: dict[str, str] = {
    "id":          "track_id",
    "name":        "track_name",
    "artists":     "artist_name",
    "popularity":  "popularity_raw",
    "album":       "album_name",
    "duration_ms": "duration_raw",
}


def parse_release_year(release_date_series: pd.Series) -> pd.Series:
    """
    Robustly extract year from Spotify release_date which can be:
    - "2014"          (year only)
    - "2014-03"       (year-month)
    - "2014-03-15"    (full date)
    Empty/missing values and implausible years (<= 1900) become None.
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


def add_artist_display(df: pd.DataFrame) -> pd.DataFrame:
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


def yc_tracks_frame(
    enriched: list[dict],
    skipped: list[dict] | None = None,
    failed: list[dict] | None = None,
    *,
    include_unenriched: bool,
) -> pd.DataFrame:
    """Tracks DataFrame from Your Collection session records.

    enriched rows have audio features; skipped/failed rows do not. With
    include_unenriched=False only `enriched` is used (audio-feature pages);
    with True skipped and failed rows are appended (count/stat pages).
    Columns are renamed to the canonical names, release_year/decade derived
    from release_date, and artist_display added.
    """
    enriched_df = pd.DataFrame(enriched)
    frames = [enriched_df]

    if include_unenriched:
        skipped_df = pd.DataFrame(skipped if skipped is not None else [])
        failed_df = pd.DataFrame(failed if failed is not None else [])

        # Skipped/failed tracks carry real Spotify IDs — keep them.
        # Only generate a synthetic id for rows that genuinely lack one (defensive
        # fallback for any very old session data written before id was stored).
        for _df in [skipped_df, failed_df]:
            if not _df.empty and "id" not in _df.columns:
                _df["id"] = _df["name"] + "||" + _df.get("artists", pd.Series(dtype=str)).fillna("")

        if not skipped_df.empty:
            frames.append(skipped_df)
        if not failed_df.empty:
            frames.append(failed_df)

    df = pd.concat(frames, ignore_index=True) if include_unenriched else enriched_df
    df = df.rename(columns=YC_COLUMN_RENAMES)

    if "release_date" in df.columns:
        df["release_year"] = parse_release_year(df["release_date"])
        df["decade"] = (df["release_year"] // 10 * 10).where(df["release_year"].notna())
    return add_artist_display(df)


_CLUSTER_BASE_COLS = [
    "track_id", "track_name", "artist_name", "artist_display", "playlist_name",
    "speechiness", "artist_genres", "decade", "release_year",
]


def cluster_pool_frame(df: pd.DataFrame, cluster_features: list[str]) -> pd.DataFrame:
    """Columns My Clusters needs from a YC tracks frame, one row per track_id.

    Keeps the base columns plus the cluster features (except the derived
    ``speechiness_log``) that exist in ``df``, then drops repeated track ids (first wins).
    """
    feature_cols = [f for f in cluster_features if f != "speechiness_log"]
    available = [c for c in _CLUSTER_BASE_COLS + feature_cols if c in df.columns]
    return df[available].drop_duplicates(subset="track_id")


def yc_unmatched_frame(skipped: list[dict], failed: list[dict],
                       include_decade: bool = False) -> pd.DataFrame:
    """Tracks of the user's collection that had no audio features (skipped + failed).

    One row per raw record (no dedup), with ``release_year`` as the first 4 characters of
    ``release_date`` and an ``artist_display`` column. With include_decade=True a
    ``decade`` column (int or None, see release_date_to_decade) follows release_year.
    Empty input gives an empty frame with the same columns.
    """
    rows = []
    for t in skipped + failed:
        row = {
            "track_id":      t.get("id", ""),
            "track_name":    t.get("name", ""),
            "artist_name":   ", ".join(t.get("artists", [])) if isinstance(t.get("artists"), list) else t.get("artists", ""),
            "release_year":  t.get("release_date", "")[:4] if t.get("release_date") else "",
        }
        if include_decade:
            row["decade"] = release_date_to_decade(t.get("release_date", "") or "")
        row["artist_genres"] = t.get("artist_genres", "")
        row["playlist_name"] = t.get("playlist_name", "")
        rows.append(row)
    columns = ["track_id", "track_name", "artist_name", "release_year",
               *(["decade"] if include_decade else []), "artist_genres", "playlist_name"]
    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=columns)
    return add_artist_display(df)
