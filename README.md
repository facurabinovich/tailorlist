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

## Two modes

- **Facu's Collection** — reads from a personal MySQL database (star schema, 14 playlists, ~450 tracks). Requires DB credentials.
- **Your Collection** — public mode. Users paste Spotify playlist URLs; tracks are fetched via the Spotify API and enriched with audio features from [ReccoBeats](https://reccobeats.com). No database needed.

## Tech stack

- **Frontend** — [Streamlit](https://streamlit.io)
- **Data** — pandas, SQLAlchemy + MySQL (personal mode), Spotify Web API
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

The **Your Collection** mode works out of the box with just the Spotify credentials. The DB vars are only needed to enable Facu's Collection.

Get Spotify API credentials at [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) — create an app, copy the Client ID and Secret.

## Deployment (Streamlit Cloud)

Set these in the Streamlit Cloud secrets dashboard:

```toml
SPOTIFY_CLIENT_ID = "..."
SPOTIFY_CLIENT_SECRET = "..."

# Only needed for Facu's Collection mode:
DB_HOST = "..."
DB_PORT = "3307"
DB_USER = "..."
DB_PASSWORD = "..."
DB_NAME = "spotify_analytics"
```

## ML models

The KMeans model ships with the repo (`models/kmeans.pkl`) — clusters tracks into 4 groups based on energy, acousticness, valence, tempo, danceability, and speechiness. Labels: *High Energy · Dark · Fast*, *High Energy · Happy · Danceable*, *Rap · Danceable · Positive*, *Acoustic · Dark*.

Training notebooks are in `ml/`.

## ETL pipeline (personal mode)

```bash
python -m pipeline.run_etl              # full sync
python -m pipeline.run_etl --skip-enrich  # skip audio feature enrichment
python -m pipeline.run_etl --enrich-only  # backfill missing audio features only
```
## Some Captures
<img width="752" height="317" alt="tailorlist_1" src="https://github.com/user-attachments/assets/1f0b69cc-048d-45cc-b45b-e02b3fce3cd6" />
<img width="766" height="402" alt="tailorlist_2" src="https://github.com/user-attachments/assets/437b78cd-d409-49cb-a1a7-23e23d8311e8" />
<img width="926" height="394" alt="tailorlist_3" src="https://github.com/user-attachments/assets/f7c57c97-f522-45e2-915c-e9cb962a8dd8" />
<img width="923" height="209" alt="tailorlist_4" src="https://github.com/user-attachments/assets/8de136ed-400f-4074-b7bc-27eb9032ad0d" />
<img width="734" height="418" alt="image" src="https://github.com/user-attachments/assets/83076b80-7bed-438b-b80b-bc5f8f00b8f4" />
<img width="714" height="308" alt="image" src="https://github.com/user-attachments/assets/58466631-054d-4d7d-b3ad-5548b0b2499a" />


