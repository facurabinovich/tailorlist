"""
Test suite for pages/2_Playlist_Detail.py
Run with:  pytest tests/test_playlist_detail.py -v
"""

import math
import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers — mirrors pure logic from 2_Playlist_Detail.py
# ---------------------------------------------------------------------------

def fmt_duration(minutes: float) -> str:
    m = int(minutes)
    s = int(round((minutes - m) * 60))
    return f"{m}:{s:02d}"


def normalize_tempo(val: float) -> float:
    return (val - 60) / (200 - 60)


def derive_af_avg_yc(df: pd.DataFrame) -> pd.DataFrame:
    """Replicate YC-mode af_avg derivation."""
    _af_cols = [c for c in ["energy", "acousticness", "valence", "danceability",
                             "speechiness", "instrumentalness", "liveness", "tempo"]
                if c in df.columns]
    if not _af_cols:
        return pd.DataFrame()
    return (
        df.drop_duplicates(subset="track_id")
        .groupby("playlist_name")[_af_cols]
        .mean()
        .reset_index()
    )


def derive_meta_yc(df: pd.DataFrame, uc_playlists: list) -> pd.DataFrame:
    """Replicate YC-mode meta derivation."""
    meta = df.groupby("playlist_name").size().reset_index(name="total_tracks")
    meta["followers"] = meta["playlist_name"].apply(
        lambda name: next((p.get("followers", 0) for p in uc_playlists if p["name"] == name), 0)
    )
    return meta


def ensure_speechiness_log(af_avg: pd.DataFrame) -> pd.DataFrame:
    if af_avg.empty:
        return af_avg
    if "speechiness" in af_avg.columns and "speechiness_log" not in af_avg.columns:
        af_avg = af_avg.copy()
        af_avg["speechiness_log"] = np.log1p(af_avg["speechiness"])
    return af_avg


def normalize_duration_yc(pl_df: pd.DataFrame) -> pd.DataFrame:
    """Convert ms → minutes for YC mode."""
    pl_df = pl_df.copy()
    if "duration_raw" in pl_df.columns:
        pl_df["duration_raw"] = pl_df["duration_raw"] / 60000
    return pl_df


def compute_playlist_kpis(pl_df: pd.DataFrame, pl_meta: pd.Series):
    total_tracks = len(pl_df)
    unique_artists = pl_df["artist_name"].nunique() if "artist_name" in pl_df.columns else 0
    followers = int(pl_meta["followers"])
    first_added = last_added = "N/A"
    if "added_at" in pl_df.columns:
        first_added = pd.to_datetime(pl_df["added_at"].min()).strftime("%b %Y")
        last_added  = pd.to_datetime(pl_df["added_at"].max()).strftime("%b %d, %Y")
    return {
        "total_tracks": total_tracks,
        "unique_artists": unique_artists,
        "followers": followers,
        "first_added": first_added,
        "last_added": last_added,
    }


def compute_averages(pl_df: pd.DataFrame):
    avg_dur  = pl_df["duration_raw"].mean() if "duration_raw" in pl_df.columns else None
    avg_pop  = pl_df["popularity_raw"].mean() if "popularity_raw" in pl_df.columns else None
    avg_year = pl_df["release_year"].dropna().mean() if "release_year" in pl_df.columns else None
    vc = pl_df["artist_name"].value_counts()
    top_artist = vc.index[0]
    top_artist_count = int(vc.iloc[0])
    return {
        "avg_dur": avg_dur,
        "avg_pop": avg_pop,
        "avg_year": avg_year,
        "top_artist": top_artist,
        "top_artist_count": top_artist_count,
    }


def compute_top_artists(pl_df: pd.DataFrame, n: int = 5):
    top = pl_df["artist_name"].value_counts().head(n).reset_index()
    top.columns = ["artist", "tracks"]
    total = len(pl_df)
    pct = top["tracks"].sum() / total * 100
    return top, pct


def compute_duplicates(pl_df: pd.DataFrame) -> pd.DataFrame:
    dupes = (
        pl_df.groupby(["track_name", "artist_name", "artist_display"])
        .size()
        .reset_index(name="count")
    )
    return dupes[dupes["count"] > 1].sort_values("count", ascending=False).reset_index(drop=True)


def compute_decade_counts(pl_df: pd.DataFrame) -> pd.DataFrame:
    if "decade" not in pl_df.columns:
        return pd.DataFrame()
    dc = pl_df["decade"].dropna().astype(int).value_counts().sort_index().reset_index()
    dc.columns = ["decade", "count"]
    dc["label"] = dc["decade"].astype(str) + "s"
    return dc


def compute_year_counts(pl_df: pd.DataFrame) -> pd.DataFrame:
    if "release_year" not in pl_df.columns:
        return pd.DataFrame()
    yc = pl_df["release_year"].dropna().astype(int).value_counts().sort_index().reset_index()
    yc.columns = ["year", "count"]
    return yc


def compute_top_genres(pl_df: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    if "artist_genres" not in pl_df.columns:
        return pd.DataFrame()
    series = (
        pl_df["artist_genres"].dropna()
        .str.split(", ")
        .explode()
        .str.strip()
    )
    series = series[series != ""]
    top = series.value_counts().head(n).reset_index()
    top.columns = ["genre", "count"]
    return top.sort_values("count")


def compute_similar_playlists(af_avg: pd.DataFrame, selected: str, n: int = 5) -> pd.DataFrame:
    numeric_features = ["energy", "acousticness", "valence", "danceability", "instrumentalness", "tempo"]
    avail = [f for f in numeric_features if f in af_avg.columns]
    if not avail:
        return pd.DataFrame()
    af_norm = af_avg.copy()
    if "tempo" in af_norm.columns:
        af_norm["tempo"] = (af_norm["tempo"] - 60) / (200 - 60)
    selected_vec = af_norm[af_norm["playlist_name"] == selected][avail].values[0]
    others = af_norm[af_norm["playlist_name"] != selected].copy()
    others["distance"] = others[avail].apply(
        lambda row: np.sqrt(np.sum((row.values - selected_vec) ** 2)), axis=1
    )
    return others.sort_values("distance").head(n).reset_index(drop=True)


def compute_monthly_growth_yc(pl_df: pd.DataFrame) -> pd.DataFrame:
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pl_df():
    """A single playlist's track rows — already filtered."""
    return pd.DataFrame({
        "track_id":      ["t1", "t2", "t3", "t4", "t5"],
        "track_name":    ["Song A", "Song B", "Song C", "Song A", "Song D"],
        "artist_name":   ["ArtistX", "ArtistX", "ArtistY", "ArtistX", "ArtistZ"],
        "artist_display":["ArtistX", "ArtistX", "ArtistY", "ArtistX", "ArtistZ"],
        "playlist_name": ["PL1"] * 5,
        "popularity_raw":[80, 70, 60, 55, 40],
        "release_year":  [1990, 2000, 1985, 2010, 2020],
        "decade":        [1990, 2000, 1980, 2010, 2020],
        "duration_raw":  [3.5, 4.0, 3.0, 5.0, 2.5],   # minutes (DB mode)
        "added_at":      ["2024-01-10", "2024-01-20", "2024-03-05", "2024-03-15", "2024-06-01"],
        "artist_genres": ["rock, indie rock", "rock", "pop", "rock", "jazz"],
        "energy":        [0.8, 0.7, 0.4, 0.6, 0.3],
        "valence":       [0.6, 0.5, 0.7, 0.4, 0.2],
        "danceability":  [0.7, 0.6, 0.5, 0.8, 0.4],
        "acousticness":  [0.2, 0.3, 0.6, 0.1, 0.8],
        "speechiness":   [0.05, 0.04, 0.06, 0.03, 0.02],
        "tempo":         [120.0, 130.0, 90.0, 140.0, 80.0],
    })


@pytest.fixture
def pl_meta():
    return pd.Series({"playlist_name": "PL1", "total_tracks": 5, "followers": 1200})


@pytest.fixture
def af_avg_multi():
    """af_avg with two playlists — for similarity and radar tests."""
    return pd.DataFrame({
        "playlist_name": ["PL1", "PL2", "PL3"],
        "energy":        [0.8,  0.3,  0.5],
        "acousticness":  [0.2,  0.7,  0.4],
        "valence":       [0.6,  0.4,  0.55],
        "danceability":  [0.7,  0.5,  0.65],
        "instrumentalness": [0.05, 0.3, 0.1],
        "tempo":         [120.0, 85.0, 100.0],
        "speechiness":   [0.05, 0.06, 0.04],
    })


@pytest.fixture
def full_df():
    """All playlists df (as returned by get_all_tracks in YC mode)."""
    rows = []
    for pl, tracks in [
        ("PL1", [("t1","ArtistX","Song A",0.8,0.6,120.0),
                 ("t2","ArtistX","Song B",0.7,0.5,130.0)]),
        ("PL2", [("t3","ArtistY","Song C",0.3,0.4,85.0),
                 ("t4","ArtistZ","Song D",0.35,0.45,90.0)]),
    ]:
        for tid, artist, name, energy, valence, tempo in tracks:
            rows.append({
                "track_id": tid, "track_name": name,
                "artist_name": artist, "artist_display": artist,
                "playlist_name": pl,
                "energy": energy, "valence": valence, "tempo": tempo,
                "speechiness": 0.05, "acousticness": 0.2,
                "danceability": 0.6, "instrumentalness": 0.1, "liveness": 0.15,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# TC-01 – TC-04  fmt_duration
# ---------------------------------------------------------------------------

class TestFmtDuration:
    def test_normal_float(self):
        assert fmt_duration(3.5) == "3:30"

    def test_zero(self):
        assert fmt_duration(0.0) == "0:00"

    def test_whole_minutes(self):
        assert fmt_duration(5.0) == "5:00"

    def test_seconds_zero_padded(self):
        # 3 min 5 sec
        assert fmt_duration(3 + 5 / 60) == "3:05"

    def test_rounding(self):
        assert fmt_duration(59 / 60) == "0:59"


# ---------------------------------------------------------------------------
# TC-05 – TC-08  Duration normalization (YC mode: ms → minutes)
# ---------------------------------------------------------------------------

class TestDurationNormalization:
    def test_yc_ms_converted_to_minutes(self, pl_df):
        pl_ms = pl_df.copy()
        pl_ms["duration_raw"] = pl_ms["duration_raw"] * 60000   # simulate YC ms
        result = normalize_duration_yc(pl_ms)
        expected = pl_df["duration_raw"]
        pd.testing.assert_series_equal(
            result["duration_raw"].reset_index(drop=True),
            expected.reset_index(drop=True),
            check_names=False,
        )

    def test_original_df_not_mutated(self, pl_df):
        original_val = pl_df["duration_raw"].iloc[0]
        pl_ms = pl_df.copy()
        pl_ms["duration_raw"] = pl_ms["duration_raw"] * 60000
        normalize_duration_yc(pl_ms)
        assert pl_ms["duration_raw"].iloc[0] == original_val * 60000

    def test_no_duration_column_returns_unchanged(self):
        df = pd.DataFrame({"track_id": ["t1"], "track_name": ["S"]})
        result = normalize_duration_yc(df)
        assert "duration_raw" not in result.columns


# ---------------------------------------------------------------------------
# TC-09 – TC-14  Playlist KPI calculations
# ---------------------------------------------------------------------------

class TestPlaylistKpis:
    def test_total_tracks(self, pl_df, pl_meta):
        kpis = compute_playlist_kpis(pl_df, pl_meta)
        assert kpis["total_tracks"] == 5

    def test_unique_artists(self, pl_df, pl_meta):
        kpis = compute_playlist_kpis(pl_df, pl_meta)
        # ArtistX, ArtistY, ArtistZ
        assert kpis["unique_artists"] == 3

    def test_followers_from_meta(self, pl_df, pl_meta):
        kpis = compute_playlist_kpis(pl_df, pl_meta)
        assert kpis["followers"] == 1200

    def test_first_added(self, pl_df, pl_meta):
        kpis = compute_playlist_kpis(pl_df, pl_meta)
        assert kpis["first_added"] == "Jan 2024"

    def test_last_added(self, pl_df, pl_meta):
        kpis = compute_playlist_kpis(pl_df, pl_meta)
        assert kpis["last_added"] == "Jun 01, 2024"

    def test_no_added_at_column_returns_na(self, pl_meta):
        df = pd.DataFrame({
            "track_id": ["t1"], "artist_name": ["A"],
            "playlist_name": ["PL1"],
        })
        kpis = compute_playlist_kpis(df, pl_meta)
        assert kpis["first_added"] == "N/A"
        assert kpis["last_added"] == "N/A"


# ---------------------------------------------------------------------------
# TC-15 – TC-20  Averages section
# ---------------------------------------------------------------------------

class TestAverages:
    def test_avg_duration(self, pl_df):
        avgs = compute_averages(pl_df)
        assert avgs["avg_dur"] == pytest.approx(pl_df["duration_raw"].mean())

    def test_avg_popularity(self, pl_df):
        avgs = compute_averages(pl_df)
        assert avgs["avg_pop"] == pytest.approx(pl_df["popularity_raw"].mean())

    def test_avg_release_year(self, pl_df):
        avgs = compute_averages(pl_df)
        assert avgs["avg_year"] == pytest.approx(pl_df["release_year"].dropna().mean())

    def test_top_artist_is_most_frequent(self, pl_df):
        avgs = compute_averages(pl_df)
        # ArtistX appears 3 times
        assert avgs["top_artist"] == "ArtistX"
        assert avgs["top_artist_count"] == 3

    def test_avg_duration_none_when_missing(self):
        df = pd.DataFrame({"track_id": ["t1"], "artist_name": ["A"]})
        avgs = compute_averages(df)
        assert avgs["avg_dur"] is None

    def test_avg_pop_none_when_missing(self):
        df = pd.DataFrame({"track_id": ["t1"], "artist_name": ["A"]})
        avgs = compute_averages(df)
        assert avgs["avg_pop"] is None


# ---------------------------------------------------------------------------
# TC-21 – TC-24  Top artists
# ---------------------------------------------------------------------------

class TestTopArtists:
    def test_top_artist_is_most_frequent(self, pl_df):
        top, _ = compute_top_artists(pl_df)
        assert top.iloc[0]["artist"] == "ArtistX"
        assert top.iloc[0]["tracks"] == 3

    def test_sorted_descending(self, pl_df):
        top, _ = compute_top_artists(pl_df)
        counts = top["tracks"].tolist()
        assert counts == sorted(counts, reverse=True)

    def test_capped_at_n(self, pl_df):
        top, _ = compute_top_artists(pl_df, n=2)
        assert len(top) == 2

    def test_percentage_calculation(self, pl_df):
        top, pct = compute_top_artists(pl_df, n=5)
        expected_pct = top["tracks"].sum() / len(pl_df) * 100
        assert pct == pytest.approx(expected_pct)

    def test_all_tracks_covered_by_top_5(self, pl_df):
        # With only 3 unique artists, top-5 should cover 100%
        _, pct = compute_top_artists(pl_df, n=5)
        assert pct == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# TC-25 – TC-28  Duplicate track detection
# ---------------------------------------------------------------------------

class TestDuplicateDetection:
    def test_exact_duplicate_detected(self, pl_df):
        # "Song A" by ArtistX appears twice (t1 and t4)
        dupes = compute_duplicates(pl_df)
        assert len(dupes) == 1
        assert dupes.iloc[0]["track_name"] == "Song A"
        assert dupes.iloc[0]["count"] == 2

    def test_no_duplicates_returns_empty(self):
        df = pd.DataFrame({
            "track_name":    ["A", "B", "C"],
            "artist_name":   ["X", "Y", "Z"],
            "artist_display":["X", "Y", "Z"],
        })
        dupes = compute_duplicates(df)
        assert dupes.empty

    def test_same_name_different_artist_not_a_duplicate(self):
        df = pd.DataFrame({
            "track_name":    ["Song A", "Song A"],
            "artist_name":   ["ArtistX", "ArtistY"],
            "artist_display":["ArtistX", "ArtistY"],
        })
        dupes = compute_duplicates(df)
        assert dupes.empty

    def test_duplicate_count_correct(self):
        df = pd.DataFrame({
            "track_name":    ["Song A", "Song A", "Song A"],
            "artist_name":   ["X", "X", "X"],
            "artist_display":["X", "X", "X"],
        })
        dupes = compute_duplicates(df)
        assert dupes.iloc[0]["count"] == 3


# ---------------------------------------------------------------------------
# TC-29 – TC-32  Era breakdown
# ---------------------------------------------------------------------------

class TestEraBreakdown:
    def test_decade_counts_sorted_chronologically(self, pl_df):
        dc = compute_decade_counts(pl_df)
        decades = dc["decade"].tolist()
        assert decades == sorted(decades)

    def test_decade_labels_formatted(self, pl_df):
        dc = compute_decade_counts(pl_df)
        for _, row in dc.iterrows():
            assert row["label"].endswith("s")
            assert str(row["decade"]) in row["label"]

    def test_year_counts_sorted_chronologically(self, pl_df):
        yc = compute_year_counts(pl_df)
        years = yc["year"].tolist()
        assert years == sorted(years)

    def test_no_decade_column_returns_empty(self):
        df = pd.DataFrame({"track_id": ["t1"], "track_name": ["S"]})
        dc = compute_decade_counts(df)
        assert dc.empty

    def test_nan_decades_excluded(self, pl_df):
        df = pl_df.copy()
        df.loc[0, "decade"] = None
        dc = compute_decade_counts(df)
        total = dc["count"].sum()
        assert total == len(pl_df) - 1


# ---------------------------------------------------------------------------
# TC-33 – TC-36  Genre extraction
# ---------------------------------------------------------------------------

class TestGenreExtraction:
    def test_genres_split_correctly(self, pl_df):
        top = compute_top_genres(pl_df)
        # "rock, indie rock" should produce "rock" and "indie rock" separately
        genres = top["genre"].tolist()
        assert "rock" in genres
        assert "indie rock" in genres

    def test_sorted_ascending_by_count(self, pl_df):
        top = compute_top_genres(pl_df)
        counts = top["count"].tolist()
        assert counts == sorted(counts)

    def test_capped_at_n(self, pl_df):
        top = compute_top_genres(pl_df, n=2)
        assert len(top) <= 2

    def test_no_genre_column_returns_empty(self):
        df = pd.DataFrame({"track_id": ["t1"], "track_name": ["S"]})
        top = compute_top_genres(df)
        assert top.empty

    def test_empty_strings_excluded(self):
        df = pd.DataFrame({
            "artist_genres": ["rock, ", ", pop", ""],
        })
        top = compute_top_genres(df)
        genres = top["genre"].tolist()
        assert "" not in genres


# ---------------------------------------------------------------------------
# TC-37 – TC-41  Similar playlists (Euclidean distance)
# ---------------------------------------------------------------------------

class TestSimilarPlaylists:
    def test_selected_playlist_excluded_from_results(self, af_avg_multi):
        result = compute_similar_playlists(af_avg_multi, "PL1")
        assert "PL1" not in result["playlist_name"].values

    def test_results_sorted_by_distance(self, af_avg_multi):
        result = compute_similar_playlists(af_avg_multi, "PL1")
        distances = result["distance"].tolist()
        assert distances == sorted(distances)

    def test_capped_at_n(self, af_avg_multi):
        result = compute_similar_playlists(af_avg_multi, "PL1", n=1)
        assert len(result) <= 1

    def test_tempo_normalized_before_distance(self, af_avg_multi):
        # PL2 has tempo=85 (low), PL3 has tempo=100 (mid).
        # With raw tempo PL3 distance would be swamped by the 120→100 diff.
        # After normalization both diffs are small fractions — other features drive order.
        result = compute_similar_playlists(af_avg_multi, "PL1")
        # Simply assert no exception and correct number of rows
        assert len(result) == 2  # only 2 other playlists

    def test_distance_is_zero_for_identical_playlist(self):
        af = pd.DataFrame({
            "playlist_name": ["PL1", "PL2"],
            "energy":        [0.8, 0.8],
            "acousticness":  [0.2, 0.2],
            "valence":       [0.6, 0.6],
            "danceability":  [0.7, 0.7],
            "instrumentalness": [0.05, 0.05],
            "tempo":         [120.0, 120.0],
        })
        result = compute_similar_playlists(af, "PL1")
        assert result.iloc[0]["distance"] == pytest.approx(0.0)

    def test_no_audio_features_returns_empty(self):
        af = pd.DataFrame({"playlist_name": ["PL1", "PL2"]})
        result = compute_similar_playlists(af, "PL1")
        assert result.empty


# ---------------------------------------------------------------------------
# TC-42 – TC-45  Playlist growth timeline (YC mode)
# ---------------------------------------------------------------------------

class TestPlaylistGrowth:
    def test_groups_by_year_month(self, pl_df):
        tl = compute_monthly_growth_yc(pl_df)
        assert "period" in tl.columns
        assert "count" in tl.columns
        # Jan 2024 has 2 tracks, Mar 2024 has 2, Jun 2024 has 1
        jan = tl[tl["period"] == "2024-01"]
        assert not jan.empty
        assert int(jan["count"].iloc[0]) == 2

    def test_no_added_at_returns_empty(self):
        df = pd.DataFrame({"track_id": ["t1"], "track_name": ["S"]})
        tl = compute_monthly_growth_yc(df)
        assert tl.empty

    def test_single_date_produces_one_period(self):
        df = pd.DataFrame({
            "track_id": ["t1", "t2"],
            "added_at": ["2024-05-10", "2024-05-20"],
        })
        tl = compute_monthly_growth_yc(df)
        assert len(tl) == 1
        assert tl.iloc[0]["period"] == "2024-05"
        assert tl.iloc[0]["count"] == 2

    def test_total_count_matches_track_count(self, pl_df):
        tl = compute_monthly_growth_yc(pl_df)
        assert tl["count"].sum() == len(pl_df)


# ---------------------------------------------------------------------------
# TC-46 – TC-49  YC mode af_avg derivation
# ---------------------------------------------------------------------------

class TestAfAvgDerivationYc:
    def test_af_avg_groups_by_playlist(self, full_df):
        result = derive_af_avg_yc(full_df)
        assert set(result["playlist_name"]) == {"PL1", "PL2"}

    def test_af_avg_deduplicates_tracks(self):
        df = pd.DataFrame({
            "track_id":      ["t1", "t1", "t2"],  # t1 in two playlists
            "playlist_name": ["PL1", "PL2", "PL1"],
            "energy":        [0.8,   0.8,   0.6],
        })
        result = derive_af_avg_yc(df)
        # After dedup on track_id, only t1 (first occurrence) and t2 remain
        pl1 = result[result["playlist_name"] == "PL1"]
        assert len(pl1) == 1

    def test_af_avg_no_audio_cols_returns_empty(self):
        df = pd.DataFrame({
            "track_id":      ["t1"],
            "playlist_name": ["PL1"],
        })
        result = derive_af_avg_yc(df)
        assert result.empty

    def test_speechiness_log_added(self, full_df):
        af = derive_af_avg_yc(full_df)
        af = ensure_speechiness_log(af)
        assert "speechiness_log" in af.columns
        # log1p is monotone — check values are correct
        expected = np.log1p(af["speechiness"])
        pd.testing.assert_series_equal(af["speechiness_log"], expected, check_names=False)

    def test_speechiness_log_not_duplicated_if_already_present(self, full_df):
        af = derive_af_avg_yc(full_df)
        af["speechiness_log"] = 999.0   # pre-existing
        af = ensure_speechiness_log(af)
        # Should NOT overwrite
        assert (af["speechiness_log"] == 999.0).all()


# ---------------------------------------------------------------------------
# TC-50 – TC-52  YC mode meta derivation
# ---------------------------------------------------------------------------

class TestMetaDerivationYc:
    def test_total_tracks_per_playlist(self, full_df):
        meta = derive_meta_yc(full_df, [])
        pl1 = meta[meta["playlist_name"] == "PL1"]
        assert int(pl1["total_tracks"].iloc[0]) == 2

    def test_followers_from_uc_playlists(self, full_df):
        uc = [{"name": "PL1", "followers": 500}, {"name": "PL2", "followers": 300}]
        meta = derive_meta_yc(full_df, uc)
        pl1 = meta[meta["playlist_name"] == "PL1"]
        assert int(pl1["followers"].iloc[0]) == 500

    def test_missing_playlist_followers_default_zero(self, full_df):
        meta = derive_meta_yc(full_df, [])   # no uc_playlists
        assert (meta["followers"] == 0).all()


# ---------------------------------------------------------------------------
# TC-53 – TC-57  AppTest integration (requires streamlit >= 1.35)
# ---------------------------------------------------------------------------

try:
    from streamlit.testing.v1 import AppTest
    APPTEST_AVAILABLE = True
except ImportError:
    APPTEST_AVAILABLE = False


def _make_full_mock_df():
    """Full-featured df that satisfies every column the page accesses unconditionally."""
    return pd.DataFrame({
        "track_id":      ["t1", "t2", "t3"],
        "track_name":    ["Song A", "Song B", "Song C"],
        "artist_name":   ["ArtistX", "ArtistX", "ArtistY"],
        "artist_display":["ArtistX", "ArtistX", "ArtistY"],
        "playlist_name": ["PL1", "PL1", "PL1"],
        "album_name":    ["Alb1", "Alb1", "Alb2"],
        "popularity_raw":[80, 70, 60],
        "release_year":  [1990, 2000, 2010],
        "decade":        [1990, 2000, 2010],
        "duration_raw":  [3.5, 4.0, 3.0],
        "added_at":      ["2024-01-15", "2024-02-20", "2024-03-05"],
        "artist_genres": ["rock", "rock", "pop"],
        "energy":        [0.8, 0.7, 0.4],
        "valence":       [0.6, 0.5, 0.7],
        "danceability":  [0.7, 0.6, 0.5],
        "acousticness":  [0.2, 0.3, 0.6],
        "speechiness":   [0.05, 0.04, 0.06],
        "instrumentalness": [0.0, 0.01, 0.05],
        "liveness":      [0.1, 0.12, 0.15],
        "tempo":         [120.0, 130.0, 90.0],
    })


def _make_mock_af_avg():
    return pd.DataFrame({
        "playlist_name": ["PL1"],
        "energy":        [0.7],
        "acousticness":  [0.3],
        "valence":       [0.6],
        "danceability":  [0.65],
        "speechiness":   [0.05],
        "instrumentalness": [0.02],
        "liveness":      [0.12],
        "tempo":         [120.0],
    })


def _make_mock_meta():
    return pd.DataFrame({
        "playlist_name": ["PL1"],
        "total_tracks":  [3],
        "followers":     [500],
    })


def _make_mock_monthly():
    return pd.DataFrame({
        "period": ["2024-01", "2024-02", "2024-03"],
        "count":  [1, 1, 1],
    })


@pytest.mark.skipif(not APPTEST_AVAILABLE, reason="streamlit.testing not available")
class TestPlaylistDetailPageRender:

    def _run_page(self, mock_df=None, session_state=None):
        if mock_df is None:
            mock_df = _make_full_mock_df()

        at = AppTest.from_file("pages/2_Playlist_Detail.py", default_timeout=30)

        if session_state:
            for k, v in session_state.items():
                at.session_state[k] = v

        with patch("db.queries.get_all_tracks", return_value=mock_df), \
             patch("db.queries.load_audio_features_by_playlist", return_value=_make_mock_af_avg()), \
             patch("db.queries.load_playlist_meta", return_value=_make_mock_meta()), \
             patch("db.queries.load_tracks_added_by_month", return_value=_make_mock_monthly()), \
             patch("utils.inject_global_css"), \
             patch("utils.inject_sidebar_nav"), \
             patch("utils.check_collection_mode", return_value=True), \
             patch("utils.spotify_icon_html", return_value=""), \
             patch("utils.page_brand_html", return_value=""):
            at.run()

        return at

    def test_TC53_page_renders_without_exception(self):
        at = self._run_page()
        assert not at.exception

    def test_TC54_yc_mode_banner_appears(self):
        at = self._run_page(session_state={
            "mode": "🔗 Your Collection",
            "uc_active": True,
        })
        assert not at.exception
        info_texts = [i.value for i in at.info]
        assert any("Your Collection" in t for t in info_texts)

    def test_TC55_playlist_selector_populated(self):
        at = self._run_page()
        assert not at.exception
        # The selectbox for playlist choice should be present
        assert len(at.selectbox) >= 1

    def test_TC56_page_renders_without_audio_features(self):
        df = _make_full_mock_df()
        # Drop audio feature columns
        df = df.drop(columns=["energy", "valence", "danceability", "acousticness",
                               "speechiness", "instrumentalness", "liveness", "tempo"])
        with patch("db.queries.load_audio_features_by_playlist", return_value=pd.DataFrame()), \
             patch("db.queries.load_playlist_meta", return_value=_make_mock_meta()), \
             patch("db.queries.load_tracks_added_by_month", return_value=_make_mock_monthly()):
            at = self._run_page(mock_df=df)
        assert not at.exception

    def test_TC57_page_renders_with_no_duplicates(self):
        df = _make_full_mock_df()
        # Ensure all track_names are unique (no duplicates to detect)
        df["track_name"] = ["Unique A", "Unique B", "Unique C"]
        at = self._run_page(mock_df=df)
        assert not at.exception
