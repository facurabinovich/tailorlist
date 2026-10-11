# Pivot: TailorList como agente LLM

Estado: **aprobado F1–F4, sin empezar** (2026-10-11) · Arranca cuando termine el refactor de `refactor/architecture` ([`SPEC.md`](../SPEC.md)), que es la F0.

> **Alcance aprobado:** F1 a F4, **en Streamlit**, con **Foundry Local** (SDK 2.x) como LLM y **sin multi-fuente**.
> **No aprobado** (queda documentado como idea, no se planifica sin pedido explícito): F5 (cambio de stack), la parte de negocio (producto pago, créditos, OpenRouter, licencias, landing) y multi-fuente. Las secciones correspondientes están marcadas como *no aprobado*.

Mockups y propuestas: [`agent-pivot-mockups.html`](agent-pivot-mockups.html) (abrir en el navegador) · copia online: https://claude.ai/artifact/NTqgYTdzDKVDanpjnf3L3z

El mockup tiene tres propuestas (A: analista, B: curador, C: agente al centro con dashboards como vistas; **elegida C**) y tres pantallas:

1. **Pedir una playlist:** "45 minutos para correr". Muestra los pasos del agente, la curva de energía y la propuesta con los botones exportar / ver en Audio DNA / guardar.
2. **Aprobación humana:** los 39 temas sin familia de género, con familia propuesta, confianza y aprobar los seguros / revisar los dudosos.
3. **Dashboard + agente:** Audio DNA con el panel lateral del agente, que resalta partes del gráfico.

Los temas y números del mockup son ejemplos ilustrativos.

## Las decisiones

- **El agente es la estrella.** Los dashboards se quedan como "Vistas" en la barra lateral, iguales que hoy, y cada uno suma un panel para preguntarle al agente sobre lo que estás viendo.
- **Se va el flujo de armado de playlists** (My Clusters, Cluster Results, asignación manual, progreso, reset). Lo hace el agente llamando a tools. Queda una vista chica de "Mis playlists" con lo que el agente armó (lista, tabla de temas, exportar).
- *(No aprobado)* **Streamlit se reemplaza a futuro, no ahora.** Se queda mientras sea para uso propio y se cambia cuando pase a producto pago (ver la sección [Streamlit](#streamlit-se-reemplaza-a-futuro)).
- *(No aprobado)* **Producto local de escritorio, pago único, sin API de Spotify** (ver [Negocio](#negocio) y [Datos](#datos-cero-api-de-spotify-en-la-app-distribuida)).

## Arquitectura

- **LangGraph solo para armar playlists:** estado tipado (filtros, candidatos, propuesta), idas y vueltas ("sacá el rap"), aprobación humana antes de exportar (`interrupt`) y sesiones que se retoman otro día (checkpointer). Para preguntas sobre los datos alcanza un loop simple de tools. Nada de varios agentes con supervisor.
- **El refactor es la base.** Las funciones de `core/` se convierten en tools. Tienen que quedar con firmas tipadas, docstrings claras y devolver algo serializable.
- **El grafo hace los pasos (cargar, filtrar, ordenar, proponer, pausar) y el LLM solo interpreta el pedido** y redacta la respuesta. Así funciona con modelos locales chicos.
- **Impacto en el refactor (ya aplicado en `SPEC.md`/`todo.md`):** se cancelan T26 y T27 (render de My Clusters y Cluster Results); el flujo de clusters sigue funcionando igual hasta que el agente lo reemplace. T10 ya se hizo en versión reducida (solo helpers idénticos). T15–T18 siguen valiendo: son la lógica que van a usar las tools.
- **Capa `agent/`:** depende de `core/` y `db/` con parámetros explícitos (modo, datos YC), nunca de `app_state/` ni `ui/`. La página le pasa al grafo los datos de la sesión; las tools no leen `st.session_state` (el grafo puede correr fuera del hilo del script de Streamlit).

### Grafo

```
usuario → router ─┬─ pregunta  → analista (loop de tools) → respuesta + gráfico / open_view
                  └─ curaduría → plan → load_collection → filter/group/cluster
                                 → sequence_by_curve → propuesta → interrupt (revisión humana)
                                     ├─ cambiar → plan
                                     └─ aprobar → export (CSV Spotlistr) → checkpointer
```

### Tools (desde `core/`)

| Tool | Sale de | Efecto externo |
|---|---|---|
| `load_collection` | `db/tracks.py` (Demo) o `core/tracks.yc_tracks_frame` (YC, con los datos que pasa la página). Devuelve un resumen, no el DataFrame | No |
| `filter_tracks` | `core/tracks.py`, `core/genres.py` | No |
| `group_by_family` | `core/grouping.py` | No |
| `cluster_kmeans` | `core/clustering.py` | No |
| `compare_playlists` | Comparación, Audio DNA (duplicados exactos y versiones, perfiles) | No |
| `sequence_by_curve` | nueva (curva de energía/tempo, ajuste a duración) | No |
| `open_view` | la devuelve el grafo como acción; la página la ejecuta con `ui/nav.py` | No |
| `export_playlist` | formato "Artista - Tema" para Spotlistr, extraído de `ui/export.py` a `core/` | **Sí, siempre detrás de `interrupt`** |

## Fases

1. **F0:** terminar el refactor, con la regla de firmas tipadas y retornos serializables en `core/`.
2. **F1:** `agent/tools.py` + 20 a 30 pedidos de prueba (evals) sobre la colección demo. Sin UI.
3. **F2:** analista. Panel lateral en Audio DNA y Comparación.
4. **F3:** curador en LangGraph. Primer caso: los temas sin familia de género.
5. **F4:** home conversacional; los dashboards se abren desde el agente.

F1 a F4 en **Streamlit, para uso propio**, con **Foundry Local** como LLM. Las fases siguientes **no están aprobadas**.

6. **F5:** si los evals con el modelo local dan bien, reemplazar Streamlit (ver la sección siguiente).

## Streamlit se reemplaza a futuro

> *No aprobado.* F1–F4 son en Streamlit.


**Decisión:** Streamlit se queda para F1 a F4 (uso propio). Se reemplaza por **FastAPI + React + Tauri** cuando el proyecto pase a producto pago, antes del video y la landing.

**Por qué no da para el producto pago:**
- **Recarga la página entera en cada click.** El agente necesita respuesta en vivo, botones de aprobación a mitad del grafo (`interrupt`) y seguir corriendo mientras el usuario mira otra vista. En Streamlit eso se hace con hilos en segundo plano, `session_state` y fragments, y se rompe fácil: si navegás a otra página en medio de una corrida, la corrida muere.
- **Ya se le está peleando.** Hay unas 290 llamadas con `unsafe_allow_html`, CSS inyectado, una navegación propia y el hack de cookies desde iframes que rompió el `visitor_id` en agosto de 2026.
- **Un producto de USD 19.99 se juzga por el video.** Tiene que verse y responder como una app de verdad.
- **El escritorio con Streamlit es incómodo:** empaquetar un servidor web para mostrar una ventana (pywebview).

**Por qué no ahora:**
- Para uso propio alcanza, y F1 a F3 se validan más rápido sin montar otro stack.
- Lo que vale está en el agente, no en la UI. Si el agente no rinde con el modelo local, cambiar de frontend no salva nada.

**A qué:**
- **Backend:** FastAPI con LangGraph, `core/`, `db/` y `app_state/`, que no saben nada de Streamlit gracias al refactor. Lo único que se reescribe es `pages/` y `ui/`.
- **Frontend:** React. Los gráficos de Plotly se serializan a JSON y plotly.js los dibuja igual. El chat sale de assistant-ui o CopilotKit, que traen integración con LangGraph (respuesta en vivo, pasos de tools, aprobación humana).
- **Escritorio:** Tauri, con instaladores chicos y el backend de Python como proceso aparte. Electron sirve pero pesa más.
- **Alternativa solo Python:** NiceGUI (funciona por eventos y tiene modo ventana nativa). Ecosistema más chico.

**Migración:** empezar por el chat y portar los dashboards de a uno.

**Consecuencia para el refactor en curso:** no vale la pena pulir componentes visuales de Streamlit más allá de lo que piden las tareas. Lo que importa es que `core/` quede puro y bien testeado, porque sobrevive al cambio de UI.

## Datos: cero API de Spotify en la app distribuida

> *No aprobado* (aplica a una app distribuida). En F1–F4 las fuentes siguen como hoy: colección Demo (MySQL local) y Your Collection (Client Credentials).


- Desde febrero de 2026 la API de Spotify es hostil: 5 usuarios por app en modo desarrollo, el dueño tiene que tener Premium, y para salir de ahí piden unos 250.000 usuarios activos por mes.
- **Entrada:** CSV que el usuario exporta (Exportify, TuneMyMusic, Soundiiz), archivos locales (features con Essentia o librosa), Last.fm para géneros e historial.
- **Salida:** Spotlistr, que crea la playlist, como hoy.
- Cada fuente es un loader que normaliza al mismo DataFrame que usa `core/`.

### Multi-fuente: SoundCloud, YouTube Music, Apple Music, Deezer y otras

> *No aprobado.*


**Decisión:** TailorList no queda atado a Spotify. Se suma cualquier plataforma, pero **importando archivos, no integrando sus APIs**. Cada API directa es una dependencia que te pueden cerrar como hizo Spotify, y la mayoría no da audio features. YouTube Music ni siquiera tiene API oficial; SoundCloud y Apple Music piden aprobación o cuenta de desarrollador paga.

**Entrada:** el usuario exporta sus playlists a CSV con una herramienta de terceros y TailorList importa el CSV.

| Plataforma | Cómo entra |
|---|---|
| Spotify | Exportify, TuneMyMusic, Soundiiz |
| YouTube Music, SoundCloud, Apple Music, Deezer, Tidal, Amazon Music | TuneMyMusic o Soundiiz (export a CSV) |
| Archivos locales (mp3, flac) | Lectura directa de tags + features con Essentia o librosa |
| Last.fm | API abierta: géneros (tags) e historial de escucha, como complemento |

Confirmar qué plataformas soporta hoy cada herramienta de export antes de prometerlas en la landing.

**Salida:** Spotlistr solo crea playlists en Spotify. Para el resto, TailorList exporta un CSV que se importa con TuneMyMusic o Soundiiz en la plataforma destino. Esto además permite pasar playlists de una plataforma a otra.

**Trabajo técnico:**
- Un loader por formato de CSV (`sources/exportify.py`, `sources/tunemymusic.py`, `sources/soundiiz.py`, `sources/local_files.py`), todos normalizados al mismo DataFrame. Agregar uno nuevo debería llevar un par de horas.
- **Identidad de un tema entre fuentes:** el mismo tema puede llegar desde Spotify y desde YouTube Music. Se usa ISRC cuando viene en el CSV; si no, artista + título normalizados (sin "Remastered", "feat.", etc.). Extiende la detección de duplicados exactos vs versiones distintas que ya existe (hoy unificada en `track_id`).
- **Audio features por fuente:** archivos locales → Essentia/librosa; streaming → ReccoBeats si hay ID de Spotify o ISRC; si no hay nada, el tema entra igual con metadata (género, año, artista) y el agente avisa cuántos no tienen features.
- Columna `source` en el DataFrame, para que el agente pueda filtrar y comparar por plataforma ("¿qué tengo en SoundCloud que no esté en Spotify?").
- Hueco conocido: quien solo usa streaming no tiene audio local. Esas features salen de ReccoBeats o no salen, y el agente lo tiene que decir.

## Negocio

> *No aprobado.* Documentado como idea.


- **Producto:** app de escritorio. Descarga gratis con dashboards; **agente pago con licencia de USD 19.99, pago único**. Nada de suscripciones; a futuro, pago por versión mayor (v2).
- **Web vs local: gana local.** Con pago único, la web te deja costos que se repiten todos los meses (hosting más tokens) contra un solo ingreso.
  - **Local:** unos USD 200–400 por año fijos (Apple Developer USD 99 por año + certificado de firma para Windows) y casi cero por usuario.
  - **Web:** unos USD 240–480 por año fijos, más tokens por cada conversación, para siempre.
- **Demo web opcional:** solo con la colección demo, con tope de conversaciones y presupuesto mensual fijo para el LLM. Sirve para el link del video.
- **Tres caminos para el LLM:**
  1. **Modelo local gratis:** SDK 2.x de Foundry Local empaquetado (ver licencias abajo). Ollama queda como opción.
  2. **Créditos incluidos** de un modelo cloud: unas 150 curadurías, mostradas en conversaciones y no en dólares. Pasan por un proxy chico tuyo (por ejemplo, un Cloudflare Worker) con tope por licencia, sin recargas.
  3. **Su propia cuenta de OpenRouter** (login OAuth) cuando se acaban los créditos. Las recargas las paga el usuario directo a OpenRouter.
- **Cobro:** Lemon Squeezy o Paddle como merchant of record (Stripe no opera en Argentina). Comisión de ~5 % + USD 0,50. Con una venta de USD 19.99 y unos USD 4 de créditos incluidos te quedan unos USD 14.50.
- **Contra la piratería:**
  - License key firmada: activación online una vez y revalidación cada 30 días.
  - Nuitka para el módulo del agente.
  - Actualizaciones que piden licencia.
  - Open core: dashboards abiertos, agente cerrado.
  - EULA. Sin DRM agresivo.
- **Validación antes de empaquetar:** video y landing con la versión local que ya funciona, más preventa. Si no aparecen ni 50 interesados, no se empaqueta.

## Licencias de Foundry Local (revisado 2026-10-11)

**Se puede usar en la app paga, con condiciones.**

| Componente | Licencia | ¿Empaquetable? |
|---|---|---|
| SDK 2.x (`pip install foundry-local-sdk`, 2.1.0) + runtime nativo `libfoundry_local` incluido | MIT | ✅ Sí, incluyendo el aviso de copyright |
| ONNX Runtime / onnxruntime-genai | MIT | ✅ Sí |
| CLI de Foundry Local | Propietaria: prohíbe "combine it with any of your applications for others to use" | ❌ No |
| `foundry-local-core` 1.x | El wheel no declara licencia | ⚠️ Evitar |
| Modelos | Cada uno con su licencia | ⚠️ Usar Phi (MIT) o Qwen/Mistral con Apache 2.0. Descarga en el primer uso, no dentro del instalador |

## Pendientes antes de lanzar

> Solo aplica si se aprueba la parte de negocio, salvo la telemetría de Foundry Local, que conviene revisar ya en F1.


- Telemetría del SDK de Foundry Local: el binario tiene un módulo que registra uso y tokens, y no está documentado cómo se apaga. Medir con un monitor de red y mencionarlo en la política de privacidad.
- Licencia exacta del modelo elegido.
- Términos del proveedor cloud: cobrar por uso dentro de la app está permitido; revender acceso a la API, no.
- Si vende en serio: consulta con un abogado de software sobre el EULA y las licencias de terceros.

## Descartado

- **SaaS web para el usuario común de Spotify:** la plataforma te cierra la puerta y Spotify ya hace AI Playlist gratis.
- **Nicho de DJs** (Rekordbox XML + Essentia): bueno, pero demasiado competitivo.
- **Microsoft Foundry cloud como pieza central:** solo sirve si hay créditos gratis de Azure para financiar los créditos incluidos.

## Fuentes

- [Spotify: Update on Developer Access and Platform Security (feb 2026)](https://developer.spotify.com/blog/2026-02-06-update-on-developer-access-and-platform-security)
- [Spotify: February 2026 Web API Dev Mode Changes, Migration Guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide)
- [TechCrunch: Spotify changes developer mode API](https://techcrunch.com/2026/02/06/spotify-changes-developer-mode-api-to-require-premium-accounts-limits-test-users/embed/)
- [LICENSE de Foundry Local](https://raw.githubusercontent.com/microsoft/Foundry-Local/main/LICENSE)
- [foundry-local-sdk en PyPI](https://pypi.org/project/foundry-local-sdk/)
- [Foundry Local GA](https://devblogs.microsoft.com/foundry/foundry-local-ga/)
