# Línea base del refactor (2026-10-11, commit 8f453e3)

## Visual (T4)

Capturas full-page más el texto de cada página, en FC (MySQL local) y en YC
(`data/dev_collection.json`): `tasks/baseline/` (ignorado por git, local).
Notas completas: `tasks/baseline/NOTES.md`. Script de captura:
`tasks/baseline/pw2.py` (Playwright con Python de Windows y Edge;
la MCP de Playwright no funciona en este WSL).

Ninguna página muestra excepciones en ningún modo.

Números que el refactor no puede cambiar:

| Página | FC | YC |
|---|---|---|
| Overview | 2,671 tracks únicos · 882 artistas · 14 playlists · pop 60.7 · era mediana 1994 | 499 únicos · 296 artistas · 6 playlists · pop 51.5 · era 1993 |
| Playlist Detail | 507: 195 tracks, 92 artistas, top Frank Sinatra 19 | Américain Rap 90-2000: 114 tracks, 89 artistas |
| Artist/Album | #1 The Beatles, 75 tracks, 19 álbumes | — |
| Comparison | 112 duplicados exactos · 8 versiones distintas | 2 · 3 |
| Audio DNA | Happy 51.1 % · Turbulent 22.5 % · Peaceful 9.1 % · Dark 17.2 % | 46.5 · 19.8 · 10.6 · 23.1 % |
| My Clusters | 2,564 seleccionados (k=auto) + 107 sin AF | 415 seleccionados; banner "505 tracks" |
| Cluster Results (KMeans auto) | k=2: Euphoric Bangers 1750, Acoustic Ballads 814; 107 unmatched | k=2: Euphoric Bangers 305, Melancholic 110; 84 unmatched |

No cubierto: expanders y toggles, modos "por categoría" y "por género
específico", y botones destructivos o de export. Esos quedan cubiertos por los
tests y por el recorrido del checkpoint 3.

## Tiempos de render (T3)

Comando (5 corridas, `call` de cada test; WSL, Python de Anaconda, Streamlit 1.55, 44 tests en verde):

```
/mnt/c/Users/facur/anaconda3/python.exe -m pytest tests/test_smoke_pages.py -q -p no:cacheprovider --durations=0
```

Mediana y rango min-max de las 5 corridas (suma de la fila `x9`: los tests de import que pytest lista, cada uno en milisegundos; los de menos de 5 ms, como `test_album_goto_redirects_to_artist_album`, no aparecen). Total de la suite de smoke: 23.2-24.2 s. El primer test en cargar un modo paga el arranque en frío (imports, caché de Streamlit).

| test | median s | min-max s |
|---|---|---|
| `test_my_clusters_run_redirects_to_results` | 4.59 | 4.52-4.72 |
| `test_page_renders[1_Overview-FC]` | 1.11 | 1.06-1.18 |
| `test_cluster_results_renders[kmeans-YC]` | 0.98 | 0.92-1.11 |
| `test_page_renders[6_My_Clusters-FC]` | 1.02 | 0.90-1.47 |
| `test_cluster_results_renders[kmeans-FC]` | 0.88 | 0.86-0.96 |
| `test_page_renders[2_Playlist_Detail-FC]` | 0.68 | 0.61-0.69 |
| `test_page_renders[4_Playlist_Comparison-YC]` | 0.27 | 0.26-0.35 |
| `test_page_renders[1_Overview-YC]` | 0.37 | 0.30-0.39 |
| `test_page_renders[5_Audio_DNA-YC]` | 0.30 | 0.28-0.66 |
| `test_page_renders[0_home-FC]` | 0.29 | 0.28-0.33 |
| `test_page_renders[2_Playlist_Detail-YC]` | 0.27 | 0.26-0.31 |
| `test_page_renders[3_Artist_Album-YC]` | 0.23 | 0.23-0.26 |
| `test_page_renders[5_Audio_DNA-FC]` | 0.24 | 0.23-0.38 |
| `test_page_renders[6_My_Clusters-YC]` | 0.22 | 0.22-0.28 |
| `test_cluster_results_renders[category-FC]` | 0.20 | 0.20-0.21 |
| `test_cluster_results_renders[category-YC]` | 0.20 | 0.20-0.22 |
| `test_page_renders[4_Playlist_Comparison-FC]` | 0.17 | 0.16-0.18 |
| `test_page_renders[3_Artist_Album-FC]` | 0.16 | 0.15-0.16 |
| `test_cluster_results_without_results_offers_way_back` | 0.14 | 0.13-0.15 |
| `test_page_renders[7_Glossary-FC]` | 0.06 | 0.06-0.14 |
| `test_yc_without_collection_shows_prompt[6_My_Clusters]` | 0.11 | 0.10-0.15 |
| `test_page_renders[0_home-YC]` | 0.07 | 0.07-0.07 |
| `test_yc_without_collection_shows_prompt[3_Artist_Album]` | 0.04 | 0.04-0.05 |
| `test_yc_without_collection_shows_prompt[2_Playlist_Detail]` | 0.04 | 0.04-0.04 |
| `test_yc_without_collection_shows_prompt[4_Playlist_Comparison]` | 0.03 | 0.03-0.04 |
| `test_yc_without_collection_shows_prompt[1_Overview]` | 0.03 | 0.03-0.04 |
| `test_enrich_without_playlists_redirects_home` | 0.02 | 0.02-0.03 |
| `test_yc_without_collection_shows_prompt[5_Audio_DNA]` | 0.02 | 0.02-0.03 |
| `test_page_renders[7_Glossary-YC]` | 0.02 | 0.02-0.02 |
| `test_page_renders[8_Contact-FC]` | 0.01 | 0.01-0.01 |
| `test_page_renders[8_Contact-YC]` | 0.01 | 0.01-0.01 |
| `test_page_does_not_import_other_pages[x9 listados, suma]` | 0.13 | 0.12-0.22 |

