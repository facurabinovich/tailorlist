# Spotify Analytics

A Streamlit app for exploring and analyzing Spotify playlist collections, with audio feature visualizations, ML clustering, and playlist comparison tools.

## Features

- **Overview** — playlist stats, top artists, release timeline
- **Playlist Detail** — per-playlist deep dive with genre breakdown
- **Artist / Album view** — discography explorer
- **Playlist Comparison** — side-by-side audio DNA diff, cross-playlist duplicates
- **Audio DNA** — radar charts, feature distributions, decade trends
- **My Clusters** — KMeans song clustering + manual labeling workflow
- **Your Collection** — paste any public Spotify playlist URL to analyze it live

## Setup

```bash
cp .env.example .env
# Fill in SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET
pip install -r requirements.txt
streamlit run app.py
```

## Deployment (Streamlit Cloud)

Set secrets in the Streamlit Cloud dashboard (equivalent to `.env`):

| Secret | Purpose |
|---|---|
| `SPOTIFY_CLIENT_ID` | Spotify app credentials |
| `SPOTIFY_CLIENT_SECRET` | Spotify app credentials |
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | MySQL — only needed for "Facu's Collection" mode |

The **Your Collection** mode works without any database — users paste playlist URLs and data is fetched live via the Spotify API.

## Architecture

See [`CLAUDE.md`](CLAUDE.md) for full architecture details.
