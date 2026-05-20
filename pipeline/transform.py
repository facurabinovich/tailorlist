"""
pipeline/transform.py
Transform extracted DataFrames into dimension/fact tables ready for loading.

Input:  playlist_df, songs_df, bridge_df, artists_df  (from pipeline/extract.py)
Output: dict[str, pd.DataFrame] keyed by table name

Tables produced:
  dim_playlist, dim_songs, dim_artist, dim_album,
  dim_releasedate, dim_date, bridge_song_artists, fac_songs

Note: dim_audio_features is NOT produced here — handled by enrich.py.
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


# ── Private helpers ───────────────────────────────────────────────────────────

def _fix_utf8(text: str) -> str:
    """Fix common Latin-1/UTF-8 mojibake that appears in Spanish text fields."""
    if not isinstance(text, str):
        return text
    replacements = {
        'Ã¡': 'á', 'Ã©': 'é', 'Ã­': 'í', 'Ã³': 'ó', 'Ãº': 'ú',
        'Ã±': 'ñ', 'Ã¼': 'ü', 'Ã ': 'à', 'Ã§': 'ç', 'Ã¢': 'â',
        'Ãª': 'ê', 'Ã®': 'î', 'Ã´': 'ô', 'Ã»': 'û', 'Ã': 'Á',
        'Ã‰': 'É', 'Ã"': 'Ó', 'Ãš': 'Ú', 'Ã': 'Ñ',
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text


def _fix_utf8_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for col in cols:
        if col in df.columns:
            df[col] = df[col].apply(_fix_utf8)
    return df


def _get_season(month: int) -> str:
    """Southern-hemisphere season from month number."""
    if 3 <= month <= 5:
        return 'Spring'
    elif 6 <= month <= 8:
        return 'Summer'
    elif 9 <= month <= 11:
        return 'Fall'
    else:
        return 'Winter'


# ── Step 1: Parse dates ───────────────────────────────────────────────────────

def _parse_release_date(val) -> pd.Timestamp:
    """
    Parse a single Spotify release_date value to Timestamp.
    Handles three Spotify precisions:
      "1985"       → 1985-01-01
      "2020-03"    → 2020-03-01
      "2020-03-15" → 2020-03-15
    """
    if pd.isna(val):
        return pd.NaT
    s = str(val).strip()
    try:
        if len(s) == 4:
            return pd.Timestamp(f"{s}-01-01")
        elif len(s) == 7:
            return pd.Timestamp(f"{s}-01")
        else:
            return pd.to_datetime(s, errors="coerce")
    except Exception:
        return pd.NaT


def _parse_dates(songs_df: pd.DataFrame) -> pd.DataFrame:
    """
    Parse ReleaseDate and AddedAt to datetime.
    ReleaseDate uses _parse_release_date to handle year-only ("1985") and
    month-year ("2020-03") strings that pd.to_datetime would silently drop.
    """
    df = songs_df.copy()
    if "ReleaseDate" in df.columns:
        df["ReleaseDate"] = df["ReleaseDate"].apply(_parse_release_date)
    if "AddedAt" in df.columns:
        df["AddedAt"] = pd.to_datetime(df["AddedAt"], errors="coerce")
    return df


# ── Step 2: Fix popularity outliers ──────────────────────────────────────────

def _fix_popularity_outliers(
    songs_df: pd.DataFrame,
    bridge_df: pd.DataFrame,
    artists_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Replace low-popularity outliers (IQR method) with the primary artist's
    median popularity across non-outlier songs. Falls back to 40 when no
    peer songs exist.

    Args:
        songs_df:   Raw songs DataFrame (column names from extract.py).
        bridge_df:  Song-artist bridge with IsPrimary boolean column.
        artists_df: Artists DataFrame with ArtistID and Name columns.

    Returns:
        (fixed_songs_df, report_df) where report_df documents each change.
    """
    df = songs_df.copy()

    q1 = df['Popularity'].quantile(0.25)
    q3 = df['Popularity'].quantile(0.75)
    lower_bound = q1 - 1.5 * (q3 - q1)

    outlier_mask = df['Popularity'] < lower_bound
    n_outliers = int(outlier_mask.sum())
    logger.info("Popularity outliers below %.1f: %d songs", lower_bound, n_outliers)

    if n_outliers == 0:
        return df, pd.DataFrame()

    # Join bridge (primary artists only) onto songs for quick artist lookup
    primary = bridge_df.loc[bridge_df['IsPrimary'] == True, ['SongID', 'ArtistID']].copy()
    songs_with_artist = df.merge(primary, on='SongID', how='left')

    fix_rows: list[dict] = []

    for _, song in df[outlier_mask].iterrows():
        sid = song['SongID']
        new_pop = 40
        fix_type = 'fallback_40'
        artist_name = 'Unknown'

        artist_row = songs_with_artist.loc[songs_with_artist['SongID'] == sid]

        if not artist_row.empty and pd.notna(artist_row.iloc[0].get('ArtistID')):
            aid = artist_row.iloc[0]['ArtistID']

            # Peer songs: same primary artist, not themselves an outlier
            peer_songs = songs_with_artist.loc[
                (songs_with_artist['ArtistID'] == aid) &
                (songs_with_artist['Popularity'] >= lower_bound)
            ]

            a_match = artists_df.loc[artists_df['ArtistID'] == aid]
            if not a_match.empty:
                artist_name = a_match.iloc[0]['Name']

            if not peer_songs.empty:
                new_pop = int(peer_songs['Popularity'].median())
                fix_type = 'artist_median'

        df.loc[df['SongID'] == sid, 'Popularity'] = new_pop
        fix_rows.append({
            'SongID': sid,
            'Name': song['Name'],
            'Playlist': song['Playlist'],
            'Artist': artist_name,
            'Old_Popularity': song['Popularity'],
            'New_Popularity': new_pop,
            'Fix_Type': fix_type,
        })

    report_df = pd.DataFrame(fix_rows)
    logger.info(
        "Outlier fixes: %d via artist_median, %d via fallback_40",
        (report_df['Fix_Type'] == 'artist_median').sum(),
        (report_df['Fix_Type'] == 'fallback_40').sum(),
    )
    return df, report_df


# ── Step 3: Individual table builders ─────────────────────────────────────────

def _build_dim_playlist(playlist_df: pd.DataFrame) -> pd.DataFrame:
    df = playlist_df.copy()
    df = _fix_utf8_cols(df, ['name', 'description', 'owner_name'])
    df = df.rename(columns={'playlist_id': 'spotify_id'})
    ordered = [
        'spotify_id', 'name', 'description', 'owner_id', 'owner_name',
        'is_public', 'is_collaborative', 'total_tracks', 'followers',
        'snapshot_id', 'is_personal',
    ]
    return df[[c for c in ordered if c in df.columns]]


def _build_dim_songs(songs_df: pd.DataFrame) -> pd.DataFrame:
    df = songs_df.copy()
    df = _fix_utf8_cols(df, ['Name', 'Album', 'AddedBy'])
    df = df.rename(columns={
        'Name': 'name',
        'SpotifyID': 'spotify_id',
        'IsLocal': 'is_local',
    })
    # has_audio_features defaults to False; enrich.py will backfill after enrichment
    df['has_audio_features'] = False
    ordered = ['SongID', 'name', 'spotify_id', 'is_local', 'has_audio_features']
    return df[[c for c in ordered if c in df.columns]]


def _build_dim_artist(artists_df: pd.DataFrame) -> pd.DataFrame:
    df = artists_df.copy()
    df = _fix_utf8_cols(df, ['Name', 'Genres'])
    df = df.rename(columns={
        'ArtistID': 'internal_id',
        'Name': 'name',
        'SpotifyID': 'spotify_id',
        'Popularity': 'popularity',
        'Genres': 'genres',
    })
    for col in ('popularity', 'genres', 'spotify_id'):
        if col not in df.columns:
            df[col] = None
    ordered = ['internal_id', 'name', 'spotify_id', 'popularity', 'genres']
    return df[[c for c in ordered if c in df.columns]]


def _build_bridge_song_artists(bridge_df: pd.DataFrame) -> pd.DataFrame:
    df = bridge_df.copy()
    return df.rename(columns={
        'SongID': 'dim_song_id',
        'ArtistID': 'dim_artist_id',
        'SpotifyArtistID': 'spotify_artist_id',
        'IsPrimary': 'is_primary',
        'ArtistOrder': 'artist_order',
    })


def _build_dim_album(songs_df: pd.DataFrame) -> pd.DataFrame:
    # One row per unique album name; take the first-seen release date
    albums = (
        songs_df[['Album', 'ReleaseDate']]
        .drop_duplicates(subset=['Album'])
        .copy()
    )
    albums = _fix_utf8_cols(albums, ['Album'])
    albums = albums.rename(columns={'Album': 'name', 'ReleaseDate': 'release_date'})
    albums['spotify_id'] = None  # populated later if enriched
    return albums[['name', 'spotify_id', 'release_date']]


def _build_dim_releasedate(songs_df: pd.DataFrame) -> pd.DataFrame:
    """Unique release dates with temporal attributes derived from ReleaseDate."""
    rows: list[dict] = []
    for raw in songs_df['ReleaseDate'].dropna().unique():
        try:
            d = pd.to_datetime(raw)
            rows.append({
                'full_date': d.date(),
                'year': d.year,
                'month': d.month,
                'day': d.day,
                'decade': (d.year // 10) * 10,
                'year_half': 1 if d.month <= 6 else 2,
                'quarter': (d.month - 1) // 3 + 1,
            })
        except Exception:
            logger.debug("Unparseable release date skipped: %r", raw)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates(subset=['full_date']).sort_values('full_date').reset_index(drop=True)
    return df


def _build_dim_date(songs_df: pd.DataFrame) -> pd.DataFrame:
    """Unique added-at dates with full temporal attributes derived from AddedAt."""
    rows: list[dict] = []
    for raw in songs_df['AddedAt'].dropna().unique():
        try:
            d = pd.to_datetime(raw)
            rows.append({
                'full_date': d.date(),
                'day_of_month': d.day,
                'month': d.month,
                'year': d.year,
                'day_of_week': d.dayofweek,
                'day_name': d.day_name(),
                'month_name': d.month_name(),
                'quarter': (d.month - 1) // 3 + 1,
                'year_month_str': d.strftime('%Y-%m'),
                'week_of_year': d.isocalendar()[1],
                'is_weekend': d.dayofweek >= 5,
                'is_holiday': False,
                'holiday_name': None,
                'season': _get_season(d.month),
                'day_of_year': d.dayofyear,
            })
        except Exception:
            logger.debug("Unparseable added_at date skipped: %r", raw)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates(subset=['full_date']).sort_values('full_date').reset_index(drop=True)
    return df


def _build_fac_songs(songs_df: pd.DataFrame) -> pd.DataFrame:
    """
    Fact table base: rename raw columns to their schema names.
    Foreign-key ID columns (dim_playlist_id, dim_album_id, etc.) are resolved
    at load time in pipeline/load.py once DB auto-increments are known.
    """
    return songs_df.rename(columns={
        'SongID': 'dim_song_id',
        'Playlist': 'playlist_name',
        'Album': 'album_name',
        'ReleaseDate': 'release_date',
        'AddedAt': 'added_at',
        'Popularity': 'popularity_raw',
        'Duration': 'duration_raw',
        'AddedBy': 'added_by',
    })


# ── Public API ────────────────────────────────────────────────────────────────

def transform(
    playlist_df: pd.DataFrame,
    songs_df: pd.DataFrame,
    bridge_df: pd.DataFrame,
    artists_df: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """
    Transform extracted DataFrames into dimension/fact tables.

    Steps:
      1. Parse date columns (ReleaseDate, AddedAt) to datetime.
      2. Fix low-popularity outliers via artist-median / fallback-40.
      3. Build each dimension and fact table with schema column names and
         UTF-8 mojibake corrections applied to all text fields.

    Args:
        playlist_df: From extract.extract_playlist_metadata().
        songs_df:    From extract.extract_tracks_and_artists()[0].
        bridge_df:   From extract.extract_tracks_and_artists()[1].
        artists_df:  From extract.extract_tracks_and_artists()[2].

    Returns:
        Dict with keys:
          dim_playlist, dim_songs, dim_artist, dim_album,
          dim_releasedate, dim_date, bridge_song_artists, fac_songs.

        dim_audio_features is intentionally absent — produced by enrich.py.
    """
    logger.info("Transform started")

    songs_df = _parse_dates(songs_df)
    songs_df, _outlier_report = _fix_popularity_outliers(songs_df, bridge_df, artists_df)

    builders = {
        'dim_playlist':       lambda: _build_dim_playlist(playlist_df),
        'dim_songs':          lambda: _build_dim_songs(songs_df),
        'dim_artist':         lambda: _build_dim_artist(artists_df),
        'bridge_song_artists': lambda: _build_bridge_song_artists(bridge_df),
        'dim_album':          lambda: _build_dim_album(songs_df),
        'dim_releasedate':    lambda: _build_dim_releasedate(songs_df),
        'dim_date':           lambda: _build_dim_date(songs_df),
        'fac_songs':          lambda: _build_fac_songs(songs_df),
    }

    tables: dict[str, pd.DataFrame] = {}
    for name, build_fn in builders.items():
        tables[name] = build_fn()
        logger.info("%s: %d rows", name, len(tables[name]))

    logger.info("Transform complete — %d tables produced", len(tables))
    return tables
