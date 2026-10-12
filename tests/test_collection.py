"""Characterization of the YC branch of get_tracks() / get_all_tracks().

EXPECTED was captured from the pre-T12 implementation (db/queries.py) by running it on
data/dev_collection.json plus the edge-case inputs below. It pins shape, column order,
dtypes, a content hash and spot values, so moving the logic must not change a bit.
The session state is a plain dict patched onto streamlit.session_state (both the
old and the new location read it as st.session_state).
"""
import json
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st

from app_state.collection import get_all_tracks, get_tracks
from app_state.session import MODE_YC

ROOT = Path(__file__).resolve().parent.parent
COLL = json.loads((ROOT / "data" / "dev_collection.json").read_text(encoding="utf-8"))


def _edge():
    enr = [
        {"id": "a1", "name": "A", "artists": "X", "release_date": "2014", "energy": .5, "playlist_name": "P1", "secondary_artists": "Z"},
        {"id": "a2", "name": "B", "artists": "Y", "release_date": "2014-03", "energy": .6, "playlist_name": "P1", "secondary_artists": ""},
        {"id": "a3", "name": "C", "artists": "Y", "release_date": "2014-03-15", "energy": .7, "playlist_name": "P2"},
        {"id": "a4", "name": "D", "artists": "W", "release_date": "", "energy": .1, "playlist_name": "P2"},
        {"id": "a5", "name": "E", "artists": "W", "release_date": None, "energy": .2, "playlist_name": "P2"},
        {"id": "a6", "name": "F", "artists": "V", "release_date": "1800", "energy": .3, "playlist_name": "P2"},
        {"name": "NoId", "artists": "V", "release_date": "1999", "energy": .4, "playlist_name": "P2"},
    ]
    skp = [{"name": "S1", "artists": "Q", "release_date": "2001", "playlist_name": "P1"},
           {"name": "S2", "playlist_name": "P1", "release_date": "2002-05"}]
    fl = [{"name": "F1", "artists": "R", "release_date": "2003-01-01", "playlist_name": "P2"}]
    return enr, skp, fl


CASES = {
    "edge_all": _edge,
    "edge_enriched_only": lambda: (_edge()[0], [], []),
    "real": lambda: (COLL["enriched"], COLL["skipped"], COLL["failed"]),
}

EXPECTED = {'get_tracks:edge_all': {'shape': [7, 10],
                         'columns': ['track_id',
                                     'track_name',
                                     'artist_name',
                                     'release_date',
                                     'energy',
                                     'playlist_name',
                                     'secondary_artists',
                                     'release_year',
                                     'decade',
                                     'artist_display'],
                         'dtypes': ['object',
                                    'object',
                                    'object',
                                    'object',
                                    'float64',
                                    'object',
                                    'object',
                                    'float64',
                                    'float64',
                                    'object'],
                         'hash': 3046381694767665058,
                         'ids': ['a1', 'a2', 'a3', 'a4', 'a5', 'a6', 'nan'],
                         'years': [2014.0, 2014.0, 2014.0, None, None, None, 1999.0],
                         'display': ['X feat. Z', 'Y', 'Y', 'W', 'W', 'V', 'V']},
 'get_tracks:edge_enriched_only': {'shape': [7, 10],
                                   'columns': ['track_id',
                                               'track_name',
                                               'artist_name',
                                               'release_date',
                                               'energy',
                                               'playlist_name',
                                               'secondary_artists',
                                               'release_year',
                                               'decade',
                                               'artist_display'],
                                   'dtypes': ['object',
                                              'object',
                                              'object',
                                              'object',
                                              'float64',
                                              'object',
                                              'object',
                                              'float64',
                                              'float64',
                                              'object'],
                                   'hash': 3046381694767665058,
                                   'ids': ['a1', 'a2', 'a3', 'a4', 'a5', 'a6', 'nan'],
                                   'years': [2014.0, 2014.0, 2014.0, None, None, None, 1999.0],
                                   'display': ['X feat. Z', 'Y', 'Y', 'W', 'W', 'V', 'V']},
 'get_tracks:real': {'shape': [416, 30],
                     'columns': ['track_id',
                                 'track_name',
                                 'artist_name',
                                 'artist_ids',
                                 'album_name',
                                 'duration_raw',
                                 'uri',
                                 'popularity_raw',
                                 'release_date',
                                 'added_at',
                                 'artist_genres',
                                 'playlist_name',
                                 'danceability',
                                 'energy',
                                 'key_value',
                                 'loudness',
                                 'mode',
                                 'speechiness',
                                 'acousticness',
                                 'instrumentalness',
                                 'liveness',
                                 'valence',
                                 'tempo',
                                 'time_signature',
                                 'track_number',
                                 'disc_number',
                                 'explicit',
                                 'release_year',
                                 'decade',
                                 'artist_display'],
                     'dtypes': ['object',
                                'object',
                                'object',
                                'object',
                                'object',
                                'int64',
                                'object',
                                'int64',
                                'object',
                                'object',
                                'object',
                                'object',
                                'float64',
                                'float64',
                                'float64',
                                'float64',
                                'int64',
                                'float64',
                                'float64',
                                'float64',
                                'float64',
                                'float64',
                                'float64',
                                'float64',
                                'float64',
                                'float64',
                                'object',
                                'int64',
                                'int64',
                                'object'],
                     'hash': 5002705990620834838,
                     'ids': None,
                     'years': [1977.0,
                               2003.0,
                               2004.0,
                               1994.0,
                               1981.0,
                               1995.0,
                               1977.0,
                               1980.0,
                               1981.0,
                               1992.0,
                               1977.0,
                               2007.0],
                     'display': None},
 'get_all_tracks:edge_all': {'shape': [10, 10],
                             'columns': ['track_id',
                                         'track_name',
                                         'artist_name',
                                         'release_date',
                                         'energy',
                                         'playlist_name',
                                         'secondary_artists',
                                         'release_year',
                                         'decade',
                                         'artist_display'],
                             'dtypes': ['object',
                                        'object',
                                        'object',
                                        'object',
                                        'float64',
                                        'object',
                                        'object',
                                        'float64',
                                        'float64',
                                        'object'],
                             'hash': 7099880080321355532,
                             'ids': ['a1',
                                     'a2',
                                     'a3',
                                     'a4',
                                     'a5',
                                     'a6',
                                     'nan',
                                     'S1||Q',
                                     'S2||',
                                     'F1||R'],
                             'years': [2014.0,
                                       2014.0,
                                       2014.0,
                                       None,
                                       None,
                                       None,
                                       1999.0,
                                       2001.0,
                                       2002.0,
                                       2003.0],
                             'display': ['X feat. Z',
                                         'Y',
                                         'Y',
                                         'W',
                                         'W',
                                         'V',
                                         'V',
                                         'Q',
                                         'nan',
                                         'R']},
 'get_all_tracks:edge_enriched_only': {'shape': [7, 10],
                                       'columns': ['track_id',
                                                   'track_name',
                                                   'artist_name',
                                                   'release_date',
                                                   'energy',
                                                   'playlist_name',
                                                   'secondary_artists',
                                                   'release_year',
                                                   'decade',
                                                   'artist_display'],
                                       'dtypes': ['object',
                                                  'object',
                                                  'object',
                                                  'object',
                                                  'float64',
                                                  'object',
                                                  'object',
                                                  'float64',
                                                  'float64',
                                                  'object'],
                                       'hash': 3046381694767665058,
                                       'ids': ['a1', 'a2', 'a3', 'a4', 'a5', 'a6', 'nan'],
                                       'years': [2014.0, 2014.0, 2014.0, None, None, None, 1999.0],
                                       'display': ['X feat. Z', 'Y', 'Y', 'W', 'W', 'V', 'V']},
 'get_all_tracks:real': {'shape': [501, 30],
                         'columns': ['track_id',
                                     'track_name',
                                     'artist_name',
                                     'artist_ids',
                                     'album_name',
                                     'duration_raw',
                                     'uri',
                                     'popularity_raw',
                                     'release_date',
                                     'added_at',
                                     'artist_genres',
                                     'playlist_name',
                                     'danceability',
                                     'energy',
                                     'key_value',
                                     'loudness',
                                     'mode',
                                     'speechiness',
                                     'acousticness',
                                     'instrumentalness',
                                     'liveness',
                                     'valence',
                                     'tempo',
                                     'time_signature',
                                     'track_number',
                                     'disc_number',
                                     'explicit',
                                     'release_year',
                                     'decade',
                                     'artist_display'],
                         'dtypes': ['object',
                                    'object',
                                    'object',
                                    'object',
                                    'object',
                                    'int64',
                                    'object',
                                    'int64',
                                    'object',
                                    'object',
                                    'object',
                                    'object',
                                    'float64',
                                    'float64',
                                    'float64',
                                    'float64',
                                    'float64',
                                    'float64',
                                    'float64',
                                    'float64',
                                    'float64',
                                    'float64',
                                    'float64',
                                    'float64',
                                    'float64',
                                    'float64',
                                    'object',
                                    'int64',
                                    'int64',
                                    'object'],
                         'hash': 2224861379780819015,
                         'ids': None,
                         'years': [1977.0,
                                   2003.0,
                                   2004.0,
                                   1994.0,
                                   1981.0,
                                   1995.0,
                                   1977.0,
                                   1980.0,
                                   1981.0,
                                   1992.0,
                                   1977.0,
                                   2007.0],
                         'display': None}}



def _hash(df):
    # list/dict cells (e.g. genres) are not hashable; stringify them first
    clean = df.map(lambda v: str(v) if isinstance(v, (list, dict)) else v)
    return int(pd.util.hash_pandas_object(clean, index=True).sum())


@pytest.mark.parametrize("fn_name,fn", [("get_tracks", get_tracks), ("get_all_tracks", get_all_tracks)])
@pytest.mark.parametrize("case", list(CASES))
def test_yc_frame_matches_pre_refactor_capture(monkeypatch, fn_name, fn, case):
    enriched, skipped, failed = CASES[case]()
    monkeypatch.setattr(st, "session_state", {
        "mode": MODE_YC, "uc_active": True,
        "uc_enriched": enriched, "uc_skipped": skipped, "uc_failed": failed,
    })
    df = fn()
    exp = EXPECTED[f"{fn_name}:{case}"]
    assert list(df.shape) == exp["shape"]
    assert list(df.columns) == exp["columns"]
    assert [str(t) for t in df.dtypes] == exp["dtypes"]
    assert _hash(df) == exp["hash"]
    if exp["ids"] is not None:
        assert [str(x) for x in df["track_id"].head(12)] == exp["ids"]
        assert [str(x) for x in df["artist_display"].head(12)] == exp["display"]
    years = [None if pd.isna(x) else float(x) for x in df["release_year"].head(12)]
    assert years == exp["years"]


def test_get_tracks_never_includes_skipped_or_failed(monkeypatch):
    enriched, skipped, failed = CASES["edge_all"]()
    monkeypatch.setattr(st, "session_state", {
        "mode": MODE_YC, "uc_active": True,
        "uc_enriched": enriched, "uc_skipped": skipped, "uc_failed": failed,
    })
    assert len(get_tracks()) == 7
    assert len(get_all_tracks()) == 10


@pytest.mark.parametrize("fn", [get_tracks, get_all_tracks])
@pytest.mark.parametrize("state", [
    {},
    {"mode": MODE_YC},
    {"mode": MODE_YC, "uc_active": True},
    {"mode": MODE_YC, "uc_active": True, "uc_enriched": []},
    {"uc_enriched": [{"id": "x", "name": "n", "artists": "a", "playlist_name": "P"}]},
], ids=["empty", "mode-only", "active-no-enriched", "active-empty-enriched", "enriched-not-active"])
def test_no_collection_returns_empty_frame_without_touching_db(monkeypatch, fn, state):
    """Without an active enriched collection the loaders return an empty frame, never the DB.

    conftest makes engine creation raise, so any DB access would fail this test.
    """
    import db.connection

    def boom(*a, **k):
        raise AssertionError("collection loaders must not touch the database")

    monkeypatch.setattr(db.connection, "get_engine", boom)
    monkeypatch.setattr(st, "session_state", dict(state))
    df = fn()
    assert df.empty
    assert {"track_id", "track_name", "artist_name", "playlist_name"} <= set(df.columns)
    assert df["playlist_name"].unique().tolist() == []


def test_collection_module_does_not_import_db():
    import app_state.collection as collection
    assert not hasattr(collection, "load_tracks")
    assert not hasattr(collection, "load_all_tracks")
    assert not hasattr(collection, "get_cluster_data")
    assert not hasattr(collection, "get_audio_features_by_playlist")


def test_active_collection_without_audio_features_still_lists_its_tracks(monkeypatch):
    """Enrichment can finish with no track found in ReccoBeats: uc_active is set and
    uc_enriched is empty. get_all_tracks() still shows the skipped/failed tracks;
    get_tracks() (audio features only) is empty."""
    monkeypatch.setattr(st, "session_state", {
        "uc_active": True, "uc_enriched": [],
        "uc_skipped": [{"id": "s1", "name": "Song", "artists": "Artist", "playlist_name": "P"}],
        "uc_failed": [],
    })
    assert get_all_tracks()["track_id"].tolist() == ["s1"]
    assert get_tracks().empty
