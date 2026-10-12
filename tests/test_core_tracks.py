"""core/tracks.py: release-year parsing, artist display, YC record normalization."""
import pandas as pd
import pytest

from core.tracks import add_artist_display, parse_release_year, yc_tracks_frame, yc_unmatched_frame


@pytest.mark.parametrize("raw,expected", [
    ("2014", 2014), ("2014-03", 2014), ("2014-03-15", 2014),
    ("", None), (None, None), ("1800", None), ("1900", None), ("1901", 1901),
    (" 2014 ", 2014), ("garbage", None), ("abcd-ef", None),
])
def test_parse_release_year(raw, expected):
    out = parse_release_year(pd.Series([raw]))
    assert (out.iloc[0] == expected) if expected is not None else pd.isna(out.iloc[0])


def test_parse_release_year_keeps_index_and_length():
    s = pd.Series(["2001", None, "1999-05"], index=[5, 6, 7])
    out = parse_release_year(s)
    assert list(out.index) == [5, 6, 7]
    assert out[5] == 2001 and pd.isna(out[6]) and out[7] == 1999


def test_add_artist_display():
    df = pd.DataFrame({"artist_name": ["A", "B", "C"], "secondary_artists": ["X, Y", "", None]})
    assert list(add_artist_display(df)["artist_display"]) == ["A feat. X, Y", "B", "C"]
    plain = add_artist_display(pd.DataFrame({"artist_name": ["A"]}))
    assert list(plain["artist_display"]) == ["A"]


ENR = [{"id": "e1", "name": "N", "artists": "Ar", "popularity": 5, "album": "Al",
        "duration_ms": 1000, "release_date": "2014-03", "energy": .5}]


def test_yc_frame_renames_and_derives_columns():
    df = yc_tracks_frame(ENR, include_unenriched=False)
    assert list(df.columns) == ["track_id", "track_name", "artist_name", "popularity_raw",
                                "album_name", "duration_raw", "release_date", "energy",
                                "release_year", "decade", "artist_display"]
    assert df.loc[0, "release_year"] == 2014 and df.loc[0, "decade"] == 2010


def test_yc_frame_include_unenriched_flag():
    skp = [{"id": "s1", "name": "S", "artists": "Q"}]
    fl = [{"id": "f1", "name": "F", "artists": "R"}]
    assert len(yc_tracks_frame(ENR, skp, fl, include_unenriched=False)) == 1
    both = yc_tracks_frame(ENR, skp, fl, include_unenriched=True)
    assert list(both["track_id"]) == ["e1", "s1", "f1"]


def test_yc_frame_synthetic_ids_only_for_rows_lacking_id():
    skp = [{"name": "S", "artists": "Q"}, {"name": "T"}]
    fl = [{"id": "f1", "name": "F", "artists": "R"}]
    df = yc_tracks_frame(ENR, skp, fl, include_unenriched=True)
    assert list(df["track_id"]) == ["e1", "S||Q", "T||", "f1"]


def test_yc_frame_empty_or_none_extras():
    for extra in ([], None):
        df = yc_tracks_frame(ENR, extra, extra, include_unenriched=True)
        assert len(df) == 1 and df.loc[0, "track_id"] == "e1"


def test_yc_frame_without_release_date_has_no_year_columns():
    df = yc_tracks_frame([{"id": "x", "name": "N", "artists": "A"}], include_unenriched=False)
    assert "release_year" not in df.columns and "decade" not in df.columns
    assert df.loc[0, "artist_display"] == "A"


def test_yc_unmatched_frame_include_decade():
    skp = [{"id": "s1", "name": "S", "artists": ["A"], "release_date": "1994-05-01"}]
    fl = [{"id": "f1", "name": "F", "artists": "B", "release_date": ""}]
    plain = yc_unmatched_frame(skp, fl)
    assert "decade" not in plain.columns
    df = yc_unmatched_frame(skp, fl, include_decade=True)
    assert list(df.columns[:5]) == ["track_id", "track_name", "artist_name", "release_year", "decade"]
    assert df.loc[0, "decade"] == 1990 and pd.isna(df.loc[1, "decade"])
    empty = yc_unmatched_frame([], [], include_decade=True)
    assert empty.empty and "decade" in empty.columns
