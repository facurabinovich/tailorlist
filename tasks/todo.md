# Tareas: refactor de arquitectura

> **Para retomar (2026-10-11, fin de la sesión):** Fases 0–3 completas y verificadas en la app real (Checkpoints 0–3). Fase 3b completa (2026-10-12, Checkpoint 3b). Fase 4 completa (Checkpoint 4, 2026-10-12); Fase 5: T28–T29 hechas; sigue T30 (README y revisión). Suite: 977 tests, ~1–3 min. Hallazgos abiertos en `plan.md`: H7, H9, H11–H13, H15–H19 (H2, H3 y H8 resueltos).

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

- [x] **T15: `core/genres.py` y test de arquitectura** · M
  - Acceptance: `GENRE_FAMILIES`, `_assign_family`, `_track_matches_families` y `_preview_filter` en `core/genres.py`. `tests/test_my_clusters.py` borra sus copias espejo y las importa, con las mismas aserciones. Se agrega `tests/test_architecture.py`: `core/` no importa `streamlit` y no hay SQL en `pages/`.
  - Verify: suite.
  - Files: `core/genres.py`, `pages/6_My_Clusters.py`, `tests/test_my_clusters.py`, `tests/test_architecture.py`.

- [x] **T16: `core/clustering.py`** · M
  - Nota de T10: `_verbose_description` es lógicamente idéntica en ambas páginas (difiere solo en comentarios); `section_title` y `_load_unmatched` son idénticas byte a byte. Se pueden deduplicar sin riesgo de lógica.
  - Acceptance: el núcleo de KMeans/PCA, `_make_names`, `_verbose_description` (deduplicada con Cluster Results), `compute_k_metrics` y `_best_k` quedan como funciones puras que reciben el df explícito. El wrapper cacheado preserva el keying actual (H1 se pregunta, no se cambia en silencio).
  - Verify: suite; los tests espejo de naming y clustering importan el código real; los resultados con un df fijo son idénticos (mismos labels con `random_state=42`).
  - Files: `core/clustering.py`, `app_state/clusters.py`, `pages/6_My_Clusters.py`, `pages/_Cluster_Results.py`, `tests/test_my_clusters.py`.

- [x] **T17: `core/grouping.py`** · S
  - Acceptance: `run_category_grouping`, `run_specific_genre_grouping` y `_rd_to_decade` puros, con tests que los importan.
  - Verify: suite.
  - Files: `core/grouping.py`, `pages/6_My_Clusters.py`, `tests/test_my_clusters.py`.

- [x] **T18: `app_state/clusters.py`: carga y unmatched** · M
  - Acceptance: `load_data`, `load_data_fc`, `load_all_grouping_fc` y `_load_unmatched` (deduplicado con Cluster Results) están en un solo lugar. El botón "Refresh track library" sigue limpiando las cachés correctas, con un test explícito.
  - Verify: suite; test del Refresh; app real: My Clusters → configurar → ver resultados en FC.
  - Files: `app_state/clusters.py`, `pages/6_My_Clusters.py`, `pages/_Cluster_Results.py`, tests.

- [x] **T18b: `core/export.py`: texto para Spotlistr** · S  *(pedido de la revisión del pivot)*
  - Acceptance: el armado de las líneas "Artista - Tema" que hoy vive dentro de `ui/export.render_export_to_spotify` (~25 y ~150) pasa a una función pura y tipada (p. ej. `spotlistr_lines(tracks: pd.DataFrame) -> str`), con un test de caracterización de la salida exacta. `ui/export.py` la llama y la UI queda idéntica. La va a usar la tool `export_playlist`.
  - Verify: suite; caracterización.
  - Files: `core/export.py`, `ui/export.py`, `tests/test_core_export.py`.

### ✅ Checkpoint 3
- [x] Suite verde (586) y test de arquitectura verde.
- [x] App real (2026-10-11): las 20 páginas estáticas son idénticas a la línea base. Los flujos se compararon A/B, app original (`e6e5f1c`) contra la refactorizada: KMeans con k=4, por categoría, por género específico, asignación de unmatched más guardado, y vuelta a My Clusters. Todo idéntico en FC y YC, salvo ruido de 1 px y de timing del script. No se probaron reset ni re-apertura, que quedan cubiertos por tests. Scripts en `tasks/qa-tools/`.
- [x] Revisión con Facu: decidió eliminar FC (Fase 3b).

---

## Fase 3b: eliminar el modo Demo Collection (FC), decisión de Facu (2026-10-11)
Arranca después del Checkpoint 3, que valida las Fases 1–3 con FC todavía presente. Un commit por task y suite verde en cada uno. Al terminar, la app sigue mostrando en YC exactamente lo de la línea base.

- [x] **R1: Un solo modo: sesión, navegación y Home** · M
  - Hecho (2026-10-12): la nav pone `mode=YC` por defecto (sin pisar un modo explícito; los tests FC de páginas siguen hasta R2/R3) y `MODE_FC` queda definido hasta R2–R4. Decisión de Facu (opción A): el banner "Session expired" (copy ajustado), About, Powered by y el footer pasan de la rama FC de Home a YC; se borran el header demo y las feature cards. App real: 9 páginas sin excepciones; textos = línea base salvo el selector y esos bloques de Home; `?mode=demo` da la misma Home. Suite 593 en ambos órdenes.
  - Acceptance: sin selector de modo en la navegación. `st.session_state["mode"]` deja de decidir nada, y la app siempre trabaja con la colección del usuario. Sale `MODE_FC`, y `MODE_YC` solo queda si algo lo sigue necesitando. Home ya no tiene la sección "DEMO COLLECTION MODE". El deep-link `?mode=` se ignora sin error. La auto-carga de `dev_collection.json` en `DEV_MODE=1` sigue igual, y lo mismo la recuperación de sesión (`?sid=`/cookie), `?playlists=`, enrich y borrar sesión.
  - Verify: suite (los smoke tests FC se eliminan o se migran a YC); app real: Home sin colección muestra el input de URL; con dev collection, todo como en la línea base YC.
  - Files: `app_state/session.py`, `ui/nav.py`, `pages/0_home.py`, tests.
- [x] **R2: Páginas de datos solo YC** · M
  - Hecho (2026-10-12): páginas 1–5 sin ramas FC; `app_state/collection.py` solo lee la sesión (sin colección devuelve un frame vacío, nunca la DB) y se borraron los wrappers de H8. `get_all_tracks()` también lista los tracks cuando ninguno tiene audio features (enrich terminado con `uc_enriched` vacío; antes caía a la DB). `check_collection_mode` sigue mirando el modo hasta R3. App real: los 9 textos y capturas son idénticos a R1. Suite: 600 en ambos órdenes.
  - Acceptance: Overview, Playlist Detail, Artist/Album, Comparison y Audio DNA sin ramas FC. `app_state/collection.py` sin la rama DB, y H8 (los wrappers sin uso) se elimina. `check_collection_mode` sigue mostrando "No collection yet" sin colección.
  - Verify: suite; los textos YC de esas páginas son idénticos a la línea base.
  - Files: las 5 páginas, `app_state/collection.py`, tests.
- [x] **R3: My Clusters y Cluster Results solo YC** · M
  - Hecho (2026-10-12): sin ramas FC ni botón Refresh; `load_data()`/`_load_unmatched()` sin `mode` y sin loaders FC; `check_collection_mode` mira solo `uc_active`. `user_key` queda `uc_session_id` o `"anonymous"`. App real: los 11 pasos de los flujos (KMeans k=4, categoría, género específico, asignación manual con guardado y vuelta a My Clusters) dan texto idéntico a una referencia corrida sobre R2 (que a su vez coincide con `checkpoint3/new/YC_*` salvo el selector); capturas idénticas salvo 1 px de antialiasing y un aviso capturado a mitad de rerun. 9 páginas estáticas idénticas a R2. Suite: 600 en ambos órdenes.
  - Acceptance: sin ramas FC, sin el botón Refresh (solo FC), sin los loaders FC cacheados en `app_state/clusters.py`. Los tres modos de agrupación siguen andando en YC, y también la asignación manual, el progreso, el reset y la re-apertura.
  - Verify: suite; flujos A/B YC del Checkpoint 3 idénticos.
  - Files: `pages/6_My_Clusters.py`, `pages/_Cluster_Results.py`, `app_state/clusters.py`, tests.
- [x] **R4: Código muerto de FC** · S
  - Hecho (2026-10-12): `db/tracks.py` borrado entero (ningún llamador, tampoco en `pipeline/`/`scripts/`), igual que los labels de `config.py`, `MODE_FC`/`MODE_YC` y la clave `"mode"` (My Clusters usa `_clusters_initialized` para la limpieza de primera visita). Decisiones de Facu: Contact pasa a "🎵 My Playlists" / "Curious what I listen to? Here are some of my playlists." (mismos 5 links), y `fc_user` pasa a `anonymous` (`monitoring.py` excluye ambos en "returned YC"). Suite: 599 en ambos órdenes.
  - Pendientes que dejaron R1–R3: `MODE_FC`/`MODE_YC` y la clave `"mode"` (la nav la sigue seteando; ya nadie la lee salvo el clear de primera visita de My Clusters vía `_clusters_mode`), el texto "playlists powering Demo Collection" en `pages/8_Contact.py:102`, y el fallback `"fc_user"` de `session_id` en los eventos de analytics.
  - Acceptance: se borran los loaders del star schema en `db/tracks.py` que ya no usa nadie, `config.PLAYLIST_LABELS`/`_DEV_PLAYLIST_LABELS`/`_DEMO_PLAYLIST_LABELS` si quedan sin uso, y los tests de esos loaders. Se queda lo que YC usa (sessions, progress, analytics, `load_uc_session`…). `pipeline/` no se toca (T28).
  - Verify: suite; grep sin referencias colgando; test de arquitectura verde.

### ✅ Checkpoint 3b
- [x] (2026-10-12) Las 9 páginas idénticas a R3 salvo el texto nuevo de Contact, y los 11 pasos de los flujos idénticos a la referencia sobre R2 (= `checkpoint3/new/YC_*` salvo el selector), sin excepciones ni tracebacks. Capturas en `tasks/checkpoint3b/`.
- [x] Suite verde y app real solo YC: los textos de las 10 páginas son idénticos a `tasks/baseline/YC_*` (salvo el selector de modo y H6), y los flujos de clustering son idénticos a `tasks/checkpoint3/new/YC_*`.

## Fase 4: páginas finas
**Prioridad por el pivot:** primero la lógica de dominio a `core/`, con firmas tipadas, porque van a ser tools (sobre todo duplicados y versiones de Comparison y los perfiles de Audio DNA). Mover HTML a `ui/` solo si es barato.

Cada task: lógica restante a `core/` (con tests que importan el código real en
lugar de copiarlo), HTML repetido a `ui/`, secciones en funciones `render_*`
cuando no dependen de un montón de globales. La meta es ~500 líneas por
página; si una queda por encima, se justifica en el commit.

- [x] **T19: Overview** · M
  - Hecho (2026-10-12): lógica a `core/overview.py` (KPIs, perfil de escucha con `current_year` como parámetro, rankings, distribuciones, timeline y drill-downs; funciones puras con dataclasses). La página pasa de 761 a 591 líneas: quedan ~150 de HTML, ~170 de 5 figuras plotly y ~120 de secciones de clic, que dependen de muchas globales. `tests/test_overview.py` importa el código real (su copia del timeline había divergido, H-T19-1) y se suma `tests/test_core_overview.py` (40 tests). Equivalencia vieja/nueva en 119 valores sobre `dev_collection.json`. App real: las 9 páginas idénticas al Checkpoint 3b. Hallazgos H11–H13. Suite: 660 en ambos órdenes.
- [x] **T20: Playlist Detail** · M
  - Hecho (2026-10-12): lógica a `core/playlist_detail.py`, y duplicados exactos y versiones a `core/duplicates.py` (con `include_playlists` para que T22 lo reuse; misma definición de "versión" que Comparison, y en duplicados exactos difieren alcance, columnas y orden). Página: 897 → 749 líneas (~400 son figuras plotly y tarjetas HTML propias de la página). Tests espejo reemplazados por imports (H14), más `test_core_playlist_detail.py` (35) y `test_core_duplicates.py` (15). Equivalencia: 37 combinaciones de playlist/variante × 20 salidas. App real: las 6 playlists con texto idéntico al de HEAD (`qa-tools/detail_all.py`). Suite: 738 en ambos órdenes.
- [x] **T21: Artist/Album** (más `_album_goto`) · M
  - Hecho (2026-10-12): `core/artist_album.py`. Página: 878 → 660 líneas. `_album_goto` es solo un `switch_page`: sin cambios. Equivalencia: 34 selecciones × 7 variantes de datos. Hallazgo H16.
- [x] **T22: Playlist Comparison** (lógica de duplicados exactos y versiones distintas a `core/`) · M
  - Hecho (2026-10-12): `core/comparison.py`, sobre `core/duplicates.py` (se le agregó `format_playlist_counts`). Página: 713 → 603 líneas. Equivalencia: 264 chequeos (colección, cada playlist, 15 pares y variantes), tablas de duplicados con su orden. Hallazgo H17.
- [x] **T23: Audio DNA** (layout y colores a `ui/charts.py`) · M
  - Hecho (2026-10-12): `core/audio_dna.py`, `ui/charts.py` y `core.formatting.short_name`. Página: 499 → 425 líneas. Equivalencia: JSON de las figuras plotly y HTML en 40 corridas AppTest, vieja contra nueva. Hallazgo H18.
- [x] **T24: Glossary y Contact** · S
  - Hecho (2026-10-12): los términos del glosario y la búsqueda pasan a `core/glossary.py` (`GLOSSARY_TERMS`, `search_terms`, `group_by_section`; base de una tool para explicar términos). Glossary: 326 → 65 líneas. Contact no tiene lógica: sin cambios. App real: vista por defecto y 3 búsquedas idénticas a HEAD (`qa-tools/glossary_search.py`).
- [x] **T25: Home y Enrich** (flujo YC: playlists en la URL, recuperación de sid, ETA) · M
  - Hecho (2026-10-12): `core/home.py` y `core/enrichment.py` (puros), `app_state/home.py` y `app_state/enrichment.py` (sesión). Home y la nav comparten `needs_restore` y `apply_restored_session`; sus diferencias (touch, banner de vencida, manejo de excepciones) quedan en cada uno. Home 797 → 598 líneas, Enrich 457 → 236. Equivalencia: funciones puras sobre la colección y 2000 entradas aleatorias, y una corrida AppTest de Enrich vieja contra nueva con el mismo estado final. Hallazgo H19.
- [~] ~~**T26: My Clusters (render)**~~: cancelada por el pivot. El agente reemplaza este flujo; su lógica ya se extrae en T15–T18.
- [~] ~~**T27: Cluster Results (render)**~~: cancelada por el pivot.

  Para cada una:
  - Acceptance: misma salida visible, tests de la página importando el código real y página con un tamaño razonable.
  - Verify: suite, smoke test y recorrido real de esa página en FC y YC.

### ✅ Checkpoint 4
- [x] (2026-10-12) Suite: 960 en ambos órdenes. App real, rama integrada: las 9 páginas tienen texto y capturas idénticos al Checkpoint 3b; las 6 playlists de Detail son idénticas a T20; los 11 pasos de los flujos de clustering son idénticos a la referencia; Glossary (vista por defecto y 3 búsquedas) es idéntico a HEAD. Sin excepciones ni tracebacks. T21–T25 se hicieron en paralelo, en worktrees, y se integraron con cherry-pick sin conflictos.

---

## Fase 5: cierre

- [x] **T28: Eliminar shims** · S  *(más, con aprobación de Facu: qué hacer con `pipeline/`, que queda sin uso al salir FC)*
  - Acceptance: `db/queries.py`, `utils.py` y `spotify_client.py` eliminados y ningún import los referencia. Fuera de `pages/`, el único que importa de `db/` es `monitoring.py`, vía `db.connection.get_engine`, que no cambia (verificado). El comentario de H2 se corrige.
  - Verify: suite; `grep`.
  - Hecho (2026-10-12): se eliminan `db/queries.py`, `utils.py` y `spotify_client.py`, y todos los imports y patches apuntan al módulo real; el test de arquitectura verifica que no vuelvan. H2 corregido. Decisión de Facu sobre `pipeline/` (rescatar y borrar): `_fetch`, `_map_fields` y `_fetch_fallback` pasan a `spotify/reccobeats.py` como `fetch_audio_features`, `map_audio_features` y `fetch_fallback_features` (mismo AST, con tests nuevos); se borran el ETL, `playlists*.yaml` y el `enrich_tracks_live` sin uso de `spotify/client.py`. `scripts/` queda (`create_schema.py` crea también las tablas de YC). Suite: 977 en ambos órdenes.
- [x] **T29: Comparación final** · S
  - Acceptance: tiempos de los smoke tests (mediana de 5) frente a la línea base, sin una regresión mayor al 20 % que supere la varianza. Capturas finales frente a las de la línea base, sin diferencias visibles.
  - Verify: `tasks/perf-baseline.md` actualizado con el antes y el después.
  - Hecho (2026-10-12): comparación pareja (mismo subconjunto YC, misma máquina, 3 corridas por versión) en `perf-baseline.md`: total +2 %, páginas pesadas entre −8 % y +1 %; Home (+0.08 s) y Cluster Results por categoría (+0.19 s) suben de forma consistente, pero en términos absolutos son menos de 0.2 s. Capturas: las 9 páginas son idénticas al Checkpoint 3b, y este a la línea base YC salvo el selector y los bloques de Home decididos en R1.
- [ ] **T30: Documentación y revisión** · S
  - Acceptance: sección de arquitectura en el README (capas y regla de dependencias). Checklist de criterios de éxito del spec completo. Revisión con `/review`.
  - Verify: todos los criterios de `SPEC.md` tildados.

### ✅ Checkpoint final
- [ ] Todos los criterios de éxito de `SPEC.md` cumplidos.
- [ ] Facu aprueba el merge a `main`.
