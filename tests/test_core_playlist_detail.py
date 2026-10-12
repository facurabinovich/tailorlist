"""Characterization of core.playlist_detail on a small fixed frame (values verified against the
pre-T20 inline logic of pages/2_Playlist_Detail.py; see tests/test_playlist_detail.py for the
broader scenarios)."""
import numpy as np
import pandas as pd
import pytest

from core import playlist_detail as pdc


@pytest.fixture
def df():
    return pd.DataFrame({
        "track_id":       ["a", "b", "c", "d", "e", "f"],
        "track_name":     ["A", "B", "C", "D", "E", "F"],
        "artist_name":    ["X", "X", "Y", "Y", "Z", "X"],
        "artist_display": ["X", "X", "Y", "Y feat. Q", "Z", "X"],
        "playlist_name":  ["P1", "P1", "P1", "P1", "P2", "P2"],
        "popularity_raw": [80, 70, 60, 50, 40, 30],
        "release_year":   [1990.0, 2000.0, 1985.0, np.nan, 2020.0, 1990.0],
        "decade":         [1990.0, 2000.0, 1980.0, np.nan, 2020.0, 1990.0],
        "duration_raw":   [180000.0, 240000.0, 210000.0, 300000.0, 120000.0, 60000.0],
        "added_at":       ["2024-01-15", "2024-01-20", "2024-03-05", "2024-03-10", "2024-05-01", "2024-05-02"],
        "artist_genres":  ["rock, indie rock", "rock", "pop", None, "jazz", ""],
        "energy":         [0.8, 0.6, 0.4, np.nan, 0.2, 0.3],
        "valence":        [0.5, 0.5, 0.7, 0.1, 0.2, 0.3],
        "danceability":   [0.7, 0.6, 0.5, 0.4, 0.3, 0.2],
        "acousticness":   [0.2, 0.3, 0.6, 0.1, 0.8, 0.9],
        "speechiness":    [0.05, 0.04, 0.06, 0.03, 0.02, 0.01],
        "instrumentalness": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5],
        "tempo":          [120.0, 130.0, 90.0, 140.0, 80.0, 100.0],
    })


@pytest.fixture
def p1(df):
    return pdc.playlist_tracks(df, "P1")


def test_playlist_audio_averages(df):
    af = pdc.playlist_audio_averages(df)
    assert af["playlist_name"].tolist() == ["P1", "P2"]
    assert af.columns.tolist() == ["playlist_name", "energy", "acousticness", "valence", "danceability",
                                   "speechiness", "instrumentalness", "tempo"]
    assert af.loc[0, "energy"] == pytest.approx(0.6)       # NaN ignored: (0.8+0.6+0.4)/3
    assert af.loc[0, "tempo"] == pytest.approx(120.0)


def test_playlist_audio_averages_without_features_is_empty(df):
    assert pdc.playlist_audio_averages(df[["track_id", "playlist_name"]]).empty


def test_playlist_meta(df):
    meta = pdc.playlist_meta(df, [{"name": "P1", "followers": 5}, {"name": "P1", "followers": 9}, {"name": "P2"}])
    assert meta.to_dict("records") == [
        {"playlist_name": "P1", "total_tracks": 4, "followers": 5},   # first matching record wins
        {"playlist_name": "P2", "total_tracks": 2, "followers": 0},   # no followers key -> 0
    ]


def test_add_speechiness_log(df):
    af = pdc.playlist_audio_averages(df)
    out = pdc.add_speechiness_log(af)
    assert "speechiness_log" not in af.columns            # input untouched
    assert out["speechiness_log"].tolist() == pytest.approx(np.log1p(af["speechiness"]).tolist())
    assert pdc.add_speechiness_log(out) is out            # existing column -> returned as is
    empty = pd.DataFrame()
    assert pdc.add_speechiness_log(empty) is empty


def test_playlist_tracks_converts_to_minutes_without_mutating(df):
    p1 = pdc.playlist_tracks(df, "P1")
    assert p1["duration_raw"].tolist() == [3.0, 4.0, 3.5, 5.0]
    assert df["duration_raw"].iloc[0] == 180000.0
    assert p1.index.tolist() == [0, 1, 2, 3]


def test_compare_audio_and_radar(df):
    af = pdc.add_speechiness_log(pdc.playlist_audio_averages(df))
    audio = pdc.compare_audio(af, "P1")
    assert audio.playlist["energy"] == pytest.approx(0.6)
    assert audio.global_avg["energy"] == pytest.approx((0.6 + 0.25) / 2)
    radar = pdc.radar_profile(af, audio, ["energy", "tempo", "missing_feature"])
    assert radar.features == ["energy", "tempo"]
    assert radar.playlist_values[1] == pytest.approx((120 - 60) / 140)
    assert radar.global_values[1] == pytest.approx(((120 + 90) / 2 - 60) / 140)


def test_compare_audio_unknown_playlist_or_empty(df):
    af = pdc.playlist_audio_averages(df)
    for audio in (pdc.compare_audio(af, "nope"), pdc.compare_audio(pd.DataFrame(), "P1")):
        assert audio.playlist is None and audio.global_avg is None
        assert pdc.radar_profile(af, audio, ["energy"]) is None


def test_radar_profile_none_without_features_or_all_nan(df):
    af = pdc.playlist_audio_averages(df)
    audio = pdc.compare_audio(af, "P1")
    assert pdc.radar_profile(af, audio, ["not_there"]) is None
    af_nan = af.copy()
    af_nan.loc[0, ["energy", "valence"]] = np.nan
    assert pdc.radar_profile(af_nan, pdc.compare_audio(af_nan, "P1"), ["energy", "valence"]) is None


def test_header_kpis(p1):
    k = pdc.header_kpis(p1, 12)
    assert (k.total_tracks, k.unique_artists, k.followers) == (4, 2, 12)
    assert (k.first_added, k.last_added) == ("Jan 2024", "Mar 10, 2024")


def test_header_kpis_without_added_at(p1):
    k = pdc.header_kpis(p1.drop(columns="added_at"), 0)
    assert (k.first_added, k.last_added) == ("N/A", "N/A")


def test_track_highlights(p1):
    h = pdc.track_highlights(p1)
    assert (h.longest["track_name"], h.shortest["track_name"]) == ("D", "A")
    assert (h.most_popular["track_name"], h.least_popular["track_name"]) == ("A", "D")
    assert (h.oldest["track_name"], h.newest["track_name"]) == ("C", "B")     # NaN year of D ignored


def test_track_highlights_missing_columns(p1):
    h = pdc.track_highlights(p1[["track_name", "artist_display"]])
    assert h == pdc.TrackHighlights(None, None, None, None, None, None) or all(
        getattr(h, f) is None for f in ("longest", "shortest", "most_popular", "least_popular", "oldest", "newest"))
    no_years = p1.assign(release_year=np.nan)
    assert pdc.track_highlights(no_years).oldest is None


def test_playlist_averages(p1):
    a = pdc.playlist_averages(p1)
    assert a.avg_duration == pytest.approx(3.875)
    assert a.avg_popularity == pytest.approx(65.0)
    assert a.avg_release_year == pytest.approx((1990 + 2000 + 1985) / 3)
    assert (a.top_artist, a.top_artist_count) == ("X", 2)       # X and Y tie -> first by appearance


def test_playlist_averages_missing_columns(p1):
    a = pdc.playlist_averages(p1[["artist_name"]])
    assert (a.avg_duration, a.avg_popularity, a.avg_release_year) == (None, None, None)


def test_top_artists(p1):
    t = pdc.top_artists(p1, 1)
    assert t.table.to_dict("records") == [{"artist": "X", "tracks": 2}]
    assert t.covered_pct == pytest.approx(50.0)
    assert pdc.top_artists(p1).covered_pct == pytest.approx(100.0)


def test_decade_and_year_counts(p1):
    d = pdc.decade_counts(p1)
    assert d.to_dict("records") == [
        {"decade": 1980, "count": 1, "label": "1980s"},
        {"decade": 1990, "count": 1, "label": "1990s"},
        {"decade": 2000, "count": 1, "label": "2000s"},
    ]
    y = pdc.year_counts(p1)
    assert y["year"].tolist() == [1985, 1990, 2000] and y["count"].tolist() == [1, 1, 1]
    assert pdc.decade_counts(p1.drop(columns="decade")).empty
    assert pdc.year_counts(p1.drop(columns="release_year")).empty


def test_decade_track_listing(df):
    out = pdc.decade_track_listing(df, 1990)
    assert out.columns.tolist() == ["Track", "Artist", "Year", "Popularity"]
    assert out["Track"].tolist() == ["A", "F"]                  # popularity descending
    assert str(out["Year"].dtype) == "Int64"


def test_decade_track_listing_without_popularity(df):
    out = pdc.decade_track_listing(df.drop(columns="popularity_raw"), 1990)
    assert out.columns.tolist() == ["Track", "Artist", "Year"]
    assert out["Track"].tolist() == ["A", "F"]


def test_top_genres(p1):
    g = pdc.top_genres(p1)
    assert g.to_dict("records")[-1] == {"genre": "rock", "count": 2}    # ascending: biggest last
    assert set(g["genre"]) == {"rock", "indie rock", "pop"}
    assert len(pdc.top_genres(p1, 2)) == 2
    assert pdc.top_genres(p1.drop(columns="artist_genres")).empty


def test_mood_map(p1):
    assert pdc.mood_map_available(p1)
    assert not pdc.mood_map_available(p1.drop(columns="energy"))
    pts = pdc.mood_map_points(p1)
    assert pts.columns.tolist() == ["track_name", "artist_display", "energy", "valence", "popularity_raw"]
    assert pts["track_name"].tolist() == ["A", "B", "C"]         # D has NaN energy
    assert pdc.mood_map_points(p1.drop(columns="popularity_raw")).columns.tolist() == [
        "track_name", "artist_display", "energy", "valence"]


def test_monthly_additions_and_growth(p1):
    m = pdc.monthly_additions(p1)
    assert m.to_dict("records") == [{"period": "2024-01", "count": 2}, {"period": "2024-03", "count": 2}]
    t = pdc.growth_timeline(m)
    assert t["month"].tolist() == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-03-01")]
    assert "month" not in m.columns
    peak = pdc.peak_month(t)
    assert (peak.label, peak.count, peak.month) == ("Jan 2024", 2, pd.Timestamp("2024-01-01"))   # tie -> first


def test_monthly_additions_without_added_at(p1):
    assert pdc.monthly_additions(p1.drop(columns="added_at")).empty


def test_single_session_date(p1):
    assert pdc.single_session_date(p1) == "January 15, 2024"
    assert pdc.single_session_date(p1.drop(columns="added_at")) is None
    assert pdc.single_session_date(p1.assign(added_at=None)) is None


def test_similar_playlists_and_pct():
    af = pd.DataFrame({
        "playlist_name": ["A", "B", "C", "D"],
        "energy":        [0.5, 0.5, 0.9, 0.5],
        "tempo":         [130.0, 130.0, 130.0, 130.0],
    })
    s = pdc.similar_playlists(af, "A", 2)
    assert s["playlist_name"].tolist() == ["B", "D"] or s["playlist_name"].tolist() == ["D", "B"]
    assert s["distance"].tolist() == pytest.approx([0.0, 0.0])
    s3 = pdc.similar_playlists(af, "A")
    assert s3["playlist_name"].iloc[-1] == "C"
    assert s3["distance"].iloc[-1] == pytest.approx(0.4)
    assert (s3["tempo"] == 0.5).all()                                  # tempo normalized
    pct = pdc.with_similarity_pct(s3)
    assert sorted(pct["playlist_name"]) == ["B", "D"]                  # farthest (C) rounds to 0 and drops
    assert pct["similarity_pct"].tolist() == pytest.approx([100.0, 100.0])


def test_with_similarity_pct_drops_farthest():
    sim = pd.DataFrame({"playlist_name": ["B", "C", "D"], "distance": [0.1, 0.2, 0.4]})
    out = pdc.with_similarity_pct(sim)
    assert out["playlist_name"].tolist() == ["B", "C"]
    assert out["similarity_pct"].tolist() == pytest.approx([75.0, 50.0])
    assert out.index.tolist() == [0, 1]


def test_with_similarity_pct_all_equal_distances_gives_empty():
    sim = pd.DataFrame({"playlist_name": ["B"], "distance": [0.0]})
    assert pdc.with_similarity_pct(sim).empty


def test_similarity_features_and_no_feature_case():
    af = pd.DataFrame({"playlist_name": ["A", "B"], "speechiness": [0.1, 0.2]})
    assert pdc.similarity_features(af) == []
    assert pdc.similar_playlists(af, "A").empty


def test_track_table(p1):
    t = pdc.track_table(p1)
    assert t.columns.tolist() == ["Track", "Artist", "Year", "Duration", "Popularity",
                                  "Energy", "Valence", "Danceability", "Acousticness"]
    assert t["Duration"].tolist() == ["3:00", "4:00", "3:30", "5:00"]
    assert t["Year"].tolist() == [1990, 2000, 1985, 0]                 # NaN year -> 0
    assert str(t["Year"].dtype) == "Int64"
    assert t["Popularity"].tolist() == [80, 70, 60, 50]


def test_track_table_minimal_columns(p1):
    t = pdc.track_table(p1[["track_name", "artist_display"]])
    assert t.columns.tolist() == ["Track", "Artist"]


def test_track_table_missing_popularity_value_raises(p1):
    bad = p1.copy()
    bad["popularity_raw"] = bad["popularity_raw"].astype(float)
    bad.loc[0, "popularity_raw"] = np.nan
    with pytest.raises(Exception):
        pdc.track_table(bad)


def test_normalize_tempo():
    assert pdc.normalize_tempo(60) == 0 and pdc.normalize_tempo(200) == 1
