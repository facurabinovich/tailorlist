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
- **H2:** el comentario de `6_My_Clusters.py:20-21` está desactualizado (Cluster
  Results no importa de My Clusters).
- **H3:** `_Enrich.py` importa funciones privadas de `pipeline/enrich.py` (fuera
  de alcance).
- **H4:** `load_dotenv` se llama en 5 módulos de la app, uno con
  `override=True`. El `.env` local pisa variables del entorno, y el
  resultado depende del orden de importación. Se resuelve en T5.
