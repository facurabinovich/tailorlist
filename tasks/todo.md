# Tareas: refactor de arquitectura

Plan: [`plan.md`](plan.md) · Spec: [`SPEC.md`](../SPEC.md)

Comando de tests (desde WSL):
`PY=/mnt/c/Users/facur/anaconda3/python.exe; $PY -m pytest -q -p no:cacheprovider`

**Definition of Done de cada task:** suite en verde, ningún test borrado ni
debilitado, un commit por task y los patches migrados en el mismo commit.

---

## Fase 0: red de seguridad

- [x] **T1: Diagnosticar y arreglar los 9 tests rojos** · S
  - Acceptance: los 6 tests de `download_button` encuentran el botón con la API de Streamlit 1.55, con la misma aserción. Para los 3 tests YC, se confirma si `load_uc_session` puede devolver `uc_skipped` como lista de `str`: si no puede, se actualiza el fixture; si puede, se registra como bug y se avisa.
  - Verify: suite completa, 391/391.
  - Files: `tests/test_analytics_identity.py`, `tests/test_audio_dna.py`, `tests/test_my_clusters.py`.

- [x] **T2: `tests/conftest.py` con guardia de DB y entorno fijo** · S
  - Acceptance: durante los tests, crear un engine real lanza un error con un mensaje claro, y lo mismo pasa con las llamadas HTTP salientes (`requests` y `spotipy`: ReccoBeats/Spotify), salvo que el test las mockee. Además, la suite deja de depender del `.env` local: hoy `spotify_client` hace `load_dotenv(override=True)` al importarse y los tests heredan `DEV_MODE=1` del `.env`. El `conftest` fija `DEV_MODE=1` explícitamente (el valor efectivo actual), después de que corra ese `load_dotenv`. La suite sigue verde; si aparece un test que pegaba a la DB o a la red, se registra y se arregla.
  - Verify: suite completa, más tests que confirman que las guardias disparan. Correr la suite con el `.env` renombrado temporalmente da el mismo resultado.
  - Files: `tests/conftest.py`.

- [x] **T3: Smoke tests de todas las páginas** · M
  - Acceptance: `tests/test_smoke_pages.py` renderiza las 12 páginas con `AppTest` sin excepción, en modo FC y en modo YC (donde aplique), reusando los mocks de los tests existentes. Las páginas que redirigen sin estado (`_album_goto`, `_Enrich` sin enriquecimiento en curso, Cluster Results sin resultados) se verifican por la redirección esperada, no por el render; ningún test existente prueba `switch_page` con `AppTest`, así que primero se confirma cómo lo expone Streamlit 1.55. También verifica que ninguna página importa otra página.
  - Verify: `pytest tests/test_smoke_pages.py` en verde; `--durations=0` en 5 corridas, con la mediana por página guardada en `tasks/perf-baseline.md`.
  - Files: `tests/test_smoke_pages.py`, `tasks/perf-baseline.md`.

- [x] **T4: Línea base visual** · S
  - Acceptance: app real (`DEV_MODE=1`, MySQL local) con capturas de cada página en FC, y en YC con `dev_collection.json` (Home lo carga solo en `DEV_MODE=1`, `0_home.py:63`). Se guardan fuera del repo (scratchpad) y se listan en `tasks/perf-baseline.md`.
  - Verify: capturas presentes para todas las páginas.
  - Files: `tasks/perf-baseline.md`.

### ✅ Checkpoint 0
- [x] Suite 100 % verde (436, independiente del orden), guardia de DB activa, smoke tests de todas las páginas y línea base registrada.
- [ ] Revisión con Facu antes de mover código.

---

## Fase 1: cimientos

- [x] **T5: `config.py`: entorno cargado una vez y `is_dev_mode()`** · M
  - Acceptance: el `.env` se carga en un solo lugar (`config.py`), con la misma semántica que hoy (`override=True`, como `spotify_client.py:19`). Se eliminan los `load_dotenv()` repartidos en `db/connection.py`, `utils.py`, `spotify_client.py` y `0_home.py`; `pipeline/`, `scripts/` y `monitoring.py` quedan como están (fuera de alcance). `is_dev_mode()` lee el entorno en cada llamada, con default `"0"`, y lo usan `config.py`, `db/connection.py` (hoy congela `_DEV_MODE` al importarse), `spotify_client.py` y `utils.py`. Los tests que hacen `import spotify_client` para forzar el orden de `load_dotenv` siguen funcionando, o pasan a depender del `conftest`.
  - Verify: suite; test unitario de `is_dev_mode` (sin definir, `"0"`, `"1"`); app real arranca en `DEV_MODE=1` contra el MySQL local.
  - Files: `config.py`, `db/connection.py`, `spotify_client.py`, `utils.py`, `tests/test_config.py` (más una línea en `0_home.py`).

- [x] **T6: `app_state/session.py`: modos y helpers de sesión** · M
  - Acceptance: las constantes `MODE_YC` y `MODE_FC` tienen el mismo texto exacto que hoy. `read_cookie`, `resolve_sid`, `forget_uc_session` y `mark_uc_session_unavailable` se mueven desde `utils.py`, que las re-exporta. `utils.py` y `db/queries.py` usan las constantes.
  - Verify: suite (`test_sid_recovery` y `test_analytics_identity` incluidos).
  - Files: `app_state/__init__.py`, `app_state/session.py`, `utils.py`, `db/queries.py`.

- [x] **T7: Páginas usan `is_dev_mode()` y las constantes de modo** · M (mecánico, 9 páginas)
  - Acceptance: ninguna página lee `os.getenv("DEV_MODE")` ni compara contra el literal `"🔗 Your Collection"`.
  - Verify: suite; `grep -rn 'getenv("DEV_MODE"\|Your Collection"' pages/` sin resultados.
  - Files: las 9 páginas con el literal (`0_home`, `1_Overview`, `2_Playlist_Detail`, `3_Artist_Album`, `4_Playlist_Comparison`, `5_Audio_DNA`, `6_My_Clusters`, `_Enrich`, `_Cluster_Results`). Excede las 5, pero es un reemplazo mecánico que conviene hacer de una vez.

- [x] **T8: `ui/theme.py` y `ui/nav.py`** · M
  - Acceptance: `inject_global_css`, `inject_sidebar_nav`, `spotify_icon_html`, `page_brand_html` y `check_collection_mode` se mueven a `ui/`. Las páginas importan desde `ui`, y los ~90 patches `utils.*` se migran.
  - Verify: suite; smoke tests.
  - Files: `ui/__init__.py`, `ui/theme.py`, `ui/nav.py`, `utils.py`, las páginas (cambio de una línea de import) y los tests (rutas de patch).
  - Nota: toca más de 5 archivos, pero es un cambio mecánico de imports. Se acepta así para no dejar la app a medio migrar.

- [x] **T9: `core/formatting.py`: `fmt_duration`** · S  *(replanificada: ver H6)*
  - Acceptance: las 3 copias idénticas (Overview, Playlist Detail, Comparison) pasan a `core/formatting.fmt_duration`, movidas tal cual, incluido el bug H6. Artist/Album conserva su versión (que es distinta y correcta) hasta que se decida H6. Hay tests de caracterización de la salida actual, con el caso 3.999 → "3:60" documentado como comportamiento existente.
  - Verify: suite; `tests/test_formatting.py`.
  - Files: `core/__init__.py`, `core/formatting.py`, las 3 páginas y `tests/test_formatting.py`.

- [x] **T10: `ui/components.py`: helpers idénticos de clusters** · S  *(replanificada)*
  - Acceptance: `cluster_card`, `info_box` y `hr` (idénticos en My Clusters y Cluster Results) se definen una vez en `ui/components.py`, con un test de caracterización del HTML previo. `kpi_card`, `section_title`, `_verbose_description` y `_load_unmatched` DIFIEREN entre las dos páginas: no se unifican. Se reporta qué difiere y si parece un arreglo aplicado en una sola página. `_load_unmatched_fc` (idéntico) queda para T18 (`app_state/clusters.py`).
  - Verify: suite; `tests/test_ui_components.py`.
  - Files: `ui/components.py`, `pages/6_My_Clusters.py`, `pages/_Cluster_Results.py` y `tests/test_ui_components.py`.

- Nota sobre `kpi_card`: las 5 copias son 5 diseños distintos (tamaños, layout y escape de HTML). Unificarlas es una decisión de diseño que se toma en el revamp visual, no en este refactor. En la Fase 4 pueden moverse a `ui/` con nombres propios si eso adelgaza las páginas.

### ✅ Checkpoint 1
- [x] Suite verde y smoke tests verdes (455, en ambos órdenes).
- [x] App real: recapturadas las 20 combinaciones de página y modo, con texto idéntico a la línea base y 19/20 capturas idénticas píxel por píxel (la otra difiere en 1 px de antialiasing). Sin tracebacks nuevos (2026-10-11).

---

## Fase 2: capa de datos

- [x] **T11: Partir `db/queries.py`** · M
  - Acceptance: `db/tracks.py`, `db/progress.py`, `db/sessions.py` y `db/analytics.py` con el código movido tal cual. `db/queries.py` solo re-exporta. Ninguna página cambia todavía.
  - Verify: suite (los patches `db.queries.*` siguen funcionando porque las páginas todavía importan de ahí).
  - Ojo: `db.queries` liga `get_engine` por nombre al importarse. Los tests parchean `db.queries.get_engine` además de `db.connection.get_engine`. Al partir el módulo, cada submódulo que importe `get_engine` necesita su propio patch, o un fixture compartido en `conftest`. Verificar la suite en orden invertido (`$(ls tests/test_*.py | sort -r)`).
  - Files: `db/*.py`.

- [x] **T12: `app_state/collection.py` y `core/tracks.py`** · M
  - Acceptance: `get_tracks`, `get_all_tracks`, `get_cluster_data` y `get_audio_features_by_playlist` (que deciden FC/YC según la sesión) salen de `db/`. La normalización de registros YC y `parse_release_year` van a `core/tracks.py`, con tests propios. Las páginas y los patches se migran.
  - Verify: suite; tests de `core/tracks.py` (formatos de fecha, IDs sintéticos, rename de columnas).
  - Files: `app_state/collection.py`, `core/tracks.py`, `db/tracks.py`, las páginas de datos y sus tests (si son más de 5, se parte por grupos de páginas).

- [x] **T13: Sacar el SQL de las páginas** · M
  - Acceptance: los 5 bloques de SQL inline (`0_home.py` ~626, `_Enrich.py` ~199, `_Cluster_Results.py` ~869, ~1203 y ~1359) pasan a ser funciones con nombre en `db/sessions.py` o `db/progress.py`, con la misma SQL, los mismos parámetros y el mismo manejo de errores. `grep -n "text(\|execute(" pages/` no da resultados.
  - Verify: suite; tests unitarios con un engine mockeado que verifican la SQL y los parámetros; corrida opcional con `DEV_MODE=0` y `DATABASE_URL` apuntando al MySQL local.
  - Files: `db/sessions.py`, `db/progress.py`, `pages/0_home.py`, `pages/_Enrich.py`, `pages/_Cluster_Results.py`.

- [x] **T14: Partir `spotify_client.py`** · M
  - Acceptance (adicional): `ui/nav.py` deja de importar `db/`; el tracking de page views pasa por una función de `app_state`.
  - Acceptance: `spotify/client.py` sin Streamlit-UI, `ui/export.py` con `render_export_to_spotify`, y `log_export_event` en `db/analytics.py`. `spotify_client.py` re-exporta. Se migran los 9 patches `spotify_client.render_export_to_spotify`. Los `import spotify_client` que los tests usan para el orden de `load_dotenv` ya no hacen falta después de T5; se reemplazan o se quitan.
  - Verify: suite (`test_analytics_identity` incluido).
  - Files: `spotify/__init__.py`, `spotify/client.py`, `ui/export.py`, `db/analytics.py`, `spotify_client.py`, más las páginas que lo usan.

### ✅ Checkpoint 2
- [x] Suite verde y smoke tests verdes (487, en ambos órdenes).
- [x] App real: 20/20 textos idénticos byte a byte a la línea base, 20/20 capturas idénticas píxel por píxel y sin errores nuevos en el log (2026-10-11). El arreglo de H6 no se ve porque ningún dato cae en el caso ":60".

---

## Fase 3: dominio de clusters

- [ ] **T15: `core/genres.py` y test de arquitectura** · M
  - Acceptance: `GENRE_FAMILIES`, `_assign_family`, `_track_matches_families` y `_preview_filter` en `core/genres.py`. `tests/test_my_clusters.py` borra sus copias espejo y las importa, con las mismas aserciones. Se agrega `tests/test_architecture.py`: `core/` no importa `streamlit` y no hay SQL en `pages/`.
  - Verify: suite.
  - Files: `core/genres.py`, `pages/6_My_Clusters.py`, `tests/test_my_clusters.py`, `tests/test_architecture.py`.

- [ ] **T16: `core/clustering.py`** · M
  - Nota de T10: `_verbose_description` es lógicamente idéntica en ambas páginas (difiere solo en comentarios); `section_title` y `_load_unmatched` son idénticas byte a byte. Se pueden deduplicar sin riesgo de lógica.
  - Acceptance: el núcleo de KMeans/PCA, `_make_names`, `_verbose_description` (deduplicada con Cluster Results), `compute_k_metrics` y `_best_k` quedan como funciones puras que reciben el df explícito. El wrapper cacheado preserva el keying actual (H1 se pregunta, no se cambia en silencio).
  - Verify: suite; los tests espejo de naming y clustering importan el código real; los resultados con un df fijo son idénticos (mismos labels con `random_state=42`).
  - Files: `core/clustering.py`, `app_state/clusters.py`, `pages/6_My_Clusters.py`, `pages/_Cluster_Results.py`, `tests/test_my_clusters.py`.

- [ ] **T17: `core/grouping.py`** · S
  - Acceptance: `run_category_grouping`, `run_specific_genre_grouping` y `_rd_to_decade` puros, con tests que los importan.
  - Verify: suite.
  - Files: `core/grouping.py`, `pages/6_My_Clusters.py`, `tests/test_my_clusters.py`.

- [ ] **T18: `app_state/clusters.py`: carga y unmatched** · M
  - Acceptance: `load_data`, `load_data_fc`, `load_all_grouping_fc` y `_load_unmatched` (deduplicado con Cluster Results) están en un solo lugar. El botón "Refresh track library" sigue limpiando las cachés correctas, con un test explícito.
  - Verify: suite; test del Refresh; app real: My Clusters → configurar → ver resultados en FC.
  - Files: `app_state/clusters.py`, `pages/6_My_Clusters.py`, `pages/_Cluster_Results.py`, tests.

- [x] **T18b: `core/export.py`: texto para Spotlistr** · S  *(pedido de la revisión del pivot)*
  - Acceptance: el armado de las líneas "Artista - Tema" que hoy vive dentro de `ui/export.render_export_to_spotify` (~25 y ~150) pasa a una función pura y tipada (p. ej. `spotlistr_lines(tracks: pd.DataFrame) -> str`), con un test de caracterización de la salida exacta. `ui/export.py` la llama y la UI queda idéntica. La va a usar la tool `export_playlist`.
  - Verify: suite; caracterización.
  - Files: `core/export.py`, `ui/export.py`, `tests/test_core_export.py`.

### ✅ Checkpoint 3
- [ ] Suite verde y test de arquitectura verde.
- [ ] App real: los 3 modos de agrupación (KMeans auto/manual, por categoría, por género específico) en FC y YC, con asignación manual, guardado de progreso, reset y re-apertura.
- [ ] Revisión con Facu (es la mitad del trabajo).

---

## Fase 4: páginas finas
**Prioridad por el pivot:** primero la lógica de dominio a `core/`, con firmas tipadas, porque van a ser tools (sobre todo duplicados y versiones de Comparison y los perfiles de Audio DNA). Mover HTML a `ui/` solo si es barato.

Cada task: lógica restante a `core/` (con tests que importan el código real en
lugar de copiarlo), HTML repetido a `ui/`, secciones en funciones `render_*`
cuando no dependen de un montón de globales. La meta es ~500 líneas por
página; si una queda por encima, se justifica en el commit.

- [ ] **T19: Overview** · M
- [ ] **T20: Playlist Detail** · M
- [ ] **T21: Artist/Album** (más `_album_goto`) · M
- [ ] **T22: Playlist Comparison** (lógica de duplicados exactos y versiones distintas a `core/`) · M
- [ ] **T23: Audio DNA** (layout y colores a `ui/charts.py`) · M
- [ ] **T24: Glossary y Contact** · S
- [ ] **T25: Home y Enrich** (flujo YC: playlists en la URL, recuperación de sid, ETA) · M
- [~] ~~**T26: My Clusters (render)**~~: cancelada por el pivot. El agente reemplaza este flujo; su lógica ya se extrae en T15–T18.
- [~] ~~**T27: Cluster Results (render)**~~: cancelada por el pivot.

  Para cada una:
  - Acceptance: misma salida visible, tests de la página importando el código real y página con un tamaño razonable.
  - Verify: suite, smoke test y recorrido real de esa página en FC y YC.

### ✅ Checkpoint 4
- [ ] Suite verde y recorrido real completo de todas las páginas.

---

## Fase 5: cierre

- [ ] **T28: Eliminar shims** · S
  - Acceptance: `db/queries.py`, `utils.py` y `spotify_client.py` eliminados y ningún import los referencia. Fuera de `pages/`, el único que importa de `db/` es `monitoring.py`, vía `db.connection.get_engine`, que no cambia (verificado). El comentario de H2 se corrige.
  - Verify: suite; `grep`.
- [ ] **T29: Comparación final** · S
  - Acceptance: tiempos de los smoke tests (mediana de 5) frente a la línea base, sin una regresión mayor al 20 % que supere la varianza. Capturas finales frente a las de la línea base, sin diferencias visibles.
  - Verify: `tasks/perf-baseline.md` actualizado con el antes y el después.
- [ ] **T30: Documentación y revisión** · S
  - Acceptance: sección de arquitectura en el README (capas y regla de dependencias). Checklist de criterios de éxito del spec completo. Revisión con `/review`.
  - Verify: todos los criterios de `SPEC.md` tildados.

### ✅ Checkpoint final
- [ ] Todos los criterios de éxito de `SPEC.md` cumplidos.
- [ ] Facu aprueba el merge a `main`.
