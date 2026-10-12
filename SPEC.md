# Spec: Refactor de arquitectura de TailorList

Estado: **aprobado** (2026-10-11) · Rama: `refactor/architecture` · 2026-10-11

## Objetivo

Reorganizar el código de TailorList en capas dentro de Streamlit para que sea
legible, testeable y fácil de cambiar, **sin perder ni alterar ninguna
funcionalidad**. Es una refactorización pura: el usuario final no debería
notar ninguna diferencia (mismas páginas, mismos números, mismo look, mismas
URLs, mismos eventos de analytics).

Habilita las fases siguientes del revamp (UX/visual, features), que hoy son
caras porque cada cambio toca archivos de 900–2000 líneas que mezclan todo.

### Diagnóstico (por qué)

| Problema | Evidencia |
|---|---|
| Páginas monolíticas | `6_My_Clusters.py` 1977 líneas, `_Cluster_Results.py` 1400, cinco páginas entre 727 y 910 |
| Lógica de negocio dentro de la UI | KMeans, naming de clusters, familias de género, grouping por categoría, todo en `6_My_Clusters.py` |
| Helpers duplicados | `kpi_card` definido en 5 páginas; `fmt_duration` en 4; `cluster_card`, `info_box`, `hr`, `section_title`, `_verbose_description`, `_load_unmatched` copiados entre My Clusters y Cluster Results (el comentario de `6_My_Clusters.py:20` que dice que Cluster Results importa de ahí está desactualizado: no importa, copia) |
| Tests que no prueban el código real | `tests/test_my_clusters.py` y otros copian la lógica ("mirror pure logic") en vez de importarla; si la página cambia, siguen en verde |
| Capa de datos acoplada a la sesión | `db/queries.get_tracks()` lee `st.session_state["mode"]` para decidir entre MySQL y datos YC |
| SQL crudo dentro de páginas | `_Cluster_Results.py` (~869, ~1203, ~1359), `0_home.py` (~626, borrado de sesión) y `_Enrich.py` (~199) abren conexiones y ejecutan SQL inline |
| Módulos "utilitarios" que mezclan capas | `utils.py` mezcla cookies/sid (estado) con CSS y navegación (UI); `spotify_client.py` mezcla cliente de API, UI (`render_export_to_spotify` usa `st.markdown`/`st.download_button`) y analytics (`log_export_event`) |
| `DEV_MODE` con defaults contradictorios | `config.py` y `db/connection.py` asumen `"1"` si falta; `spotify_client.py` y `utils.py` asumen `"0"`; las páginas comparan contra `None` |
| Strings mágicos | `"🔗 Your Collection"` comparado literalmente en 11 archivos; 58 claves distintas de `session_state` (~490 accesos) sin registro central |
| HTML/CSS inline masivo | ~290 llamadas `unsafe_allow_html` repartidas en las páginas |

## Tech stack (sin cambios)

Python 3.12 · Streamlit ≥1.37 (local 1.55) · pandas 2.2 · SQLAlchemy 2 + PyMySQL ·
scikit-learn · Plotly · spotipy · pytest. **No se agregan dependencias.**

## Comandos

Entorno con dependencias: Python de Anaconda en Windows (desde WSL):

```bash
PY=/mnt/c/Users/facur/anaconda3/python.exe
$PY -m pytest -q -p no:cacheprovider          # suite completa
$PY -m pytest -q -p no:cacheprovider tests/test_smoke_pages.py   # humo de páginas (nuevo)
$PY -m streamlit run app.py                   # app local (DEV_MODE=1 → MySQL local)
```

## Estructura objetivo

```
app.py                  → navegación (sin cambios de rutas)
config.py               → constantes + settings: DEV_MODE leído en UN solo lugar (is_dev_mode())

core/                   → DOMINIO PURO. Prohibido importar streamlit. Funciones de DataFrame→DataFrame.
  genres.py             → familias de género, matching exacto de tokens, filtros de preview
  clustering.py         → KMeans, métricas de k / best_k, naming de clusters, descripciones
  grouping.py           → agrupación por categoría (década/género) y por género específico
  tracks.py             → normalización de registros YC → DataFrame, release_year/decade, dedup, conteos
  formatting.py         → fmt_duration y similares

db/                     → ACCESO A DATOS. Sin lógica de UI. Todo el SQL vive acá.
  connection.py         → engine (usa config.is_dev_mode())
  tracks.py             → loaders del star schema (cacheados)
  progress.py           → progreso de clusters (load/save/reset/bulk)
  sessions.py           → sesiones YC (save/touch/restore)
  analytics.py          → track_event (y lo que hoy es log_export_event / _track de Cluster Results)
  queries.py            → re-exporta temporalmente lo anterior (compatibilidad durante la migración; se elimina al final)

spotify/                → CLIENTE DE SPOTIFY (sin UI): credenciales, extract_playlist_id,
  client.py               get_playlist_tracks, create_spotify_playlist, enrich_tracks_live
                          (spotify_client.py se parte: la UI de export va a ui/export.py)

app_state/              → PUENTE con Streamlit: única capa que conoce session_state y query_params
  session.py            → Mode (FC/YC) como constante, claves de sesión centralizadas,
                          helpers de sid/cookies (read_cookie, resolve_sid, forget_uc_session… de utils.py)
  collection.py         → get_tracks() / get_all_tracks(): decide FC vs YC y llama a db/ o core/

ui/                     → COMPONENTES DE PRESENTACIÓN. Sin lógica de negocio.
  theme.py              → inject_global_css, colores
  nav.py                → sidebar/navegación propia
  components.py         → kpi_card, ranking_card, cluster_card, info_box, section_title, hr, empty states
  charts.py             → layout Plotly compartido, mapas de color
  export.py             → render_export_to_spotify (export / CSV Spotlistr)
  (utils.py desaparece: su contenido se reparte entre ui/ y app_state/)

pages/                  → PÁGINAS FINAS: leen estado, llaman core/db vía app_state, renderizan con ui/.
                          Secciones grandes se parten en funciones render_*() locales o en ui/.

tests/                  → importan el código real; nada de copias de lógica
```

Regla de dependencias (una sola dirección, sin ciclos):

```
pages → ui, app_state, core
ui → app_state, config   (nunca db/ directo)
app_state → db, spotify, core
db → config, core      (puede usar st.cache_data / st.cache_resource; core es la hoja pura)
spotify → config
core → (nada del proyecto salvo config)
```

Ninguna página importa de otra página (hoy ya se cumple; la regla evita que
el arreglo de los duplicados se haga importando entre páginas).

`_Enrich.py` importa funciones privadas de `pipeline/enrich.py`
(`_fetch`, `_map_fields`, `_fetch_fallback`). Como `pipeline/` está fuera de
alcance, ese acoplamiento se deja como está y se anota para más adelante.

**Fuera de alcance:** `pipeline/` (ETL), `ml/` (notebooks), `models/`,
`scripts/`, `monitoring.py` (solo se adapta a `is_dev_mode()` si hace falta),
rediseño visual, features nuevas.

## Estilo de código

Seguir el estilo existente: type hints, docstrings cortos que explican el *por
qué*, separadores `# ---` entre secciones, nombres en inglés. Funciones de
`core/` puras y deterministas:

```python
# core/tracks.py
def parse_release_year(release_date: pd.Series) -> pd.Series:
    """Year from Spotify release_date ("2014", "2014-03" or "2014-03-15").
    Implausible years (<=1900) become None."""
    ...
```

```python
# pages/2_Playlist_Detail.py — después
from app_state.collection import get_all_tracks
from ui.components import kpi_card
from core.formatting import fmt_duration
```

Mover código **tal cual** primero; mejorar después y en commits separados.

## Estrategia de testing

1. **Red de seguridad antes de mover nada:**
   - `tests/test_smoke_pages.py`: cada página renderiza sin excepción con
     `AppTest`, en modo FC (DB mockeada) y en modo YC (sesión sintética).
   - Snapshot de métricas clave por página (conteos de tracks, KPIs, nombres de clusters con datos fijos) para detectar cambios de números.
2. **Al extraer a `core/`:** los tests existentes que copian lógica pasan a
   importar la función real, con las mismas aserciones. No se borra ni se
   debilita ningún test.
3. **Migración de los targets de `patch()`, el riesgo principal.** Los tests
   tienen ~180 `patch("db.queries.…")` y `patch("utils.…")`. Funcionan porque
   las páginas hacen `from db.queries import X` *después* del patch. Cuando una
   página pase a importar desde `app_state`/`ui`, el patch viejo deja de
   interceptar y el test puede terminar **pegándole a la DB real** o pasando
   por casualidad. Por eso:
   - Cada commit que mueve una función actualiza en el mismo commit los
     `patch()` que la apuntan. Es un cambio de *ruta*, no de aserción.
   - Se agrega un `tests/conftest.py` que hace fallar cualquier intento de
     crear un engine real durante los tests, así un patch roto se ve como
     error y no como un acceso silencioso a MySQL.
4. **Test de arquitectura:** falla si algún módulo de `core/` importa
   `streamlit`, o si una página importa otra página.
5. **Verificación en runtime** (proporcional): correr la app al final de cada
   fase y recorrer las páginas en ambos modos; capturas con Playwright antes y
   después de la refactorización para comparar.
6. **Guardia de performance:** tiempo de render por página con `AppTest`,
   mediana de 5 corridas, medido antes de empezar (línea base) y al final. Se
   compara contra la varianza entre corridas, no solo contra la media. Una
   regresión mayor al 20 % que supere esa varianza bloquea el merge.

**Línea base actual:** 382 pasan y 9 fallan. Se diagnostican antes de
refactorizar:
- 6 usan `AppTest.download_button`, que no existe en Streamlit 1.55. Hay que
  adaptar el test para que encuentre el botón por otra vía, con la misma
  aserción.
- 3 (modo YC de Audio DNA y My Clusters) cargan `uc_skipped` en el fixture
  como lista de IDs (`str`), pero la app guarda dicts
  (`_Enrich.py:425`). Probablemente el fixture está desactualizado. Falta
  confirmar que ninguna sesión restaurada desde la DB (`load_uc_session`)
  pueda traer el formato viejo; si puede traerlo, es un bug real y va a un
  commit propio.

## Límites

- **Siempre:** suite en verde antes de cada commit; un movimiento por commit;
  mantener claves de `session_state`, parámetros de URL (`?sid=`,
  `?playlists=`, `?mode=`), nombres y propiedades de eventos de analytics, y
  rutas de páginas exactamente iguales.
- **Preguntar primero:** arreglar un bug encontrado durante la refactorización (se registra
  y se arregla en un commit propio, nunca mezclado con un movimiento); agregar
  dependencias; tocar algo fuera de alcance.
- **Nunca:** cambiar el schema de la DB; cambiar textos, layout o estilos
  visibles; borrar o saltear tests para llegar a verde; editar
  `agent-skills/`; commitear secretos; pushear o mergear a `main` sin
  aprobación.

## Criterios de éxito

- [x] Toda la funcionalidad del inventario sigue funcionando: tests en verde y recorrido manual en FC y YC.
      *(2026-10-12: FC se eliminó por decisión de Facu, la única excepción. YC: 977 tests en verde y recorridos reales en los Checkpoints 3b y 4 y en T30, idénticos a la línea base.)*
- [x] Los 382 tests que hoy pasan siguen pasando, y los 9 que fallan quedan diagnosticados y resueltos o documentados. *(T1. Los tests que probaban comportamiento exclusivo de FC se eliminaron con FC.)*
- [x] Ningún test copia lógica de producción: todos importan el código real. *(Los espejos se reemplazaron en T15–T25 y T30; varios se habían desviado: H10, H14, H17, H-T19-1 y los TC33–38 de naming. Quedan helpers triviales de formato de tarjetas en `test_playlist_comparison.py` y `cluster_pct` en `test_my_clusters.py`, que no corresponden a funciones de producción.)*
- [x] `core/` no importa `streamlit` (lo verifica un test), y sus funciones públicas tienen firmas tipadas y docstrings (base de las tools del agente).
- [x] Ninguna página importa de otra página.
- [x] Cada helper de UI y de formato *idéntico* está definido una sola vez. *(T30: `_BASE_LAYOUT` en 4 páginas pasa a `ui.charts.BASE_LAYOUT`; la de Artist/Album es otro diseño. Un barrido por AST no encuentra funciones con cuerpo idéntico en módulos distintos.)* Las
      variantes que producen salidas distintas (p. ej. las 5 versiones de `kpi_card`)
      no se fusionan acá: quedan documentadas para el revamp visual.
- [x] `DEV_MODE` se lee en un único lugar, con un default único y documentado.
- [x] No queda SQL dentro de `pages/`.
- [~] Ninguna página supera ~500 líneas (hoy el máximo es 1977), salvo My Clusters y Cluster Results (ver pivot). Es un
      objetivo, no una excusa para partir archivos de forma artificial: si una
      página queda en 600 líneas de render cohesivo, se justifica en el PR.
      *(Fin del refactor: Glossary 65, Contact 138, Enrich 236 y Audio DNA 425 quedan por debajo; Overview 591, Home 598, Comparison 600, Artist/Album 660 y Playlist Detail 744 quedan por encima, con lo que resta siendo figuras plotly y HTML propios de cada página, justificado en cada commit. Las de clusters no se adelgazan por el pivot.)*
- [x] Ningún test pega contra una DB real (lo garantiza el `conftest`).
- [~] El render por página no empeora más de un 20 % respecto de la línea base. *(T29: total +2 % y páginas pesadas entre −8 % y +1 %; Home +0.08 s y Cluster Results por categoría +0.19 s superan el 20 % relativo, aunque en términos absolutos son menos de 0.2 s. Ver `tasks/perf-baseline.md`.)*
- [x] `db/queries.py` queda eliminado o reducido a nada (sin shim de compatibilidad colgando).

## Inventario de funcionalidad (no se puede romper)

- **Home:** selector de modo FC/YC, deep-link `?mode=`; YC: agregar/quitar
  playlists por URL, `?playlists=` en la URL, revisión antes de enriquecer,
  recuperación de sesión vía `?sid=` y cookie, borrar datos de sesión, "start
  over", guardar dev collection (DEV).
- **Enrich:** enriquecimiento con ReccoBeats con progreso y ETA, fallback DB,
  persistencia de sesión YC, cancelar.
- **Overview:** KPIs, top artistas/álbumes (toggle top 20), timeline, promedios
  de audio features, selector de género.
- **Playlist Detail:** selector, KPIs, highlights, géneros, tabla de tracks.
- **Artist/Album:** modo artista/álbum, header card, pills de género,
  extremos, ir a álbum (`_album_goto`).
- **Playlist Comparison:** diff de DNA, duplicados exactos y versiones
  distintas, únicos, nota de tamaño.
- **Audio DNA:** radar, distribuciones, tendencias por década, multiselect de
  playlists.
- **My Clusters:** pre-filtros (playlists, décadas, familias de género),
  refresh de librería, 3 modos de agrupación (KMeans auto/manual k, por
  categoría, por género específico con selección por familia), conteos de 3
  niveles, progreso persistido, reset, re-abrir, banner de 100 %.
- **Cluster Results:** cards por cluster, asignación manual de unmatched
  (fragment), guardar asignaciones, export a Spotify / CSV Spotlistr, crear
  playlist, renombrar, keep visible, skip remaining, reconfigurar.
- **Glossary** (búsqueda) y **Contact**.
- **Transversal:** navegación propia del sidebar, CSS global, analytics
  (visitor_id cookie, eventos), banner de sesión expirada, `check_collection_mode`.
- **Invalidación de caché:** "Refresh track library" en My Clusters
  (`load_data_fc.clear()` y `load_all_grouping_fc.clear()`, el arreglo del bug
  de OG Rap), `st.cache_data.clear()` en Overview y al volver al modo FC
  (`db/queries.py:382`). Al mover funciones cacheadas, cada `.clear()` tiene
  que seguir apuntando al objeto correcto. Va con un test explícito.

## Decisiones (antes preguntas abiertas)

1. **`DEV_MODE` sin definir → `"0"` (producción).** Se lee en un solo lugar
   (`config.is_dev_mode()`). Sin `DATABASE_URL` falla con un error claro.
2. **Bugs encontrados durante la refactorización:** se registran en
   `tasks/todo.md`, se avisa y se arreglan en commits propios, nunca mezclados
   con un movimiento.
3. **MySQL local disponible** (verificado el 2026-10-11: 19 tablas, 2783 filas
   en `fac_songs`). El modo FC se verifica en vivo además de con tests.

## Pivot aprobado (2026-10-11) y consecuencias para este refactor

Facu aprobó el pivot de `tasks/agent-pivot.md` con este alcance: **F1 a F4 en
Streamlit, con Foundry Local como LLM y sin multi-fuente**. F5 (cambio de stack),
la parte de negocio y multi-fuente no están aprobados. El refactor es la fase
F0 del pivot.

- **`core/` es la base de las tools del agente.** Funciones con firmas
  completamente tipadas, docstrings claras (el LLM las lee) y entradas/salidas
  simples: DataFrames, dicts y escalares; nada de `st.*` ni de estado global.
- **El flujo de armado de playlists (My Clusters + Cluster Results) lo va a
  reemplazar el agente.** Hasta que eso pase tiene que seguir funcionando igual
  ("no perder funcionalidad" sigue vigente), pero no se invierte en adelgazar su
  UI: se cancelan T26 y T27. Su lógica sí se extrae a `core/` (T15–T18), porque
  la usan las tools.
- **Las demás páginas quedan como "Vistas"** del agente. En la Fase 4, la
  prioridad es extraer su lógica de dominio a `core/` (p. ej. duplicados y
  versiones de Comparación, perfiles de Audio DNA → tool `compare_playlists`).
  Mover HTML inline a `ui/` solo se hace si es barato: la UI no se pule más allá
  de lo que piden las tareas.
- **El criterio de ~500 líneas por página** no aplica a My Clusters ni a
  Cluster Results.
- **Las tools no leen la sesión.** Lo que va a `core/` recibe DataFrames y
  parámetros explícitos. `app_state/` es solo el wrapper que lee
  `st.session_state` y llama a `core/` (como `yc_tracks_frame`). El grafo del
  agente puede correr fuera del hilo del script de Streamlit.
- **Regla para el futuro paquete `agent/` (F1):** `agent/ → core, db, config`.
  Nunca `app_state` ni `ui`. Los datos de la sesión (colección YC) se le pasan
  explícitos.

## Eliminación del modo Demo Collection (FC), decidida el 2026-10-11

Facu confirmó en esta sesión que se elimina el modo FC ("🎵 Demo Collection",
que en local muestra sus 14 playlists del MySQL local) sin exportar esos datos.
Es la **única excepción explícita** a "no perder funcionalidad":
- La app queda con un solo modo, la colección del usuario (hoy "YC"), cargada por
  URL o, en `DEV_MODE=1`, desde `data/dev_collection.json`.
- Desaparecen: el selector de modo, `MODE_FC`, el deep-link `?mode=demo`, las
  ramas FC de páginas y `app_state`, el botón "Refresh track library" (solo
  recargaba FC desde la DB) y los loaders del star schema que quedan sin uso.
- **Se queda MySQL para lo que usa YC** (sesiones `uc_sessions`, progreso de
  clusters, analytics). Simplificar eso es otra decisión, aparte.
- `pipeline/` (el ETL que llenaba FC) queda sin uso. Se decide en T28, con
  aprobación.
- Desde acá, los checkpoints comparan solo YC (`dev_collection.json`) contra la
  línea base, y los tests o fixtures de FC se borran o se migran a YC.
- `agent/` recibe la colección como DataFrame (`core/tracks.yc_tracks_frame`).
  No necesita `db` para cargarla.

## Contexto operativo

El proyecto **no está en línea**: todos los recursos cloud (Railway, MySQL
de producción) están dados de baja. Consecuencias:
- No hay usuarios ni producción que proteger durante la refactorización. El
  criterio "no perder funcionalidad" se refiere al código y su comportamiento,
  verificado local.
- La ruta `DEV_MODE=0` (DB de producción, persistencia YC, analytics) no se
  puede probar contra infraestructura real; se cubre con tests y mocks.
- `monitoring.py`, `Procfile` y el deploy quedan fuera de alcance.
