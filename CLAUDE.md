# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
# Start Streamlit (from project root)
streamlit run app.py

# Development mode — auto-runs ETL on startup and loads a test collection from data/dev_collection.json
DEV_MODE=1 streamlit run app.py
```

## ETL pipeline

```bash
# Full pipeline (extract → transform → load → enrich)
python -m pipeline.run_etl

# Skip audio feature enrichment (faster, just syncs track data)
python -m pipeline.run_etl --skip-enrich

# Enrich only — backfill missing audio features from ReccoBeats
python -m pipeline.run_etl --enrich-only
```

## Environment variables

Copy `.env` to the project root. Required vars:

| Variable | Purpose |
|---|---|
| `SPOTIFY_CLIENT_ID` | Spotify app credentials (Client Credentials flow) |
| `SPOTIFY_CLIENT_SECRET` | Spotify app credentials |
| `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME` | MySQL connection |
| `DEV_MODE=1` | Enables dev features: ETL on startup, OAuth export, `data/dev_collection.json` auto-load |

On Streamlit Cloud, credentials can also be set via `st.secrets`.

## Architecture

### Two modes of operation

The app supports two collection modes toggled in the sidebar:

- **Facu's Collection** — reads from a personal MySQL DB (star schema) via `db/queries.py` + `db/connection.py`
- **Your Collection** — users paste Spotify playlist URLs; tracks are fetched via Client Credentials API (`spotify_client.py`) and enriched live via ReccoBeats. Session data persists via `db/queries.save_uc_session()` and is restored via `?sid=` URL param.

### Page structure

`app.py` registers all pages via `st.navigation()` but keeps the nav hidden — `utils.inject_sidebar_nav()` renders a custom sidebar with manual `st.page_link()` calls. Every page must call `inject_sidebar_nav()` and then `check_collection_mode()` to guard "Your Collection" routes.

Pages live in `pages/`:
- `0_home.py` — landing, playlist paste-URL flow, enrichment trigger
- `1_Overview.py` – `6_My_Clusters.py` — analytics views
- `_Enrich.py` — hidden page that runs live enrichment for "Your Collection" mode

### Data layer (Facu's Collection)

Star schema in MySQL:
- Fact table: `fac_songs` (one row per track per playlist)
- Dims: `dim_songs`, `dim_artist`, `dim_album`, `dim_playlist`, `dim_audio_features`, `dim_releasedate`
- Bridge: `bridge_song_artists` (handles multi-artist tracks; `is_primary=TRUE` for main artist)

`db/queries.py` contains `load_tracks()` and `load_tracks_all()` as the canonical data-loading functions — both use `@st.cache_data`. All other page queries build on these or add their own cached functions.

### ML models (`models/`)

Pre-trained scikit-learn models serialized as `.pkl`:
- `rf_classifier.pkl` + `scaler.pkl` + `feature_cols.pkl` — Random Forest playlist classifier
- `kmeans.pkl` + `kmeans_scaler.pkl` — KMeans song clustering (4 clusters, defined in `config.CLUSTER_NAMES`)

`config.py` defines `CLUSTER_FEATURES` (6 features including `speechiness_log = log1p(speechiness)`), `CLUSTER_NAMES`, and `CLUSTER_COLORS`.

### Spotify client (`spotify_client.py`)

All Spotify API calls go through here. Key design decisions:
- Uses **Client Credentials** (no user OAuth) for public playlist fetching — works for unlimited users
- `get_spotify_oauth_client()` is only available under `DEV_MODE=1` for direct playlist creation
- Export to Spotify for end-users goes through **Spotlistr** (copy-paste flow) via `render_export_to_spotify()`
- `enrich_tracks_live()` calls `pipeline/enrich._fetch` + `_map_fields` directly with 1s/track rate limiting

### Pipeline (`pipeline/`)

- `extract.py` uses **SpotifyOAuth** (intentionally — this is a private backend script, not the public app)
- `enrich.py` fetches audio features from ReccoBeats API (1 req/sec rate limit); has a SQLite fallback cache at `data/audio_fallback.db`
- `playlists.yaml` — config file listing personal playlist IDs/names for the ETL

### Theming

`utils.inject_global_css()` applies global Spotify-branded CSS (dark theme, `#1DB954` green accent, Plus Jakarta Sans font). All pages must call this first. Button styling uses Streamlit `kind` attributes: `primary`=green, `secondary`=grey, `tertiary`=red (destructive).
