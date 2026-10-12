"""
Test suite for pages/4_Playlist_Comparison.py
Run with:  pytest tests/test_playlist_comparison.py -v
"""

import pandas as pd
import numpy as np
import pytest
from unittest.mock import patch

NORMALIZED_FEATURES = [
    "energy", "acousticness", "valence", "danceability",
    "speechiness", "instrumentalness", "liveness",
]

FEATURE_LABELS = {
    "energy":           ("⚡", "Most Energetic"),
    "acousticness":     ("🎸", "Most Acoustic"),
    "valence":          ("😄", "Happiest"),
    "danceability":     ("🕺", "Most Danceable"),
    "speechiness":      ("🎤", "Most Speechy"),
    "instrumentalness": ("🎹", "Most Instrumental"),
    "liveness":         ("🎪", "Most Live"),
}


# ---------------------------------------------------------------------------
# Helpers — mirrors pure logic from 4_Playlist_Comparison.py
# ---------------------------------------------------------------------------

from core.formatting import fmt_duration


def ranking_card_medal(rank: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")


def ranking_card_pct_str(pct: float) -> str:
    return f"{pct * 100:.1f}"


from core import comparison
from core.playlist_detail import playlist_audio_averages


def derive_meta_yc(uc_playlists: list) -> pd.DataFrame:
    return comparison.playlist_meta(uc_playlists)


def derive_af_avg_yc(df: pd.DataFrame) -> pd.DataFrame:
    return playlist_audio_averages(df)


def audio_feature_winner(af_avg: pd.DataFrame, feature: str) -> str:
    return {l.feature: l.playlist_name for l in comparison.feature_leaders(af_avg)}[feature]


def count_unique_genres(genres_series: pd.Series) -> int:
    return comparison.count_unique_genres(genres_series)


def compute_genre_diversity(df): return comparison.genre_diversity(df).reset_index(drop=True)
def compute_release_era(df): return comparison.release_era(df).reset_index(drop=True)
def compute_decade_dist(df): return comparison.decade_mix(df)
def compute_playlist_age(df): return comparison.playlist_age(df)
def compute_popularity_stats(df): return comparison.popularity_by_playlist(df)
def compute_pop_chart_range(pop): return comparison.popularity_axis_range(pop)


def compute_duration_stats(df):
    # the page feeds milliseconds; the fixture holds minutes, so scale it up
    return comparison.duration_by_playlist(df.assign(duration_raw=df["duration_raw"] * 60000))


def records_from_frame(df: pd.DataFrame) -> list:
    """Raw import records (id / name / artists / playlist_name) matching a collection frame."""
    return [
        {"id": r.track_id, "name": r.track_name, "artists": r.artist_display, "playlist_name": r.playlist_name}
        for r in df.itertuples()
    ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def multi_pl_df():
    """Two playlists, enough variety for all sections."""
    rows = []
    for pl, tracks in [
        ("PL1", [
            ("t1", "Song A", "ArtistX", "ArtistX", 80, 2000, 1990, 3.5, "rock, pop",   0.8, 0.2, 0.6, 0.7, 0.05, 0.01, 0.1, 120.0),
            ("t2", "Song B", "ArtistX", "ArtistX", 70, 2005, 2000, 4.0, "rock",         0.75,0.25,0.55,0.65,0.04, 0.02, 0.12,125.0),
            ("t3", "Song C", "ArtistY", "ArtistY", 60, 1995, 1990, 3.0, "indie",        0.7, 0.3, 0.5, 0.6, 0.06, 0.0,  0.15,118.0),
        ]),
        ("PL2", [
            ("t4", "Song D", "ArtistZ", "ArtistZ", 50, 2015, 2010, 5.0, "jazz, blues",  0.4, 0.7, 0.3, 0.5, 0.03, 0.2,  0.08, 95.0),
            ("t5", "Song E", "ArtistZ", "ArtistZ", 40, 2020, 2020, 2.5, "jazz",         0.35,0.75,0.25,0.45,0.02, 0.25, 0.07, 90.0),
            # t1 also in PL2 — cross-playlist duplicate
            ("t1", "Song A", "ArtistX", "ArtistX", 80, 2000, 1990, 3.5, "rock, pop",   0.8, 0.2, 0.6, 0.7, 0.05, 0.01, 0.1, 120.0),
        ]),
    ]:
        for (tid, name, artist, disp, pop, yr, dec, dur, genres,
             energy, acoust, val, dance, speech, instr, live, tempo) in tracks:
            rows.append({
                "track_id":       tid,
                "track_name":     name,
                "artist_name":    artist,
                "artist_display": disp,
                "playlist_name":  pl,
                "popularity_raw": pop,
                "release_year":   yr,
                "decade":         dec,
                "duration_raw":   dur,
                "added_at":       "2024-01-10" if pl == "PL1" else "2024-06-15",
                "artist_genres":  genres,
                "energy":         energy,
                "acousticness":   acoust,
                "valence":        val,
                "danceability":   dance,
                "speechiness":    speech,
                "instrumentalness": instr,
                "liveness":       live,
                "tempo":          tempo,
            })
    return pd.DataFrame(rows)


@pytest.fixture
def af_avg(multi_pl_df):
    return derive_af_avg_yc(multi_pl_df)


@pytest.fixture
def meta_df():
    return pd.DataFrame({
        "playlist_name": ["PL1", "PL2"],
        "total_tracks":  [10, 8],
        "followers":     [500, 200],
    })


# ---------------------------------------------------------------------------
# TC-01 – TC-04  fmt_duration
# ---------------------------------------------------------------------------

class TestFmtDuration:
    def test_normal(self):
        assert fmt_duration(3.5) == "3:30"

    def test_zero(self):
        assert fmt_duration(0.0) == "0:00"

    def test_zero_padded_seconds(self):
        assert fmt_duration(3 + 5 / 60) == "3:05"

    def test_whole_minutes(self):
        assert fmt_duration(4.0) == "4:00"


# ---------------------------------------------------------------------------
# TC-05 – TC-09  ranking_card logic
# ---------------------------------------------------------------------------

class TestRankingCard:
    def test_rank_1_medal(self):
        assert ranking_card_medal(1) == "🥇"

    def test_rank_2_medal(self):
        assert ranking_card_medal(2) == "🥈"

    def test_rank_3_medal(self):
        assert ranking_card_medal(3) == "🥉"

    def test_rank_4_fallback(self):
        assert ranking_card_medal(4) == "#4"

    def test_rank_10_fallback(self):
        assert ranking_card_medal(10) == "#10"

    def test_pct_str_format(self):
        # pct is 0-1 float → percentage string with 1 decimal
        assert ranking_card_pct_str(0.75) == "75.0"
        assert ranking_card_pct_str(1.0)  == "100.0"
        assert ranking_card_pct_str(0.0)  == "0.0"


# ---------------------------------------------------------------------------
# TC-10 – TC-13  YC mode derivations
# ---------------------------------------------------------------------------

class TestYcModeDerivations:
    def test_meta_yc_renames_columns(self):
        uc = [{"name": "PL1", "track_count": 10, "followers": 500}]
        meta = derive_meta_yc(uc)
        assert "playlist_name" in meta.columns
        assert "total_tracks"  in meta.columns

    def test_meta_yc_empty_list_returns_empty(self):
        meta = derive_meta_yc([])
        assert meta.empty

    def test_af_avg_yc_groups_by_playlist(self, multi_pl_df):
        af = derive_af_avg_yc(multi_pl_df)
        assert set(af["playlist_name"]) == {"PL1", "PL2"}

    def test_af_avg_yc_deduplicates_tracks(self):
        df = pd.DataFrame({
            "track_id":      ["t1", "t1", "t2"],
            "playlist_name": ["PL1", "PL2", "PL1"],
            "energy":        [0.8,   0.8,   0.6],
        })
        af = derive_af_avg_yc(df)
        pl1 = af[af["playlist_name"] == "PL1"]
        assert len(pl1) == 1

    def test_af_avg_yc_no_audio_cols_returns_empty(self):
        df = pd.DataFrame({"track_id": ["t1"], "playlist_name": ["PL1"]})
        af = derive_af_avg_yc(df)
        assert af.empty


# ---------------------------------------------------------------------------
# TC-14 – TC-18  Cross-playlist duplicate detection
# ---------------------------------------------------------------------------

class TestCrossPlaylistDupes:
    # The page detects duplicates by Spotify ID over the raw records (core.comparison), not by
    # name + artist as an earlier local mirror did; the cases below use records accordingly.

    def test_track_in_two_playlists_detected(self, multi_pl_df):
        dupes = comparison.exact_duplicates_across_playlists(records_from_frame(multi_pl_df))
        assert len(dupes) == 1
        assert dupes.iloc[0]["track_name"] == "Song A"

    def test_playlists_list_sorted(self, multi_pl_df):
        dupes = comparison.exact_duplicates_across_playlists(records_from_frame(multi_pl_df))
        assert dupes.iloc[0]["playlists"] == "PL1 · PL2"

    def test_track_in_one_playlist_not_in_dupes(self, multi_pl_df):
        dupes = comparison.exact_duplicates_across_playlists(records_from_frame(multi_pl_df))
        names = dupes["track_name"].tolist()
        assert "Song D" not in names
        assert "Song B" not in names

    def test_same_track_name_different_artist_not_duplicate(self):
        recs = [
            {"id": "1", "name": "Song X", "artists": "A", "playlist_name": "PL1"},
            {"id": "2", "name": "Song X", "artists": "B", "playlist_name": "PL2"},
        ]
        assert comparison.exact_duplicates_across_playlists(recs).empty
        assert comparison.different_versions_across_playlists(recs).empty

    def test_same_track_twice_in_same_playlist_is_listed(self):
        # The old name-based mirror said "not a cross-playlist dupe"; the page section is
        # "Exact Duplicates ... across or within playlists", so a within-playlist repeat IS listed.
        recs = [
            {"id": "1", "name": "Song X", "artists": "A", "playlist_name": "PL1"},
            {"id": "1", "name": "Song X", "artists": "A", "playlist_name": "PL1"},
        ]
        dupes = comparison.exact_duplicates_across_playlists(recs)
        assert len(dupes) == 1
        assert dupes.iloc[0]["playlists"] == "PL1 (×2)"

    def test_result_sorted_by_track_name(self):
        recs = [
            {"id": "z", "name": "Zebra", "artists": "X", "playlist_name": "PL1"},
            {"id": "z", "name": "Zebra", "artists": "X", "playlist_name": "PL2"},
            {"id": "a", "name": "Apple", "artists": "Y", "playlist_name": "PL1"},
            {"id": "a", "name": "Apple", "artists": "Y", "playlist_name": "PL2"},
        ]
        names = comparison.exact_duplicates_across_playlists(recs)["track_name"].tolist()
        assert names == ["Apple", "Zebra"]


# ---------------------------------------------------------------------------
# TC-19 – TC-22  Duration normalization & stats
# ---------------------------------------------------------------------------

class TestDurationSection:
    def test_yc_mode_converts_ms_to_minutes(self, multi_pl_df):
        df_ms = multi_pl_df.copy()
        df_ms["duration_raw"] = df_ms["duration_raw"] * 60000
        extremes = comparison.duration_extremes(df_ms)
        assert extremes.longest.minutes == pytest.approx(5.0)
        assert extremes.shortest.minutes == pytest.approx(2.5)

    def test_duration_stats_has_correct_columns(self, multi_pl_df):
        dur = compute_duration_stats(multi_pl_df)
        assert set(dur.columns) == {"playlist_name", "avg_min", "min_min", "max_min"}

    def test_longest_track_identified(self, multi_pl_df):
        longest = comparison.duration_extremes(multi_pl_df.assign(duration_raw=multi_pl_df["duration_raw"] * 60000)).longest
        assert longest.track_name == "Song D"

    def test_shortest_track_identified(self, multi_pl_df):
        shortest = comparison.duration_extremes(multi_pl_df.assign(duration_raw=multi_pl_df["duration_raw"] * 60000)).shortest
        assert shortest.track_name == "Song E"


# ---------------------------------------------------------------------------
# TC-23 – TC-27  Popularity section
# ---------------------------------------------------------------------------

class TestPopularitySection:
    def test_sorted_descending(self, multi_pl_df):
        pop = compute_popularity_stats(multi_pl_df)
        scores = pop["avg_popularity"].tolist()
        assert scores == sorted(scores, reverse=True)

    def test_most_popular_is_first(self, multi_pl_df):
        pop = compute_popularity_stats(multi_pl_df)
        assert pop.iloc[0]["playlist_name"] == "PL1"

    def test_least_popular_is_last(self, multi_pl_df):
        pop = compute_popularity_stats(multi_pl_df)
        assert pop.iloc[-1]["playlist_name"] == "PL2"

    def test_chart_range_y_min_clamps_to_zero(self):
        pop = pd.DataFrame({"avg_popularity": [3.0, 7.0]})
        y_min, _ = compute_pop_chart_range(pop)
        assert y_min == 0  # max(0, 3-5) = 0

    def test_chart_range_y_max_clamps_to_100(self):
        pop = pd.DataFrame({"avg_popularity": [95.0, 98.0]})
        _, y_max = compute_pop_chart_range(pop)
        assert y_max == 100  # min(100, 98+8) = 100

    def test_chart_range_normal_case(self):
        pop = pd.DataFrame({"avg_popularity": [40.0, 60.0]})
        y_min, y_max = compute_pop_chart_range(pop)
        assert y_min == 35.0  # 40 - 5
        assert y_max == 68.0  # 60 + 8


# ---------------------------------------------------------------------------
# TC-28 – TC-33  Audio Feature Leaders
# ---------------------------------------------------------------------------

class TestAudioFeatureLeaders:
    def test_highest_energy_playlist_wins(self, af_avg):
        # PL1 has energy ~0.75, PL2 ~0.375
        winner = audio_feature_winner(af_avg, "energy")
        assert winner == "PL1"

    def test_highest_acousticness_playlist_wins(self, af_avg):
        # PL2 has higher acousticness
        winner = audio_feature_winner(af_avg, "acousticness")
        assert winner == "PL2"

    def test_winner_is_idxmax(self, af_avg):
        for feat in ["energy", "valence", "danceability"]:
            if feat in af_avg.columns:
                winner = audio_feature_winner(af_avg, feat)
                max_val = af_avg[feat].max()
                assert af_avg.loc[af_avg["playlist_name"] == winner, feat].iloc[0] == max_val

    def test_available_items_filters_missing_features(self):
        af = pd.DataFrame({"playlist_name": ["PL1"], "energy": [0.8]})
        available = [(feat, m) for feat, m in FEATURE_LABELS.items() if feat in af.columns]
        assert len(available) == 1
        assert available[0][0] == "energy"

    def test_heatmap_feats_filtered_correctly(self, af_avg):
        heatmap_feats = [f for f in NORMALIZED_FEATURES if f in af_avg.columns]
        # All NORMALIZED_FEATURES should be present in our full mock
        assert len(heatmap_feats) >= 5


# ---------------------------------------------------------------------------
# TC-34 – TC-39  Genre diversity
# ---------------------------------------------------------------------------

class TestGenreDiversity:
    def test_unique_genres_counted(self):
        s = pd.Series(["rock, pop", "rock", "jazz"])
        assert count_unique_genres(s) == 3  # rock, pop, jazz

    def test_case_insensitive(self):
        s = pd.Series(["Rock", "rock", "ROCK"])
        assert count_unique_genres(s) == 1

    def test_nan_ignored(self):
        s = pd.Series([None, "rock"])
        assert count_unique_genres(s) == 1

    def test_empty_strings_excluded(self):
        s = pd.Series(["rock, ", ", pop", " "])
        assert count_unique_genres(s) == 2  # rock, pop

    def test_diversity_sorted_ascending(self, multi_pl_df):
        div = compute_genre_diversity(multi_pl_df)
        counts = div["unique_genres"].tolist()
        assert counts == sorted(counts)

    def test_most_diverse_is_last_after_sort(self, multi_pl_df):
        div = compute_genre_diversity(multi_pl_df)
        # PL1 has rock+pop+indie=3; PL2 has jazz+blues=2 → PL1 is most diverse
        assert div.iloc[-1]["unique_genres"] >= div.iloc[0]["unique_genres"]


# ---------------------------------------------------------------------------
# TC-40 – TC-44  Release era
# ---------------------------------------------------------------------------

class TestReleaseEra:
    def test_sorted_ascending_by_avg_year(self, multi_pl_df):
        release = compute_release_era(multi_pl_df)
        avgs = release["avg_release_year"].tolist()
        assert avgs == sorted(avgs)

    def test_most_nostalgic_is_first(self, multi_pl_df):
        release = compute_release_era(multi_pl_df)
        # PL1 has older tracks on average
        assert release.iloc[0]["avg_release_year"] <= release.iloc[-1]["avg_release_year"]

    def test_nan_release_years_excluded(self, multi_pl_df):
        df = multi_pl_df.copy()
        df.loc[0, "release_year"] = None
        release = compute_release_era(df)
        total_rows = release["playlist_name"].nunique()
        assert total_rows == 2  # still 2 playlists

    def test_min_max_year_per_playlist(self, multi_pl_df):
        release = compute_release_era(multi_pl_df)
        pl1 = release[release["playlist_name"] == "PL1"].iloc[0]
        pl1_years = multi_pl_df[multi_pl_df["playlist_name"] == "PL1"]["release_year"].dropna()
        assert pl1["min_year"] == pl1_years.min()
        assert pl1["max_year"] == pl1_years.max()

    def test_avg_year_correct(self, multi_pl_df):
        release = compute_release_era(multi_pl_df)
        pl1 = release[release["playlist_name"] == "PL1"].iloc[0]
        expected = multi_pl_df[multi_pl_df["playlist_name"] == "PL1"]["release_year"].dropna().mean()
        assert pl1["avg_release_year"] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# TC-45 – TC-48  Decade distribution
# ---------------------------------------------------------------------------

class TestDecadeDistribution:
    def test_decade_labels_formatted(self, multi_pl_df):
        dist = compute_decade_dist(multi_pl_df)
        for lbl in dist["decade_label"].unique():
            assert lbl.endswith("s")

    def test_nan_decades_excluded(self, multi_pl_df):
        df = multi_pl_df.copy()
        df.loc[0, "decade"] = None
        dist = compute_decade_dist(df)
        total_original = compute_decade_dist(multi_pl_df)["count"].sum()
        assert dist["count"].sum() == total_original - 1

    def test_all_playlists_present(self, multi_pl_df):
        dist = compute_decade_dist(multi_pl_df)
        assert set(dist["playlist_name"]) == {"PL1", "PL2"}

    def test_count_correct(self, multi_pl_df):
        dist = compute_decade_dist(multi_pl_df)
        pl1_1990s = dist[(dist["playlist_name"] == "PL1") & (dist["decade_label"] == "1990s")]
        # PL1 has t1 (decade=1990) and t3 (decade=1990); t2 has decade=2000
        assert int(pl1_1990s["count"].iloc[0]) == 2


# ---------------------------------------------------------------------------
# TC-49 – TC-53  Playlist age
# ---------------------------------------------------------------------------

class TestPlaylistAge:
    def test_sorted_ascending_by_first_added(self, multi_pl_df):
        age = compute_playlist_age(multi_pl_df)
        dates = age["first_added"].tolist()
        assert dates == sorted(dates)

    def test_earliest_playlist_is_first(self, multi_pl_df):
        age = compute_playlist_age(multi_pl_df)
        # PL1 was first added on 2024-01-10, PL2 on 2024-06-15
        assert age.iloc[0]["playlist_name"] == "PL1"

    def test_first_added_is_min_date_per_playlist(self, multi_pl_df):
        age = compute_playlist_age(multi_pl_df)
        for _, row in age.iterrows():
            pl_dates = pd.to_datetime(
                multi_pl_df[multi_pl_df["playlist_name"] == row["playlist_name"]]["added_at"]
            )
            assert row["first_added"] == pl_dates.min()

    def test_nan_dates_excluded(self, multi_pl_df):
        df = multi_pl_df.copy()
        df.loc[0, "added_at"] = None
        age = compute_playlist_age(df)
        # Both playlists still have at least one non-null date
        assert len(age) == 2

    def test_playlist_with_all_null_dates_absent(self):
        df = pd.DataFrame({
            "track_id":      ["t1", "t2"],
            "playlist_name": ["PL1", "PL1"],
            "added_at":      [None, None],
        })
        age = compute_playlist_age(df)
        assert age.empty


# ---------------------------------------------------------------------------
# TC-54 – TC-58  AppTest integration (requires streamlit >= 1.35)
# ---------------------------------------------------------------------------

try:
    from streamlit.testing.v1 import AppTest
    APPTEST_AVAILABLE = True
except ImportError:
    APPTEST_AVAILABLE = False


def _make_uc_playlists(followers=(500, 200)):
    """uc_playlists session records: the page builds its playlist metadata from them."""
    return [
        {"name": "PL1", "track_count": 10, "followers": followers[0]},
        {"name": "PL2", "track_count": 8, "followers": followers[1]},
    ]


def _yc_state(uc_playlists=None):
    return {
        "uc_active": True,
        "uc_playlists": uc_playlists if uc_playlists is not None else _make_uc_playlists(),
    }


def _make_full_mock_df():
    rows = []
    for pl, base_pop, base_date in [("PL1", 70, "2024-01-10"), ("PL2", 50, "2024-06-15")]:
        for i in range(4):
            rows.append({
                "track_id":       f"{pl}-t{i}",
                "track_name":     f"Song {pl} {i}",
                "artist_name":    f"Artist{i % 2}",
                "artist_display": f"Artist{i % 2}",
                "playlist_name":  pl,
                "popularity_raw": base_pop + i,
                "release_year":   2000 + i,
                "decade":         2000,
                "duration_raw":   int((3.5 + i * 0.1) * 60000),  # YC delivers milliseconds
                "added_at":       base_date,
                "artist_genres":  "rock, pop",
                **{f: 0.5 + i * 0.01 for f in NORMALIZED_FEATURES},
                "tempo":          120.0,
            })
    return pd.DataFrame(rows)


@pytest.mark.skipif(not APPTEST_AVAILABLE, reason="streamlit.testing not available")
class TestPlaylistComparisonPageRender:

    def _run_page(self, mock_df=None, session_state=None):
        if mock_df is None:
            mock_df = _make_full_mock_df()
        at = AppTest.from_file("pages/4_Playlist_Comparison.py", default_timeout=30)
        for k, v in {**_yc_state(), **(session_state or {})}.items():
            at.session_state[k] = v
        with patch("app_state.collection.get_all_tracks", return_value=mock_df), \
             patch("ui.theme.inject_global_css"), \
             patch("ui.nav.inject_sidebar_nav"), \
             patch("ui.nav.check_collection_mode", return_value=True), \
             patch("ui.theme.spotify_icon_html", return_value=""), \
             patch("ui.theme.page_brand_html", return_value=""):
            at.run()
        return at

    def test_TC54_page_renders_without_exception(self):
        at = self._run_page()
        assert not at.exception

    def test_TC55_single_playlist_shows_info_and_stops(self):
        single = _make_full_mock_df()
        single["playlist_name"] = "PL1"  # collapse to one playlist
        at = self._run_page(mock_df=single)
        assert not at.exception
        info_texts = [i.value for i in at.info]
        assert any("one playlist" in t.lower() for t in info_texts)

    def test_TC56_yc_mode_renders_without_exception(self):
        at = self._run_page(session_state={
            "uc_playlists": [
                {"name": "PL1", "track_count": 4, "followers": 100},
                {"name": "PL2", "track_count": 4, "followers": 50},
            ],
        })
        assert not at.exception

    def test_TC57_no_followers_renders_gracefully(self):
        at = AppTest.from_file("pages/4_Playlist_Comparison.py", default_timeout=30)
        for k, v in _yc_state(_make_uc_playlists(followers=(0, 0))).items():
            at.session_state[k] = v
        with patch("app_state.collection.get_all_tracks", return_value=_make_full_mock_df()), \
             patch("ui.theme.inject_global_css"), \
             patch("ui.nav.inject_sidebar_nav"), \
             patch("ui.nav.check_collection_mode", return_value=True), \
             patch("ui.theme.spotify_icon_html", return_value=""), \
             patch("ui.theme.page_brand_html", return_value=""):
            at.run()
        assert not at.exception

    def test_TC58_no_audio_features_renders_gracefully(self):
        df = _make_full_mock_df().drop(columns=NORMALIZED_FEATURES + ["tempo"], errors="ignore")
        at = AppTest.from_file("pages/4_Playlist_Comparison.py", default_timeout=30)
        for k, v in _yc_state().items():
            at.session_state[k] = v
        with patch("app_state.collection.get_all_tracks", return_value=df), \
             patch("ui.theme.inject_global_css"), \
             patch("ui.nav.inject_sidebar_nav"), \
             patch("ui.nav.check_collection_mode", return_value=True), \
             patch("ui.theme.spotify_icon_html", return_value=""), \
             patch("ui.theme.page_brand_html", return_value=""):
            at.run()
        assert not at.exception
