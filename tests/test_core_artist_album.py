"""Characterization of core.artist_album on a small fixed frame (values verified against the
pre-T21 inline logic of pages/3_Artist_Album.py; tests/test_artist_album.py has the broader scenarios)."""
import numpy as np
import pandas as pd
import pytest

from core import artist_album as aa


@pytest.fixture
def df():
    # X: 5 rows / 4 tracks (t1 in two playlists), album "Hits" 3 tracks, "Solo" 1 track. Y: 2 tracks.
    return pd.DataFrame({
        "track_id":       ["t1", "t1", "t2", "t3", "t4", "t5", "t6"],
        "track_name":     ["A", "A", "B", "C", "D", "E", "F"],
        "artist_name":    ["X", "X", "X", "X", "X", "Y", "Y"],
        "artist_display": ["X", "X", "X", "X", "X", "Y", "Y feat. Q"],
        "album_name":     ["Hits", "Hits", "Hits", "Hits", "Solo", "Hits", "Other"],
        "playlist_name":  ["P1", "P2", "P1", "P1", "P2", "P1", "P1"],
        "popularity_raw": [80.0, 80.0, 60.0, np.nan, 40.0, 10.0, 20.0],
        "release_year":   [1990.0, 1990.0, 2000.0, np.nan, 2010.0, 1990.0, 2020.0],
        "duration_raw":   [180000.0, 180000.0, 240000.0, np.nan, 60000.0, 90000.0, 120000.0],
        "artist_genres":  ["rock, indie", "rock, indie", "rock", None, "pop", "jazz", "jazz"],
        "energy":         [0.8, 0.8, 0.6, np.nan, 0.2, 0.5, 0.4],
        "valence":        [0.5, 0.5, 0.4, np.nan, 0.3, 0.2, 0.1],
        "danceability":   [0.7, 0.7, 0.6, np.nan, 0.5, 0.4, 0.3],
        "tempo":          [100.0, 100.0, 120.0, np.nan, 140.0, 60.0, 180.0],
    })


def test_constants():
    assert (aa.MIN_TRACKS_ARTIST, aa.MIN_TRACKS_ALBUM, aa.POPULARITY_BIN_SIZE) == (5, 3, 5)


def test_artist_choices_counts_rows(df):
    c = aa.artist_choices(df)
    assert c.options_raw == ["X"] and c.options == ["🏆 #1 · X"]
    assert c.top_default == "X" and c.rank_map == {"X": 1} and c.pairs is None


def test_artist_choices_empty_and_threshold(df):
    c = aa.artist_choices(df, min_tracks=6)
    assert c.options_raw == [] and c.top_default is None and c.rank_map == {}
    assert aa.artist_choices(df, min_tracks=2).options_raw == ["X", "Y"]


def test_album_choices_pairs_use_unique_tracks(df):
    c = aa.album_choices(df)
    assert c.options_raw == ["Hits — X"]  # t1 twice counts once: 3 unique; Hits — Y has 1; Solo 1
    assert c.pairs.to_dict("records") == [{"label": "Hits — X", "album_name": "Hits", "artist_name": "X", "n": 3}]
    assert c.top_default == "Hits — X" and c.options == ["🏆 #1 · Hits — X"]
    assert aa.album_pair(c, "Hits — X") == ("Hits", "X")


def test_album_choices_missing_column_and_empty(df):
    assert aa.album_choices(df.drop(columns=["album_name"])) is None
    c = aa.album_choices(df, min_tracks=99)
    assert c.options_raw == [] and c.top_default is None and len(c.pairs) == 0


def test_default_option_index(df):
    c = aa.album_choices(df, min_tracks=1)  # Hits — X, Hits — Y, Other — Y, Solo — X
    assert c.options_raw == ["Hits — X", "Hits — Y", "Other — Y", "Solo — X"]
    assert aa.default_option_index(c) == 0
    assert aa.default_option_index(c, "Other — Y") == 2
    assert aa.default_option_index(c, "nothing") == 0


def test_artist_rows_dedups_per_playlist_and_adds_minutes(df):
    sel = aa.artist_rows(df, "X")
    assert len(sel) == 5  # (t1,P1) (t1,P2) t2 t3 t4
    assert sel.loc[sel["track_id"] == "t2", "duration_min"].iloc[0] == pytest.approx(4.0)
    assert "duration_min" not in df.columns  # input untouched
    dup = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    assert len(aa.artist_rows(dup, "X")) == 5


def test_album_rows_and_no_duration(df):
    sel = aa.album_rows(df.drop(columns=["duration_raw"]), "Hits", "X")
    assert sorted(sel["track_id"]) == ["t1", "t1", "t2", "t3"]
    assert "duration_min" not in sel.columns


def test_selection_kpis(df):
    k = aa.selection_kpis(aa.artist_rows(df, "X"), aa.MIN_TRACKS_ARTIST)
    assert (k.track_count, k.playlist_count, k.enough) == (4, 2, False)
    k = aa.selection_kpis(aa.album_rows(df, "Hits", "X"), aa.MIN_TRACKS_ALBUM)
    assert (k.track_count, k.playlist_count, k.enough) == (3, 2, True)
    k = aa.selection_kpis(pd.DataFrame({"playlist_name": ["P", "P"]}), 1)
    assert (k.track_count, k.playlist_count) == (2, 1)


def test_genres(df):
    assert aa.selection_genres(aa.artist_rows(df, "X")) == ["rock", "indie", "pop"]
    assert aa.selection_genres(df.drop(columns=["artist_genres"])) == []
    assert aa.selection_genres(df.assign(artist_genres=None)) == []
    assert aa.top_genre_tags(pd.Series(["a, b", " ", None, "a"]), n=1) == ["a"]
    assert aa.top_genre_tags(pd.Series([], dtype=str)) == []


def test_track_table_artist(df):
    t = aa.track_table(aa.artist_rows(df, "X"), include_album=True)
    assert list(t.columns) == ["Track", "Album", "Playlist", "Popularity", "Year", "Duration"]
    assert t["Track"].tolist() == ["A", "A", "B", "D", "C"]  # popularity desc, NaN last
    assert str(t["Year"].dtype) == "Int64"
    assert t["Duration"].tolist() == ["3:00", "3:00", "4:00", "1:00", "—"]


def test_track_table_variants_and_sort_without_popularity(df):
    sel = aa.artist_rows(df, "X")
    assert list(aa.track_table(sel, True, include_playlist=False).columns) == \
        ["Track", "Album", "Popularity", "Year", "Duration"]
    assert list(aa.track_table(sel, False, include_year=False).columns) == \
        ["Track", "Playlist", "Popularity", "Duration"]
    bare = sel.drop(columns=["popularity_raw", "release_year", "duration_min", "duration_raw"])
    t = aa.track_table(bare, include_album=True)
    assert list(t.columns) == ["Track", "Album", "Playlist"]
    assert t["Track"].tolist() == ["A", "A", "B", "C", "D"]  # Track ascending


def test_popularity_bin_tracks(df):
    sel = aa.artist_rows(df, "X")
    assert sorted(aa.popularity_bin_tracks(sel, 40)["track_id"]) == ["t4"]
    assert sorted(aa.popularity_bin_tracks(sel, 80)["track_id"]) == ["t1", "t1"]
    assert aa.popularity_bin_tracks(sel, 0).empty


def test_album_breakdown(df):
    ab = aa.album_breakdown(aa.artist_rows(df, "X"))
    assert ab.to_dict("records") == [{"album_name": "Hits", "count": 3}, {"album_name": "Solo", "count": 1}]
    assert aa.deep_dive_albums(ab) == ["Hits"]
    assert aa.deep_dive_albums(ab, min_tracks=1) == ["Hits", "Solo"]


def test_playlist_distribution(df):
    pl = aa.playlist_distribution(aa.artist_rows(df, "X"))
    assert pl.to_dict("records") == [{"playlist_name": "P1", "count": 3}, {"playlist_name": "P2", "count": 2}]


def test_track_extremes(df):
    ex = aa.track_extremes(aa.artist_rows(df, "X"), include_years=True)
    assert (ex.longest["track_name"], ex.shortest["track_name"]) == ("B", "D")
    assert (ex.most_popular["track_name"], ex.least_popular["track_name"]) == ("A", "D")
    assert (ex.oldest["track_name"], ex.newest["track_name"]) == ("A", "D")
    no_years = aa.track_extremes(aa.artist_rows(df, "X"), include_years=False)
    assert no_years.oldest is None and no_years.newest is None


def test_track_extremes_missing_and_all_nan(df):
    bare = df[["track_name", "playlist_name"]]
    ex = aa.track_extremes(bare, include_years=True)
    assert all(v is None for v in (ex.longest, ex.shortest, ex.most_popular, ex.oldest))
    nan_pop = df.assign(popularity_raw=np.nan)
    assert aa.track_extremes(nan_pop, include_years=False).most_popular is None


def test_audio_radar(df):
    sel = aa.artist_rows(df, "X")
    r = aa.audio_radar(sel, df)
    assert r.features == ["energy", "valence", "danceability"]
    assert r.n_enriched == 4  # t3 has no features
    assert r.axis_labels == ["energy", "valence", "danceability", "tempo"]
    assert r.feature_means == pytest.approx([0.6, 0.425, 0.625])  # t1 counts once per playlist
    assert r.mean_tempo_bpm == pytest.approx(115.0)
    # collection tempo range 60..180 -> (115 - 60) / 120
    assert r.axis_values[-1] == pytest.approx(55 / 120)


def test_audio_radar_edges(df):
    flat = df.assign(tempo=100.0)
    assert aa.audio_radar(aa.artist_rows(flat, "X"), flat).axis_values[-1] == 0.5
    no_tempo = df.drop(columns=["tempo"])
    r = aa.audio_radar(aa.artist_rows(no_tempo, "X"), no_tempo)
    assert r.mean_tempo_bpm is None and r.axis_labels == r.features
    empty = df.assign(energy=np.nan, valence=np.nan, danceability=np.nan)
    r = aa.audio_radar(aa.artist_rows(empty, "X"), empty)
    assert r.n_enriched == 0 and r.axis_labels == [] and r.feature_means == []
    r = aa.audio_radar(df[["track_id"]], df[["track_id"]])
    assert r.features == [] and r.n_enriched == 0


def test_popularity_distribution(df):
    d = aa.popularity_distribution(aa.artist_rows(df, "X"))
    assert d.bin_labels == ["40–44", "60–64", "80–84"]
    assert d.counts == [1, 1, 2] and d.bin_starts == [40, 60, 80]
    assert (d.average, d.median, d.highest, d.lowest) == (pytest.approx(65.0), 70.0, 80.0, 40.0)


def test_popularity_distribution_empty():
    d = aa.popularity_distribution(pd.DataFrame({"popularity_raw": [np.nan]}))
    assert d.bin_labels == [] and np.isnan(d.average) and np.isnan(d.lowest)


def test_release_years(df):
    sel = aa.artist_rows(df, "X")
    yc = aa.release_year_counts(sel)
    assert yc.to_dict("records") == [{"release_year": 2010, "count": 1}, {"release_year": 2000, "count": 1},
                                     {"release_year": 1990, "count": 2}]
    assert str(yc["release_year"].dtype) == "Int64"
    s = aa.year_summary(sel)
    assert (s.average, s.oldest, s.newest, s.span) == (pytest.approx(1997.5), 1990, 2010, 20)
    nothing = df.assign(release_year=np.nan)
    assert aa.year_summary(nothing) is None and aa.release_year_counts(nothing).empty


def test_album_release_takes_the_year_as_parameter(df):
    sel = aa.album_rows(df, "Hits", "X")
    assert aa.album_release(sel, 2026) == aa.AlbumRelease(1990, 36)
    assert aa.album_release(sel, 1990).years_ago == 0
    tie = pd.DataFrame({"release_year": [2001.0, 1999.0]})
    assert aa.album_release(tie, 2026).year == 1999  # smallest on ties
    assert aa.album_release(df.assign(release_year=np.nan), 2026) is None
