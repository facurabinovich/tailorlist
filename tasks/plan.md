# Plan de implementación: refactor de arquitectura

Spec: [`SPEC.md`](../SPEC.md) · Rama: `refactor/architecture` · Tareas: [`tasks/todo.md`](todo.md)

## Resumen

Se mueve código de las páginas hacia capas (`core/`, `db/`, `spotify/`,
`app_state/`, `ui/`) en pasos chicos. Cada paso deja la app funcionando y la
suite en verde, y se commitea solo. Orden: primero la red de seguridad, después
los cimientos (config, estado, UI compartida), la capa de datos, el dominio de
clusters y al final las páginas, una por una. Lo más riesgoso (My Clusters y
Cluster Results) va al final, cuando ya está todo lo que esas páginas
necesitan.

## Decisiones de arquitectura

- **Mover tal cual y después mejorar.** Cada movimiento preserva el código
  byte a byte, salvo imports. Las mejoras, si las hay, van en commits propios.
- **Shims temporales para no romper todo de golpe.** Durante la migración,
  `db/queries.py`, `utils.py` y `spotify_client.py` re-exportan desde los
  módulos nuevos. Se eliminan en la Fase 5, cuando ya nadie los importa.
- **Los `patch()` se mueven con el código.** Un test tiene que parchear donde
  el nombre se *busca*, no donde se define. Cada task que cambia un import en
  una página actualiza en el mismo commit los patches que lo apuntan.
- **Funciones cacheadas:** el decorador `@st.cache_data` queda en la capa que
  conoce Streamlit (`db/` o `app_state/`). `core/` recibe datos explícitos y
  devuelve datos, sin caché ni sesión.
- **Las variantes de UI no se fusionan a ciegas.** Las 5 copias de `kpi_card`
  tienen 5 HTML distintos (hashes distintos). Antes de unificar, un test de
  caracterización fija el HTML que genera cada variante para entradas
  representativas; el componente unificado tiene que reproducirlos exactamente.
  Si no se puede sin parámetros absurdos, se conservan variantes con nombre
  propio en `ui/components.py`.
- **Verificación proporcionada** (ver memoria del proyecto): pytest más una
  corrida real de la app en cada checkpoint. Sin harnesses de DB falsa nuevos;
  los smoke tests reusan el patrón de mocks que ya usan los tests de cada
  página. Las capturas se toman una vez antes de empezar y una vez al final.

## Pivot (2026-10-11)

Este refactor es la F0 del pivot a agente LLM (`tasks/agent-pivot.md`; aprobado F1 a F4 en Streamlit, con Foundry Local y sin multi-fuente). Cambios: se cancelan T26 y T27; `core/` va con firmas tipadas y docstrings; la Fase 4 prioriza extraer la lógica de dominio por sobre mover HTML. Detalle en `SPEC.md`.

## Fases

### Fase 0: red de seguridad (T1–T4)
Suite 100 % verde, guardia contra la DB real, smoke tests de todas las páginas,
línea base de tiempos y capturas.

### Fase 1: cimientos (T5–T10)
`DEV_MODE` en un solo lugar, `Mode` como constante, helpers de sesión en
`app_state/session.py`, tema y navegación en `ui/`, componentes compartidos
en `ui/components.py`.

### Fase 2: capa de datos (T11–T14)
`db/queries.py` partido por tema, carga FC/YC en `app_state/collection.py`, SQL
fuera de las páginas, `spotify_client.py` partido.

### Fase 3: dominio de clusters (T15–T18)
Géneros, clustering, agrupación y unmatched a `core/` y `app_state/clusters.py`.
Los tests espejo de My Clusters pasan a importar el código real.

### Fase 4: páginas finas (T19–T27)
Una task por página: lógica restante a `core/`, HTML repetido a `ui/`,
secciones en funciones `render_*`.

### Fase 5: cierre (T28–T30)
Eliminar shims, comparar tiempos y capturas contra la línea base, documentar y
hacer la revisión final.

## Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Un patch deja de interceptar y el test pega a MySQL o pasa por casualidad | Alto | `conftest.py` bloquea engines reales (T2); los patches se migran en el mismo commit |
| Convertir el script de una página en funciones cambia el scope de variables (globales que se leen en otro bloque) | Alto | Fase 4 al final; una página por task; smoke tests más el recorrido real; las secciones que dependen de muchas globales se dejan como están y se documentan |
| Unificar componentes cambia el HTML visible | Medio | Test de caracterización del HTML antes de unificar (T9, T10) |
| `.clear()` de cachés apunta a un objeto viejo después de mover funciones | Medio | Test explícito del botón Refresh (T18) |
| `run_kmeans` lee la global `df_all`, que no está en su clave de caché; al extraerlo, pasar el df cambia el keying | Medio | Registrado como hallazgo (H1). En T16 se preserva el keying actual y se pregunta antes de cambiarlo |
| Las escrituras de producción (`DEV_MODE=0`) no se pueden probar en vivo: la infraestructura no existe | Medio | Tests con mocks; opcionalmente, una corrida con `DEV_MODE=0` y `DATABASE_URL` apuntando al MySQL local |
| Cambiar el default de `DEV_MODE` a `"0"` | Bajo | `.env` local ya define `DEV_MODE=1` (verificado); en tests se fija explícitamente en `conftest` |
| Los resultados de los tests dependen del `.env` local: `spotify_client` hace `load_dotenv(override=True)` al importarse y los tests importan ese módulo a propósito para forzar el orden | Alto | T2 fija el entorno en `conftest` y verifica la suite sin `.env`; T5 centraliza la carga en `config.py` |
| Un smoke test dispara llamadas reales a ReccoBeats o Spotify (`_Enrich`) | Medio | El `conftest` bloquea HTTP saliente (T2) |
| `switch_page` dentro de `AppTest` de un solo archivo: ningún test lo cubre hoy | Bajo | T3 confirma el comportamiento primero; las páginas que redirigen se verifican por la redirección |
| Credenciales de Spotify inválidas tras dar de baja recursos | Bajo | La verificación del modo YC usa `data/dev_collection.json`, sin llamar a la API; el flujo de enrich se cubre con tests |

## Hallazgos registrados (no se arreglan en un movimiento)

- **H1:** `run_kmeans` (`6_My_Clusters.py:589`) está cacheada por
  `(track_ids, k)` pero lee la global `df_all`. Si cambian los datos y los IDs
  son los mismos, devuelve un resultado viejo.
  **Decisión de Facu (2026-10-11): opción 2.** En T16 primero se mueve tal cual
  (mismo keying). Después, en un commit aparte, el DataFrame entra en la clave
  de caché, con medición del costo antes y después.
  **RESUELTO:** `app_state/clusters.py` recibe `df_all` sin guion bajo, así que entra en la clave de caché; costo de un cache hit medido (mediana de 10, set dev completo): `run_kmeans` 13.4 ms -> 20.4 ms, `compute_k_metrics` 12.1 ms -> 14.3 ms.
- **H2:** el comentario de `6_My_Clusters.py:20-21` está desactualizado (Cluster
  Results no importa de My Clusters). **RESUELTO en T28.**
- **H3:** `_Enrich.py` importa funciones privadas de `pipeline/enrich.py` (fuera
  de alcance). **RESUELTO en T28:** las tres funciones pasan a `spotify/reccobeats.py` con nombres públicos y `pipeline/` se elimina (decisión de Facu).
- **H4:** `load_dotenv` se llama en 5 módulos de la app, uno con
  `override=True`. El `.env` local pisa variables del entorno, y el
  resultado depende del orden de importación. Se resuelve en T5.
- **H5:** en YC, el banner de My Clusters dice "505 tracks", mientras que Home y Overview
  dicen 499 (dev collection: 6 duplicados). Es una inconsistencia que ya existía
  antes del refactor y se preserva tal cual.
- **H6 (bug):** `fmt_duration` en Overview, Playlist Detail y Comparison trunca
  minutos y redondea segundos por separado: `3.999` → "3:60". Artist/Album usa
  `divmod` sobre segundos totales y da "4:00". **RESUELTO:** unificado en el algoritmo `divmod`.
- **H8:** `app_state.collection.get_cluster_data()` y
  `get_audio_features_by_playlist()` no tienen ningún llamador (verificado con
  grep). Además, `get_cluster_data()` hace `st.cache_data.clear()` en cada
  llamada FC: si una tool lo usara en loop, borraría todas las cachés. Propuesta:
  eliminarlas en T28, con aprobación de Facu (es código muerto, no funcionalidad). **RESUELTO en R2** (eliminadas junto con la rama DB de `app_state/collection.py`).
- **H9:** `core/export.spotlistr_lines` falla con `AttributeError` si un track
  tiene `artists=None`, igual que el código original. Pendiente para la tool
  `export_playlist` en F1: no debería romperse por un dato faltante.
- **H11 (T19):** el Top Genres de Overview crasheaba (`KeyError`) si existe
  `artist_genres` pero ningún track tiene género. `core.overview.genre_track_counts`
  devuelve ahora un frame vacío con columnas `genre`/`track_count`: único cambio de
  comportamiento de T19 (un crash pasa a ser un treemap vacío), con test.
- **H12 (T19):** los drill-downs de Overview por artista, década, popularidad y
  género ordenan por `popularity_raw` sin guardia: sin esa columna, el clic da
  `KeyError` (el de mes sí tiene guardia). Se preservó (`track_listing(strict_sort=True)`).
  Relevante para las tools si reciben colecciones sin popularidad.
- **H13 (T19):** con `popularity_raw` presente pero toda NaN, el KPI de popularidad
  promedio muestra "nan". Se preservó.
- **H14 (T20):** los espejos de `tests/test_playlist_detail.py` se habían desviado:
  `compute_duplicates` agrupaba por nombre+artista (el page detecta por Spotify ID,
  así que el caso del test era una "versión distinta", no un duplicado exacto) y
  `derive_af_avg_yc` deduplicaba antes de promediar (el page promedia todas las filas).
  Se corrigió el fixture con comentario y se agregó un test del comportamiento real.
- **H15 (T20):** rarezas preservadas en `core/playlist_detail.py`: `track_highlights`
  falla si una columna existe pero es toda NaN; `track_table` falla si algún
  `popularity_raw` es NaN; un `added_at` NaT da un mes "NaT"; con todas las
  distancias iguales, `with_similarity_pct` deja todo vacío. Top genres de Detail
  cuenta tags por fila y el de Overview tracks únicos por substring (definiciones
  distintas). Relevante para las tools.
- **H16 (T21):** Artist/Album: si un artista o álbum elegible tiene `popularity_raw`
  presente pero toda NaN, Highest/Lowest hace `int(NaN)` y da `ValueError` (se preservó).
  La elegibilidad de artistas cuenta filas y el KPI cuenta tracks únicos: un artista
  puede aparecer en el selector y mostrar `enough=False`. La normalización del tempo
  del radar usa el min/max de la colección; la de Playlist Detail, 60–200 BPM fijos.
- **H17 (T22):** el espejo de duplicados cruzados de `test_playlist_comparison.py`
  detectaba por nombre y artista; el page usa Spotify ID ("across or within
  playlists"). Se reescribió sobre registros crudos. `playlist_meta([])` da un frame
  vacío con el que la sección Size fallaría (no se llega: sin colección la página se
  corta antes). El page tenía una tabla de duración por playlist sin uso: queda como
  `core.comparison.duration_by_playlist` para las tools.
- **H18 (T23):** Audio DNA: `format_extreme_value` muestra "< 0.001" para valores de
  ~0.00005–0.00015, y `extreme_tracks` devuelve filas NaN (tarjetas "nan") si una
  feature tiene menos de n valores. Se preservó. `_BASE_LAYOUT` sigue duplicado en
  Playlist Detail y Comparison, y hay variantes inline en Overview y clusters. **T30:** las 4 copias idénticas (Detail, Comparison, My Clusters, Cluster Results) usan `ui.charts.BASE_LAYOUT`; quedan la de Artist/Album (otro diseño) y las variantes inline.
- **H19 (T25):** `playlist_set_key` usa `hash()`, que cambia por proceso: el backfill
  de la fila `enrichment_start` solo funciona dentro del mismo proceso. `confirm_estimate`
  cuenta un registro enriquecido sin id como "ya enriquecido". Se preservó (con test).
- **H10:** los tests espejo de My Clusters (`_track_matches_families` y
  `_preview_filter`) se habían desviado del código de producción. Probaban el
  comportamiento anterior al cambio deliberado del 2026-05-20 ("los tracks sin
  género siempre pasan el filtro de familia"), así que seguían en verde sin
  proteger nada. En T15 se reemplazaron por imports y se corrigieron las 2
  aserciones desactualizadas (TC10 y TC20) al comportamiento real.
- **H7:** `kpi_card` tiene 5 diseños distintos, no 5 copias. Su unificación se
  difiere al revamp visual.
