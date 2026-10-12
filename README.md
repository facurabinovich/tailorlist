# TailorList — Spotify Analytics

A personal Spotify analytics app built with Streamlit. Analyze your own playlists or paste any public Spotify URL to explore audio features, discover patterns, and cluster your music collection with ML.

## Features

| Page | What it does |
|---|---|
| **Overview** | Collection-wide stats — top artists, release timeline, audio feature averages |
| **Playlist Detail** | Per-playlist deep dive with genre breakdown and track table |
| **Artist / Album** | Discography explorer with audio feature profiles |
| **Playlist Comparison** | Side-by-side audio DNA diff, cross-playlist duplicates, unique tracks |
| **Audio DNA** | Radar charts, feature distributions, decade-by-decade trends |
| **My Clusters** | KMeans song clustering (4 clusters) + manual labeling workflow |
| **Your Collection** | Paste any public Spotify playlist URL — analyzed live, no account needed |

## How it works

Users paste public Spotify playlist URLs. Tracks are fetched from the Spotify API and enriched with audio features from [ReccoBeats](https://reccobeats.com), falling back to a local SQLite snapshot (`data/audio_fallback.db`) for tracks ReccoBeats doesn't have. The enriched collection lives in the Streamlit session and is saved in MySQL for 7 days, so a bookmarked URL (or the `tailorlist_sid` cookie) brings it back. MySQL also stores cluster-labeling progress and anonymous usage analytics.

## Tech stack

- **Frontend** — [Streamlit](https://streamlit.io)
- **Data** — pandas, Spotify Web API, SQLAlchemy + MySQL (saved sessions, cluster progress, analytics)
- **ML** — scikit-learn: KMeans clustering, Random Forest playlist classifier
- **Viz** — Plotly
- **Audio features** — [ReccoBeats API](https://reccobeats.com)

## Local setup

```bash
git clone https://github.com/facurabinovich/tailorlist.git
cd tailorlist
pip install -r requirements.txt
cp .env.example .env
# Fill in SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET
streamlit run app.py
```

Fill in the `DB_*` variables to point at a MySQL database (`python scripts/create_schema.py` creates the tables). With `DEV_MODE=1` the app uses those variables and auto-loads `data/dev_collection.json` as the collection, if present; with `DEV_MODE=0` it reads `DATABASE_URL` instead.

Get Spotify API credentials at [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) — create an app, copy the Client ID and Secret.

## Deployment

Production runs with `DEV_MODE=0` and needs `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` and `DATABASE_URL` (a `mysql://` URL), either as environment variables or Streamlit secrets.

## ML models

The KMeans model ships with the repo (`models/kmeans.pkl`) — clusters tracks into 4 groups based on energy, acousticness, valence, tempo, danceability, and speechiness. Labels: *High Energy · Dark · Fast*, *High Energy · Happy · Danceable*, *Rap · Danceable · Positive*, *Acoustic · Dark*.

Training notebooks are in `ml/`.

## Architecture

The code is split in layers with one-way dependencies (no cycles):

```
app.py            navigation (st.navigation over pages/)
config.py         constants and settings; DEV_MODE is read only here (is_dev_mode())

core/             pure domain logic: no Streamlit, no session state. Typed functions over
                  DataFrames / plain data, documented for an LLM reader: they are the
                  base of the planned agent's tools (overview, playlist_detail,
                  artist_album, comparison, duplicates, audio_dna, clustering, grouping,
                  genres, tracks, enrichment, home, export, glossary, formatting)
db/               all SQL: connection, sessions, progress, analytics
spotify/          external APIs, no UI: Spotify client, ReccoBeats client + fallback DB
app_state/        the only layer that reads/writes st.session_state and query params:
                  collection, session restore, clusters, enrichment run, home flow
ui/               presentation helpers: theme, sidebar nav, shared components, charts, export
pages/            thin pages: read state, call core/ (via app_state), render with ui/
tests/            import the real code; tests/conftest.py blocks real DB engines and HTTP
```

Dependency rule:

```
pages     -> ui, app_state, core   (+ db for cluster progress, analytics and session deletion)
ui        -> app_state, config     (never db/)
app_state -> db, spotify, core
db        -> config
spotify   -> config
core      -> config only
```

The key parts are enforced by tests: `tests/test_architecture.py` checks that `core/` never imports Streamlit or `db/`, that its public functions are typed and documented, that `ui/` never imports `db/` and that there is no SQL in `pages/`; `tests/test_smoke_pages.py` checks that pages never import other pages.

Run the tests with `python -m pytest -q -p no:cacheprovider`.

## Some Captures
<img width="752" height="317" alt="tailorlist_1" src="https://github.com/user-attachments/assets/1f0b69cc-048d-45cc-b45b-e02b3fce3cd6" />
<img width="766" height="402" alt="tailorlist_2" src="https://github.com/user-attachments/assets/437b78cd-d409-49cb-a1a7-23e23d8311e8" />
<img width="926" height="394" alt="tailorlist_3" src="https://github.com/user-attachments/assets/f7c57c97-f522-45e2-915c-e9cb962a8dd8" />
<img width="923" height="209" alt="tailorlist_4" src="https://github.com/user-attachments/assets/8de136ed-400f-4074-b7bc-27eb9032ad0d" />
<img width="734" height="418" alt="image" src="https://github.com/user-attachments/assets/83076b80-7bed-438b-b80b-bc5f8f00b8f4" />
<img width="714" height="308" alt="image" src="https://github.com/user-attachments/assets/58466631-054d-4d7d-b3ad-5548b0b2499a" />


