"""Single-playlist analysis behind the Playlist Detail page (no Streamlit, no session state, no plotting).

Pure functions that turn the collection DataFrame into everything the page shows for one
selected playlist: header KPIs, track highlights, averages, top artists, era breakdown, top
genres, mood map, growth over time, similar playlists and the full track table. Duplicates and
versions live in core.duplicates.

Conventions shared by every function:
  - The collection frame (df) has one row per (track, playlist) pair. Expected columns (all
    optional unless a function says otherwise): track_id, track_name, artist_name (primary
    artist), artist_display, playlist_name, popularity_raw (0-100), release_year, decade,
    duration_raw, added_at (date-like), artist_genres (comma-separated tags) and the audio
    features energy, acousticness, valence, danceability, speechiness, instrumentalness,
    liveness, tempo.
  - The playlist frame (pl_df) is the rows of one playlist as returned by playlist_tracks,
    where duration_raw is in MINUTES (the collection holds milliseconds).
  - af_avg is the per-playlist mean of the audio features (see playlist_audio_averages).
  - Inputs are never mutated. Nothing reads the clock or the session.
  - Missing columns give None / an empty DataFrame as documented on each function.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.formatting import fmt_duration

#: Audio feature columns averaged per playlist, in this order (only those present are used).
AUDIO_FEATURE_COLUMNS = ["energy", "acousticness", "valence", "danceability",
                         "speechiness", "instrumentalness", "liveness", "tempo"]

#: Features used to measure distance between playlists.
SIMILARITY_FEATURES = ["energy", "acousticness", "valence", "danceability", "instrumentalness", "tempo"]

#: Tempo range (BPM) mapped to 0-1 for radar charts and distances: (tempo - 60) / (200 - 60).
TEMPO_MIN_BPM = 60
TEMPO_MAX_BPM = 200


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HeaderKpis:
    """Headline numbers of one playlist.

    Attributes:
        total_tracks: rows of the playlist (a track saved twice counts twice).
        unique_artists: distinct primary artist names.
        followers: Spotify followers of the playlist (0 when unknown).
        first_added: earliest added_at as "Mon YYYY", or "N/A" without an added_at column.
        last_added: latest added_at as "Mon DD, YYYY", or "N/A" without an added_at column.
    """
    total_tracks: int
    unique_artists: int
    followers: int
    first_added: str
    last_added: str


@dataclass(frozen=True)
class TrackHighlights:
    """Standout tracks of a playlist; each is a full row (pd.Series) or None when not computable.

    Attributes:
        longest, shortest: by duration_raw (None without that column).
        most_popular, least_popular: by popularity_raw (None without that column).
        oldest, newest: by release_year ignoring missing years (None when there is no year).
        On ties the first row wins.
    """
    longest: pd.Series | None
    shortest: pd.Series | None
    most_popular: pd.Series | None
    least_popular: pd.Series | None
    oldest: pd.Series | None
    newest: pd.Series | None


@dataclass(frozen=True)
class PlaylistAverages:
    """Averages and the most frequent artist of a playlist.

    Attributes:
        avg_duration: mean duration_raw (minutes for a playlist frame); None without the column.
        avg_popularity: mean popularity_raw; None without the column.
        avg_release_year: mean release_year ignoring missing; None without the column (NaN
            when the column has no values).
        top_artist: primary artist with the most rows (first one on ties).
        top_artist_count: number of rows of top_artist.
    """
    avg_duration: float | None
    avg_popularity: float | None
    avg_release_year: float | None
    top_artist: str
    top_artist_count: int


@dataclass(frozen=True)
class TopArtists:
    """The most represented artists of a playlist.

    Attributes:
        table: DataFrame [artist, tracks] by tracks descending, at most n rows.
        covered_pct: percent (0-100) of the playlist's rows covered by those artists.
    """
    table: pd.DataFrame
    covered_pct: float


@dataclass(frozen=True)
class AudioComparison:
    """A playlist's audio averages next to the global ones.

    Attributes:
        playlist: the playlist's row of af_avg (Series indexed by playlist_name and features),
            or None when af_avg is empty or lacks the playlist.
        global_avg: mean of every numeric column of af_avg over all playlists (equal weight
            per playlist), or None under the same condition.
    """
    playlist: pd.Series | None
    global_avg: pd.Series | None


@dataclass(frozen=True)
class RadarProfile:
    """Values for the Audio DNA radar chart.

    Attributes:
        features: radar axes (CLUSTER_FEATURES present in af_avg).
        playlist_values, global_values: one value per axis; tempo is normalized to 0-1.
    """
    features: list[str]
    playlist_values: list[float]
    global_values: list[float]


@dataclass(frozen=True)
class PeakMonth:
    """The month with the most additions.

    Attributes:
        month: first day of the month.
        label: "Mon YYYY".
        count: tracks added that month.
    """
    month: pd.Timestamp
    label: str
    count: int


# ---------------------------------------------------------------------------
# Collection-level derivations
# ---------------------------------------------------------------------------

def playlist_audio_averages(df: pd.DataFrame) -> pd.DataFrame:
    """Mean audio features per playlist.

    Args:
        df: all (track, playlist) rows; needs playlist_name. Uses AUDIO_FEATURE_COLUMNS that exist.
    Returns:
        DataFrame [playlist_name, <features present>], one row per playlist, means over all
        its rows (a track repeated within a playlist counts each time). Empty DataFrame
        (no columns) when df has none of the features.
    """
    cols = [c for c in AUDIO_FEATURE_COLUMNS if c in df.columns]
    if not cols:
        return pd.DataFrame()
    return df.groupby("playlist_name")[cols].mean().reset_index()


def playlist_meta(df: pd.DataFrame, uc_playlists: list[dict]) -> pd.DataFrame:
    """Rows and followers per playlist.

    Args:
        df: all rows; needs playlist_name.
        uc_playlists: playlist records from the user's Spotify import, dicts with "name" and
            optionally "followers"; the first record with a matching name is used.
    Returns:
        DataFrame [playlist_name, total_tracks, followers]; followers is 0 for playlists not
        in uc_playlists or without a followers key.
    """
    meta = df.groupby("playlist_name").size().reset_index(name="total_tracks")
    meta["followers"] = meta["playlist_name"].apply(
        lambda name: next((p.get("followers", 0) for p in uc_playlists if p["name"] == name), 0)
    )
    return meta


def add_speechiness_log(af_avg: pd.DataFrame) -> pd.DataFrame:
    """Add speechiness_log = log1p(speechiness), the transform CLUSTER_FEATURES expects.

    Args:
        af_avg: per-playlist averages (see playlist_audio_averages).
    Returns:
        A copy with the extra column when af_avg is non-empty, has speechiness and has no
        speechiness_log yet (an existing one is never overwritten); otherwise af_avg itself.
    """
    if not af_avg.empty and "speechiness" in af_avg.columns and "speechiness_log" not in af_avg.columns:
        af_avg = af_avg.copy()
        af_avg["speechiness_log"] = np.log1p(af_avg["speechiness"])
    return af_avg


def playlist_tracks(df: pd.DataFrame, playlist: str) -> pd.DataFrame:
    """Rows of one playlist with duration converted to minutes.

    Args:
        df: all rows; needs playlist_name. duration_raw, when present, is milliseconds.
        playlist: exact playlist name.
    Returns:
        A copy of the playlist's rows (original index labels kept) where duration_raw is
        divided by 60000 (minutes), if the column exists.
    """
    pl_df = df[df["playlist_name"] == playlist].copy()
    if "duration_raw" in pl_df.columns:
        pl_df["duration_raw"] = pl_df["duration_raw"] / 60000
    return pl_df


def compare_audio(af_avg: pd.DataFrame, playlist: str) -> AudioComparison:
    """Pick a playlist's audio averages and the global averages.

    Args:
        af_avg: per-playlist averages (see playlist_audio_averages, optionally with
            speechiness_log from add_speechiness_log).
        playlist: exact playlist name.
    Returns:
        AudioComparison; both fields are None when af_avg is empty or does not contain the playlist.
    """
    if not af_avg.empty and playlist in af_avg["playlist_name"].values:
        return AudioComparison(
            af_avg[af_avg["playlist_name"] == playlist].iloc[0],
            af_avg.mean(numeric_only=True),
        )
    return AudioComparison(None, None)


def normalize_tempo(bpm: float) -> float:
    """Map tempo in BPM to roughly 0-1 using the 60-200 BPM range: (bpm - 60) / 140."""
    return (bpm - TEMPO_MIN_BPM) / (TEMPO_MAX_BPM - TEMPO_MIN_BPM)


def radar_profile(af_avg: pd.DataFrame, audio: AudioComparison, features: list[str]) -> RadarProfile | None:
    """Values for the playlist-vs-global radar chart.

    Args:
        af_avg: per-playlist averages (decides which features are available).
        audio: result of compare_audio for the selected playlist.
        features: wanted radar axes (e.g. CLUSTER_FEATURES); those missing from af_avg are dropped.
    Returns:
        RadarProfile with tempo normalized by normalize_tempo, or None when the playlist has
        no audio data (audio fields None, no feature available, or all its values NaN).
    """
    available = [f for f in features if f in af_avg.columns] if not af_avg.empty else []
    if audio.playlist is None or audio.global_avg is None or not available \
            or audio.playlist[available].isna().all():
        return None
    return RadarProfile(
        available,
        [audio.playlist[f] if f != "tempo" else normalize_tempo(audio.playlist[f]) for f in available],
        [audio.global_avg[f] if f != "tempo" else normalize_tempo(audio.global_avg[f]) for f in available],
    )


# ---------------------------------------------------------------------------
# Header, highlights, averages, top artists
# ---------------------------------------------------------------------------

def header_kpis(pl_df: pd.DataFrame, followers: int) -> HeaderKpis:
    """Header numbers of a playlist (see HeaderKpis).

    Args:
        pl_df: the playlist's rows; needs artist_name; added_at is optional.
        followers: follower count to report (from playlist_meta).
    Returns:
        HeaderKpis. first_added / last_added use the min / max of added_at as given (string
        or datetime), so ISO-like strings order correctly.
    """
    if "added_at" in pl_df.columns:
        first_added = pd.to_datetime(pl_df["added_at"].min()).strftime("%b %Y")
        last_added = pd.to_datetime(pl_df["added_at"].max()).strftime("%b %d, %Y")
    else:
        first_added = "N/A"
        last_added = "N/A"
    return HeaderKpis(len(pl_df), pl_df["artist_name"].nunique(), followers, first_added, last_added)


def track_highlights(pl_df: pd.DataFrame) -> TrackHighlights:
    """Longest/shortest, most/least popular and oldest/newest tracks of a playlist.

    Args:
        pl_df: the playlist's rows; duration_raw, popularity_raw and release_year are optional
            (each missing column leaves its pair as None). A present column with no values at
            all raises (idxmax of all-NaN), except release_year which is None.
    Returns:
        TrackHighlights.
    """
    longest = shortest = most_pop = least_pop = oldest = newest = None
    if "duration_raw" in pl_df.columns:
        longest = pl_df.loc[pl_df["duration_raw"].idxmax()]
        shortest = pl_df.loc[pl_df["duration_raw"].idxmin()]
    if "popularity_raw" in pl_df.columns:
        most_pop = pl_df.loc[pl_df["popularity_raw"].idxmax()]
        least_pop = pl_df.loc[pl_df["popularity_raw"].idxmin()]
    if "release_year" in pl_df.columns:
        years = pl_df["release_year"].dropna()
        if not years.empty:
            oldest = pl_df.loc[years.idxmin()]
            newest = pl_df.loc[years.idxmax()]
    return TrackHighlights(longest, shortest, most_pop, least_pop, oldest, newest)


def playlist_averages(pl_df: pd.DataFrame) -> PlaylistAverages:
    """Average duration, popularity and release year, plus the top artist (see PlaylistAverages).

    Args:
        pl_df: the playlist's rows (not empty); needs artist_name.
    Returns:
        PlaylistAverages. Raises IndexError for an empty playlist.
    """
    counts = pl_df["artist_name"].value_counts()
    return PlaylistAverages(
        avg_duration=pl_df["duration_raw"].mean() if "duration_raw" in pl_df.columns else None,
        avg_popularity=pl_df["popularity_raw"].mean() if "popularity_raw" in pl_df.columns else None,
        avg_release_year=pl_df["release_year"].dropna().mean() if "release_year" in pl_df.columns else None,
        top_artist=counts.index[0],
        top_artist_count=int(counts.iloc[0]),
    )


def top_artists(pl_df: pd.DataFrame, n: int = 5) -> TopArtists:
    """The n artists with the most rows in the playlist.

    Args:
        pl_df: the playlist's rows (not empty); needs artist_name.
        n: how many artists to keep.
    Returns:
        TopArtists. Ties keep first-appearance order.
    """
    table = pl_df["artist_name"].value_counts().head(n).reset_index()
    table.columns = ["artist", "tracks"]
    return TopArtists(table, table["tracks"].sum() / len(pl_df) * 100)


# ---------------------------------------------------------------------------
# Era breakdown, genres, mood map
# ---------------------------------------------------------------------------

def decade_counts(pl_df: pd.DataFrame) -> pd.DataFrame:
    """Rows per decade of a playlist.

    Args:
        pl_df: the playlist's rows; uses decade (missing values ignored).
    Returns:
        DataFrame [decade (int), count, label ("1990s")] ordered by decade ascending. Empty
        DataFrame (no columns) when decade is missing.
    """
    if "decade" not in pl_df.columns:
        return pd.DataFrame()
    counts = pl_df["decade"].dropna().astype(int).value_counts().sort_index().reset_index()
    counts.columns = ["decade", "count"]
    counts["label"] = counts["decade"].astype(str) + "s"
    return counts


def year_counts(pl_df: pd.DataFrame) -> pd.DataFrame:
    """Rows per release year of a playlist.

    Args:
        pl_df: the playlist's rows; uses release_year (missing values ignored).
    Returns:
        DataFrame [year (int), count] ordered by year ascending. Empty DataFrame (no columns)
        when release_year is missing.
    """
    if "release_year" not in pl_df.columns:
        return pd.DataFrame()
    counts = pl_df["release_year"].dropna().astype(int).value_counts().sort_index().reset_index()
    counts.columns = ["year", "count"]
    return counts


def decade_track_listing(pl_df: pd.DataFrame, decade: int) -> pd.DataFrame:
    """Tracks of one decade of a playlist, for the drill-down table.

    Args:
        pl_df: the playlist's rows; needs decade and track_name/artist_display/release_year
            (those present are shown); popularity_raw is optional.
        decade: decade start year, e.g. 1990.
    Returns:
        DataFrame [Track, Artist, Year, Popularity] (columns present only), by popularity
        descending when popularity_raw exists, with Year NaN shown as 0 (Int64). Index is
        kept from pl_df (reset it before display).
    """
    in_decade = pl_df[pl_df["decade"].astype("Int64") == decade]
    if "popularity_raw" in pl_df.columns:
        cols = [c for c in ["track_name", "artist_display", "release_year", "popularity_raw"] if c in pl_df.columns]
        tracks = in_decade[cols].copy().sort_values("popularity_raw", ascending=False)
    else:
        cols = [c for c in ["track_name", "artist_display", "release_year"] if c in pl_df.columns]
        tracks = in_decade[cols].copy()
    if "release_year" in tracks.columns:
        tracks["release_year"] = tracks["release_year"].fillna(0).astype("Int64")
    return tracks.rename(columns={
        "track_name": "Track", "artist_display": "Artist",
        "release_year": "Year", "popularity_raw": "Popularity",
    })


def top_genres(pl_df: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    """Most frequent genre tags of a playlist's rows.

    Each row's artist_genres is split on ", " and every tag is counted once per row (unlike
    core.overview.genre_track_counts, there is no sub-genre substring matching and no
    unique-track counting).

    Args:
        pl_df: the playlist's rows; needs artist_genres. Blank tags and missing values are ignored.
        n: how many genres to keep.
    Returns:
        DataFrame [genre, count] of the n most frequent genres sorted by count ASCENDING (so
        a horizontal chart shows the largest on top). Empty DataFrame (no columns) when
        artist_genres is missing.
    """
    if "artist_genres" not in pl_df.columns:
        return pd.DataFrame()
    tags = pl_df["artist_genres"].dropna().str.split(", ").explode().str.strip()
    tags = tags[tags != ""]
    top = tags.value_counts().head(n).reset_index()
    top.columns = ["genre", "count"]
    return top.sort_values("count")


def mood_map_available(pl_df: pd.DataFrame) -> bool:
    """Whether both energy and valence exist, i.e. the mood map can be drawn."""
    return "energy" in pl_df.columns and "valence" in pl_df.columns


def mood_map_points(pl_df: pd.DataFrame) -> pd.DataFrame:
    """Per-track points for the energy-vs-valence scatter.

    Args:
        pl_df: the playlist's rows; needs track_name and artist_display. Uses energy, valence
            and popularity_raw when present.
    Returns:
        DataFrame [track_name, artist_display, energy?, valence?, popularity_raw?] without rows
        that have any missing value among those columns. Check mood_map_available first.
    """
    audio = [c for c in ["energy", "valence"] if c in pl_df.columns]
    extra = ["popularity_raw"] if "popularity_raw" in pl_df.columns else []
    return pl_df[["track_name", "artist_display"] + audio + extra].dropna()


# ---------------------------------------------------------------------------
# Growth over time
# ---------------------------------------------------------------------------

def monthly_additions(pl_df: pd.DataFrame) -> pd.DataFrame:
    """Rows added per calendar month.

    Args:
        pl_df: the playlist's rows; uses added_at (date-like). Missing dates form a "NaT" period.
    Returns:
        DataFrame [period ("YYYY-MM"), count] ordered by period. Empty DataFrame (no columns)
        when added_at is missing.
    """
    if "added_at" not in pl_df.columns:
        return pd.DataFrame()
    monthly = (
        pl_df.assign(_month=pd.to_datetime(pl_df["added_at"]).dt.to_period("M").astype(str))
        .groupby("_month")
        .size()
        .reset_index(name="count")
    )
    monthly.columns = ["period", "count"]
    return monthly


def growth_timeline(monthly: pd.DataFrame) -> pd.DataFrame:
    """Add a datetime "month" column (first day of the month) to monthly_additions output.

    Args:
        monthly: DataFrame [period "YYYY-MM", count] with at least one row.
    Returns:
        A copy with columns [period, count, month].
    """
    out = monthly.copy()
    out.columns = ["period", "count"]
    out["month"] = pd.to_datetime(out["period"], format="%Y-%m")
    return out


def peak_month(timeline: pd.DataFrame) -> PeakMonth:
    """The month with the most additions (first one on ties).

    Args:
        timeline: output of growth_timeline (not empty).
    Returns:
        PeakMonth.
    """
    idx = timeline["count"].idxmax()
    month = timeline.loc[idx, "month"]
    return PeakMonth(month, month.strftime("%b %Y"), int(timeline.loc[idx, "count"]))


def single_session_date(pl_df: pd.DataFrame) -> str | None:
    """Date of the first non-missing added_at, for the "built in a single session" card.

    Args:
        pl_df: the playlist's rows.
    Returns:
        The date as "Month DD, YYYY", or None when added_at is missing or has no values.
    """
    if "added_at" in pl_df.columns and pl_df["added_at"].notna().any():
        return pd.to_datetime(pl_df["added_at"].dropna().iloc[0]).strftime("%B %d, %Y")
    return None


# ---------------------------------------------------------------------------
# Similar playlists
# ---------------------------------------------------------------------------

def similarity_features(af_avg: pd.DataFrame) -> list[str]:
    """SIMILARITY_FEATURES present in af_avg (empty list means similarity cannot be computed)."""
    return [f for f in SIMILARITY_FEATURES if f in af_avg.columns]


def similar_playlists(af_avg: pd.DataFrame, selected: str, n: int = 5) -> pd.DataFrame:
    """The n playlists closest to the selected one by Euclidean distance of audio averages.

    Tempo is normalized to 0-1 first (normalize_tempo) so it does not dominate.

    Args:
        af_avg: per-playlist averages; must contain the selected playlist (else IndexError).
        selected: exact playlist name.
        n: how many playlists to keep.
    Returns:
        The other playlists' af_avg rows (tempo normalized) plus a "distance" column, nearest
        first, fresh index. Empty DataFrame (no columns) when no similarity feature exists.
    """
    avail = similarity_features(af_avg)
    if not avail:
        return pd.DataFrame()
    af_norm = af_avg.copy()
    if "tempo" in af_norm.columns:
        af_norm["tempo"] = (af_norm["tempo"] - TEMPO_MIN_BPM) / (TEMPO_MAX_BPM - TEMPO_MIN_BPM)
    selected_vec = af_norm[af_norm["playlist_name"] == selected][avail].values[0]
    others = af_norm[af_norm["playlist_name"] != selected].copy()
    others["distance"] = others[avail].apply(
        lambda row: np.sqrt(np.sum((row.values - selected_vec) ** 2)), axis=1
    )
    return others.sort_values("distance").head(n).reset_index(drop=True)


def with_similarity_pct(similar: pd.DataFrame) -> pd.DataFrame:
    """Turn distances into a 0-100 similarity percentage and drop rows that round to 0.

    Args:
        similar: output of similar_playlists (has "distance").
    Returns:
        A copy with "similarity_pct" = (1 - distance / max distance) * 100, keeping only rows
        whose percentage rounds above 0, with a fresh index. The farthest playlist therefore
        always drops out, and if all distances are equal (max 0) everything drops out.
    """
    out = similar.copy()
    max_dist = out["distance"].max()
    out["similarity_pct"] = (1 - out["distance"] / max_dist) * 100
    return out[out["similarity_pct"].round() > 0].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Full track table
# ---------------------------------------------------------------------------

def track_table(pl_df: pd.DataFrame) -> pd.DataFrame:
    """The "All Tracks" table of a playlist, formatted for display.

    Args:
        pl_df: the playlist's rows (duration_raw in minutes); needs track_name and
            artist_display. Optional columns are shown when present: release_year,
            duration_raw, popularity_raw, energy, valence, danceability, acousticness.
    Returns:
        DataFrame with columns Track, Artist, Year, Duration ("m:ss"), Popularity (int),
        Energy, Valence, Danceability, Acousticness (those present, in that order); missing
        release_year shown as 0. Original index kept (reset it before display). A missing
        popularity_raw value raises (cannot cast to int).
    """
    cols = ["track_name", "artist_display"]
    cols += [c for c in ["release_year", "duration_raw", "popularity_raw"] if c in pl_df.columns]
    cols += [c for c in ["energy", "valence", "danceability", "acousticness"] if c in pl_df.columns]
    table = pl_df[cols].copy()
    if "duration_raw" in table.columns:
        table["duration_raw"] = table["duration_raw"].apply(fmt_duration)
    if "release_year" in table.columns:
        table["release_year"] = table["release_year"].fillna(0).astype("Int64")
    if "popularity_raw" in table.columns:
        table["popularity_raw"] = table["popularity_raw"].astype(int)
    return table.rename(columns={
        "track_name": "Track", "artist_display": "Artist", "release_year": "Year",
        "duration_raw": "Duration", "popularity_raw": "Popularity", "energy": "Energy",
        "valence": "Valence", "danceability": "Danceability", "acousticness": "Acousticness",
    })
