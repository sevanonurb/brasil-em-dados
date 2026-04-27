# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Painel Geoespacial Iterativo do Brasil — a continental-scale geospatial data visualization panel. The stack serves PostGIS vector tiles through Martin (Rust) to a MapLibre GL JS + Deck.gl frontend, with Dagster orchestrating ETL from IBGE and DataSUS sources.

## Service ports

| Service | Port | URL |
|---|---|---|
| Nginx (proxy) | 80 | http://localhost:80 |
| Martin (tile server) | 3000 | http://localhost:3000 (direct, dev only) |
| Dagster UI | 3001 | http://localhost:3001 |
| Grafana | 3002 | http://localhost:3002 |
| Frontend (Vite) | 5173 | http://localhost:5173 |
| PostGIS | 5432 | direct psql |
| PgBouncer | 6432 | connection pool |
| Redis | 6380 | (host port; container is 6379) |
| Prometheus | 9090 | http://localhost:9090 |

Nginx at port 80 routes: `/api/` → metadata API (`brasil_api` container, internal port 8001); `/` → Martin tile server with 5-minute tile cache.

## Common commands

```bash
# Start full stack
docker compose up -d

# Start individual service
docker compose up -d postgis martin

# Restart a service (e.g. after config change)
docker compose restart martin

# View logs
docker compose logs -f martin

# Run SQL directly
docker exec brasil_postgis psql -U brasil -d brasil_dados -c "SELECT COUNT(*) FROM geo.municipios;"

# Apply/reload tile functions after editing 04_tile_functions.sql
# IMPORTANT: also restart Martin after function changes to clear its tile cache
docker exec -i brasil_postgis psql -U brasil -d brasil_dados < database/init/04_tile_functions.sql
docker compose restart martin

# Refresh materialized views (required after any data ingestion)
docker exec brasil_postgis psql -U brasil -d brasil_dados -c "
  REFRESH MATERIALIZED VIEW CONCURRENTLY api.indicadores_municipio;
  REFRESH MATERIALIZED VIEW CONCURRENTLY api.indicadores_uf;
"

# Run ingestion script directly in Dagster container
docker cp /tmp/script.py brasil_dagster_web:/tmp/script.py
docker exec brasil_dagster_web python /tmp/script.py

# Load SIM/DataSUS mortality data (use --workers 1 — DataSUS FTP rate-limits parallel connections)
docker cp pipeline/load_sim.py brasil_dagster_web:/tmp/load_sim.py
docker exec -d brasil_dagster_web bash -c "python -u /tmp/load_sim.py --anos 2015 2016 2017 2018 2019 2020 2021 2022 2023 --workers 1 > /tmp/load_sim.log 2>&1"
docker exec brasil_dagster_web tail -f /tmp/load_sim.log  # monitor progress

# Load economic data (PIB from IBGE SIDRA + receita from Siconfi RREO)
docker cp pipeline/load_economic_data.py brasil_dagster_web:/tmp/load_economic_data.py
docker exec -d brasil_dagster_web bash -c "python -u /tmp/load_economic_data.py --anos-pib 2015 2016 2017 2018 2019 2020 2021 2022 2023 --anos-siconfi 2015 2016 2017 2018 2019 2020 2021 2022 2023 > /tmp/load_economic.log 2>&1"
docker exec brasil_dagster_web tail -f /tmp/load_economic.log

# Check what years are loaded per metric
docker exec brasil_postgis psql -U brasil -d brasil_dados -c "
  SELECT 'sim' as fonte, ano, COUNT(*) FROM saude.sim_mortalidade GROUP BY ano
  UNION ALL
  SELECT 'siconfi', ano, COUNT(*) FROM economia.siconfi_municipios GROUP BY ano
  ORDER BY 1, 2;"

# Frontend dev server (runs outside Docker — preferred for development)
cd frontend && npm install && npm run dev -- --host 0.0.0.0

# Check all tile endpoints
curl -s -o /dev/null -w "HTTP %{http_code} | %{size_download}b\n" http://localhost:3000/tiles_ufs/3/3/4
curl -s -o /dev/null -w "HTTP %{http_code} | %{size_download}b\n" http://localhost:3000/tiles_municipios/7/47/72
```

## Frontend environment setup (critical)

Vite reads `.env` from the directory containing `vite.config.js` — which is `frontend/`, not the project root. The root `.env` is only used by Docker Compose. **Always maintain `frontend/.env`** separately:

```bash
# frontend/.env (required for the dev server to find Martin)
VITE_MARTIN_URL=http://localhost:3000
VITE_API_URL=http://localhost:80
```

Without this file, `import.meta.env.VITE_MARTIN_URL` is `undefined` at runtime and every tile URL becomes the literal string `"undefined/tiles_ufs/{z}/{x}/{y}"` — the map renders blank with no network error. The Docker Compose `frontend` service injects these as environment variables directly (bypassing the file), so this only affects local dev outside Docker.

Full setup sequence:
```bash
cp .env.example .env
# Edit .env — set POSTGRES_PASSWORD and GRAFANA_PASSWORD
cp .env frontend/.env
docker compose up -d
```

## node_modules patches (postinstall)

`frontend/patches/apply-patches.sh` patches two packages after `npm install`:

- **`@loaders.gl/mvt/dist/mvt-worker.js`** — the bundled Pbf library throws `"Unimplemented type: 4"` on protobuf wire type 4 (End Group, deprecated proto2). Martin/PostGIS MVT tiles trigger this path.
- **`node_modules/pbf/index.js`** — same fix for the main-thread pbf.

The fix silently skips wire types 3/4. It runs automatically via `"postinstall": "bash patches/apply-patches.sh"` in `package.json`. If tiles fail to render with `Worker exception: Error: Unimplemented type: 4` in the console, re-run `npm install` to re-apply.

## Architecture

### Request flow

```
Browser → Martin (Rust, port 3000) — direct via CORS (dev)
                    ↓
               PostGIS (port 5432)
                    ↓
          api.tiles_* SQL functions
          → ST_AsMVT → bytea → browser
```

The frontend uses **two simultaneous render surfaces**:
1. **MapLibre `Map`** object in a container div — renders the basemap (OSM raster at zoom ≥ 9)
2. **Deck.gl `Deck`** instance on a separate canvas — renders analytical vector layers

These are synced via `map.jumpTo()` on every `onViewStateChange` event from Deck.gl. MapLibre is set `interactive: false`; Deck.gl controls all interaction.

### Semantic zoom levels

The map shows completely different data sources at each zoom level — not just visual simplification:

| Level | Zoom | Data source | Tile function |
|---|---|---|---|
| NACIONAL | 0–4 | 27 UFs | `api.tiles_ufs` |
| ESTADUAL | 5–8 | 5,570 municípios | `api.tiles_municipios` |
| MUNICIPAL | 9–12 | ~215k setores censitários | `api.tiles_setores` |
| GEOLOCALIZACAO | 13+ | CNEFE address points | `api.tiles_cnefe` |

Layers are conditionally included/excluded from the Deck.gl layers array (not `visible: false`, which still fetches tiles).

### Database schemas

- `geo.*` — spatial dimensions: `ufs`, `municipios`, `setores_censitarios`, `setores_subdivididos` (partitioned by `cod_uf`)
- `saude.*` — `sim_mortalidade` (SIM/DataSUS death records)
- `seguranca.*` — `sinesp_ocorrencias` (crime data)
- `economia.*` — `siconfi_municipios` (municipal finance)
- `censo.*` — `cnefe_enderecos` (111M address points, partitioned)
- `api.*` — materialized views (`indicadores_municipio`, `indicadores_uf`) and tile functions

All geometries are stored in **EPSG:4674** (SIRGAS 2000, Brazilian datum). Tile functions transform to EPSG:3857 via `ST_Transform(..., 3857)` immediately before passing to `ST_AsMVTGeom` — both arguments to `ST_AsMVTGeom` must be in the same SRID.

### Critical: municipality and UF code arithmetic

SIM/DataSUS uses **6-digit IBGE codes** (`CODMUNRES`), while `geo.municipios.cod_ibge_7` is **7 digits** (6 digits + check digit). Join with: `m.cod_ibge_7 / 10 = s.cod_municipio`.

The UF code embedded in a 6-digit SIM municipality code is the **first 2 digits**: `cod_uf = cod_municipio // 10000` (not `// 100000`). For example, `140010 // 10000 = 14` (Roraima). Using `// 100000` gives `1`, which is wrong.

### Tile functions (Martin auto-discovery)

Martin v1.7 auto-discovers functions in the `api` schema that match the signature:
```sql
function_name(z INT, x INT, y INT, query_params JSON DEFAULT '{}') RETURNS bytea
```
URL query params are forwarded as the `query_params` JSON argument. Functions must be declared `STABLE PARALLEL SAFE`.

Use `ST_TileEnvelope(z, x, y)` — not `ST_TileBBox` (doesn't exist in PostGIS 3.x).

**NUMERIC columns must be cast to `FLOAT8`** before `ST_AsMVT`. PostGIS encodes `NUMERIC`/`DECIMAL` as strings in MVT; `FLOAT8` encodes as a proper double. Without the cast, values arrive in the browser as strings (`"767.0"` instead of `767.0`), breaking choropleth color normalization silently.

### Materialized views

`api.indicadores_municipio` and `api.indicadores_uf` are defined in `02_schema.sql` but start empty because the Dagster pipeline runs after PostgreSQL first starts. Always refresh after loading data. `CONCURRENTLY` requires the unique index (`idx_indicadores_municipio_pk`) to exist — created in the same file.

### Partitioned tables

`geo.setores_censitarios`, `geo.setores_subdivididos`, and `censo.cnefe_enderecos` are partitioned by `cod_uf`. Their primary keys **must include the partition column**: `PRIMARY KEY (gid, cod_uf)`. A simple `gid SERIAL PRIMARY KEY` will fail on creation.

### PySUS ingestion (v1.x API)

```python
from pysus.online_data import SIM
import tempfile

with tempfile.TemporaryDirectory() as tmpdir:
    parquet_set = SIM.download("CID10", "SP", 2023, data_dir=tmpdir)
    df = parquet_set.to_dataframe()
```

Before inserting into PostgreSQL, convert nullable pandas integer columns to object dtype (psycopg2 cannot adapt `numpy.int64`):
```python
for col in batch.select_dtypes(include=["Int8","Int16","Int32","Int64"]).columns:
    batch[col] = batch[col].astype(object).where(batch[col].notna(), None)
```

### Cross-filtering architecture

Filters are split into two layers:
- **Server-side** (`ano`, `cod_uf`, `cid10_capitulo`, `metrica`): change triggers new tile requests. Serialized as URL query params to Martin.
- **GPU-side** (`faixa_etaria`, `cor_raca`, `valor_min/max`): applied by `DataFilterExtension` in WebGL shaders at 60fps with no new network request.

State is managed in a Zustand store (`frontend/src/filters/cross_filter.js`).

### Dynamic available years (`anosDisponiveis`)

The year dropdown is populated at runtime, not hardcoded. On startup, `main.jsx` calls `useAnosDisponiveis()` which fetches `GET /api/anos` (through Nginx → `api/server.py` → PostGIS `DISTINCT ano` queries). The store has a `setAnosDisponiveis` action that also auto-corrects the selected year if it's no longer valid for the new metric. `ANOS_POR_METRICA_DEFAULT` in `cross_filter.js` serves as the fallback while the fetch is in flight. When new years are loaded via the pipeline scripts, the frontend reflects them automatically on next page load — no code changes needed.

### Forced zoom level (`nivelForcado`)

`main.jsx` has a `nivelForcado` React state (`null` by default). When non-null it overrides the zoom-derived level:
```js
const nivelAtual = nivelForcado ?? getNivelSemantico(viewState.zoom);
```
Setting `nivelForcado` does **not** change the Deck.gl viewport — it only controls which data layer is active. This lets the user lock to, e.g., ESTADUAL while zoomed in past zoom 8.

### Color scale ranges per indicator and CID-10 chapter

`frontend/src/main.jsx` defines `METRICAS_RANGES` (per metric, per zoom level) and `CID10_RANGES` (per CID-10 chapter, for `taxa_mortalidade`). When `filtros.cid10_capitulo` is set, the `estatisticas` useEffect picks the chapter-specific range instead of the all-cause range. All-cause mortality (300–1000/100k) is very different from disease-specific rates (cancer ~0–200, cardiovascular ~0–400), so per-chapter ranges are essential for a usable choropleth.

### Martin tile cache behavior

Martin's tile cache is keyed on the **full URL including query parameters**. Switching CID-10 or year filters always fetches fresh tiles (different URL). However, stale tiles from before a SQL function change will persist in the cache until Martin is restarted. Always `docker compose restart martin` after deploying changes to `04_tile_functions.sql` or any SQL function in the `api` schema.

### External API quirks (IBGE SIDRA + Siconfi)

**IBGE SIDRA v3** (PIB data — table 5938, variable 37, `N6[all]` for all municipalities):
- Use **comma** as separator for multiple IDs: `N6[1100015,3550308]`
- **Pipe separator** (`|`) causes HTTP 500. A single `N6[all]` fetches all 5570 municipalities in one call and avoids the separator entirely — prefer this.

**Siconfi RREO API** (receita municipal):
- Query parameters `no_conta`, `co_conta`, `no_coluna` are **completely ignored** by the server. The response always contains all ~4034 rows regardless of these params. Do not rely on server-side filtering.
- Filter locally after fetching: `cod_conta == "ReceitasExcetoIntraOrcamentarias"` AND `coluna == "Até o Bimestre (c)"`.
- Default `limit=5000` covers all rows without pagination needed.
- Only ~3314/5570 municipalities (59.5%) report to Siconfi — small municipalities legitimately do not file RREO. Missing `receita_total` for ~2256 municipalities is expected, not a bug.

### SIM/DataSUS FTP rate limiting

DataSUS serves `.dbc` files over FTP. Running more than 1–2 parallel downloads triggers `Connection refused` and `Connection reset by peer` errors. Always use `--workers 1` for `load_sim.py`. The default of 4 workers looks faster but silently fails most downloads. The `--limpar-ano <year>` flag does a DELETE before re-inserting (idempotent re-runs). Idempotency for individual UF+year combos is also ensured by DELETE-then-INSERT (not ON CONFLICT, since the serial PK never conflicts).

### Homicídio methodology (SIM/DataSUS, not SINESP)

`seguranca.sinesp_ocorrencias` is empty (SINESP data not yet ingested). Homicides in `api.indicadores_municipio` are derived from `saude.sim_mortalidade` using CID-10 codes X85–Y09 (external causes — assaults), the same methodology as the Atlas da Violência (IPEA/FBSP):
```sql
COUNT(s.id) FILTER (
    WHERE s.ano = 2023
      AND s.cid10_codigo >= 'X85'
      AND s.cid10_codigo < 'Y1'
)
```
This gives ~43,000 homicides for 2023, consistent with official IPEA figures.

### Demographic denominators for mortality rates

`censo.populacao_raca_municipio` and `censo.populacao_faixa_municipio` store Censo 2022 population breakdowns by racial group and age group per municipality (loaded by `pipeline/load_populacao_demografica.py` from IBGE SIDRA tables 9605 and 9514).

When a demographic filter is active, tile functions use the subgroup population as denominator — not the total population — to compute correct rates per 100k:
- **Race filter only**: denominator = population of that racial group in the municipality
- **Age filter only**: denominator = sum of population of selected age bands
- **Both filters**: proportional estimate = `pop_race × pop_age_bands / pop_total` (approximation under independence assumption)
- **No filter**: total population from `api.indicadores_municipio.populacao_2022`

SIDRA quirk for age table (9514): `N6[all]` + multiple categories in classification 287 returns HTTP 500. Must fetch one category at a time. The load script uses `ThreadPoolExecutor(max_workers=5)` for parallel single-category calls.

Municipality code alignment: `sim_mortalidade.cod_municipio` = **6-digit** IBGE; `populacao_raca_municipio.cod_municipio` = **7-digit** IBGE (from SIDRA N6). In the tile functions, `pop_raca` joins on `pr.cod_municipio = m.cod_ibge_7` (7-digit). The `mortalidade_agg` CTE groups by `s.cod_municipio` (6-digit) and joins via `ma.cod_municipio = m.cod_ibge_7 / 10`.

### Martin config (tileserver/martin_config.yaml)

Martin connects directly to PostGIS (`postgis:5432`), not through PgBouncer. PgBouncer is in transaction pooling mode which is incompatible with prepared statements used by Martin's connection pool.

Martin auto-publishes all tables from schemas `geo`, `api`, `censo` and all functions from schema `api`. PMTiles files in `tileserver/pmtiles/` are served as a fallback.

### Metadata API (`api/server.py`)

Minimal stdlib Python HTTP server (no framework). Runs as the `brasil_api` container (internal port 8001, no external port). Exposes `GET /anos` only. Nginx proxies `localhost:80/api/anos` → `brasil_api:8001/anos`. The Python server sets `Access-Control-Allow-Origin: *` — do **not** also set it in the nginx `location /api/` block or the browser will reject the response due to duplicate CORS headers.
