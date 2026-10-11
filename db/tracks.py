import pandas as pd
import streamlit as st
from db.connection import get_engine
# Pure helper lives in core/tracks.py; kept under its old private name for the loaders below.
from core.tracks import add_artist_display as _add_artist_display



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


@st.cache_data
def load_tracks_deduped() -> pd.DataFrame:
    """Unique tracks only (keep first occurrence per spotify_id)."""
    df = load_tracks()
    return df.drop_duplicates(subset="track_id").reset_index(drop=True)

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


