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

_Pendiente._
