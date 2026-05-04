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

# Frontend dev server (runs outside Docker — preferred for development)
cd frontend && npm install && npm run dev -- --host 0.0.0.0

# Check tile endpoint
curl -s -o /dev/null -w "HTTP %{http_code} | %{size_download}b\n" http://localhost:3000/tiles_municipios/7/47/72?metrica=taxa_mortalidade&ano=2023

# Check all metrics loaded and their row counts
docker exec brasil_postgis psql -U brasil -d brasil_dados -c "
  SELECT metrica, COUNT(DISTINCT ano) AS anos, COUNT(*) AS rows
  FROM api.metricas_municipio GROUP BY metrica ORDER BY metrica;"
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
- `seguranca.*` — `sinesp_ocorrencias` (crime data, currently empty)
- `economia.*` — `siconfi_municipios` (municipal finance)
- `censo.*` — `cnefe_enderecos` (111M address points, partitioned)
- `api.*` — materialized views (`indicadores_municipio`, `indicadores_uf`), tile functions, and `metricas_municipio` (EAV table)

All geometries are stored in **EPSG:4674** (SIRGAS 2000, Brazilian datum). Tile functions transform to EPSG:3857 via `ST_Transform(..., 3857)` immediately before passing to `ST_AsMVTGeom` — both arguments to `ST_AsMVTGeom` must be in the same SRID.

### Critical: municipality and UF code arithmetic

SIM/DataSUS uses **6-digit IBGE codes** (`CODMUNRES`), while `geo.municipios.cod_ibge_7` is **7 digits** (6 digits + check digit). Join with: `m.cod_ibge_7 / 10 = s.cod_municipio`.

The UF code embedded in a 6-digit SIM municipality code is the **first 2 digits**: `cod_uf = cod_municipio // 10000` (not `// 100000`). For example, `140010 // 10000 = 14` (Roraima).

### EAV metrics table (`api.metricas_municipio`)

The primary storage for the 75+ non-SIM metrics:

```sql
CREATE TABLE api.metricas_municipio (
    cod_municipio  INTEGER  NOT NULL,  -- 7-digit IBGE (same as geo.municipios.cod_ibge_7)
    metrica        TEXT     NOT NULL,
    ano            SMALLINT NOT NULL,
    valor          FLOAT8,
    PRIMARY KEY (cod_municipio, metrica, ano)
);
```

The tile functions (`04_tile_functions.sql`) have explicit `CASE WHEN v_metrica = '...' THEN` branches for metrics that require special joins (SIM mortality, PIB, Siconfi, CNES). **All other metrics fall through to a generic `ELSE` clause** that reads directly from `api.metricas_municipio`. This means adding a new metric loaded into this table requires **no SQL changes** — only adding it to the frontend dropdowns, `ANOS_POR_METRICA_DEFAULT` in `cross_filter.js`, `METRICAS_RANGES` in `main.jsx`, and `api/server.py`'s `FALLBACK` dict.

At the UF level, the ELSE clause computes `AVG(valor)` across municipalities in the UF.

### Tile functions (Martin auto-discovery)

Martin v1.7 auto-discovers functions in the `api` schema that match the signature:
```sql
function_name(z INT, x INT, y INT, query_params JSON DEFAULT '{}') RETURNS bytea
```
URL query params are forwarded as the `query_params` JSON argument. Functions must be declared `STABLE PARALLEL SAFE`.

Use `ST_TileEnvelope(z, x, y)` — not `ST_TileBBox` (doesn't exist in PostGIS 3.x).

**NUMERIC columns must be cast to `FLOAT8`** before `ST_AsMVT`. PostGIS encodes `NUMERIC`/`DECIMAL` as strings in MVT; `FLOAT8` encodes as a proper double. Without the cast, values arrive in the browser as strings (`"767.0"` instead of `767.0`), breaking choropleth color normalization silently.

### Martin tile cache behavior

Martin's tile cache is keyed on the **full URL including query parameters**. Switching filters always fetches fresh tiles (different URL). Stale tiles from before a SQL function change persist until Martin is restarted. Always `docker compose restart martin` after deploying changes to `04_tile_functions.sql`.

### Materialized views

`api.indicadores_municipio` and `api.indicadores_uf` are defined in `02_schema.sql` but start empty because the Dagster pipeline runs after PostgreSQL first starts. Always refresh after loading data. `CONCURRENTLY` requires the unique index (`idx_indicadores_municipio_pk`) to exist — created in the same file.

### Partitioned tables

`geo.setores_censitarios`, `geo.setores_subdivididos`, and `censo.cnefe_enderecos` are partitioned by `cod_uf`. Their primary keys **must include the partition column**: `PRIMARY KEY (gid, cod_uf)`. A simple `gid SERIAL PRIMARY KEY` will fail on creation.

### Cross-filtering architecture

**All demographic filters are server-side** — passed as query params to Martin → PostGIS, which aggregates `sim_mortalidade` records applying filters before computing rates.

Serialized in `getServerParams()` in `cross_filter.js`:
- Always: `ano`, `cod_uf`, `cid10_capitulo`, `metrica`
- For `METRICAS_SAUDE` only: `sexo`, `cor_raca`, `faixa_etaria_min/max` (only included when non-default)
- For GEOLOCALIZACAO level only: `especie` (CNEFE address type filter)

State is managed in a Zustand store (`frontend/src/filters/cross_filter.js`).

### Dynamic available years (`anosDisponiveis`)

The year dropdown is populated at runtime. On startup, `main.jsx` calls `useAnosDisponiveis()` which fetches `GET /api/anos` (Nginx → `api/server.py` → PostGIS). `ANOS_POR_METRICA_DEFAULT` in `cross_filter.js` serves as the fallback while the fetch is in flight. When new years are loaded via pipeline scripts, the frontend reflects them automatically on next page load — no code changes needed.

The `setAnosDisponiveis` action also auto-corrects the selected year if it's no longer valid for the new metric.

### Color scale ranges per indicator

`frontend/src/main.jsx` defines `METRICAS_RANGES` (per metric, per zoom level) and `CID10_RANGES` (per CID-10 chapter, for `taxa_mortalidade`). When `filtros.cid10_capitulo` is set, the `estatisticas` useEffect picks the chapter-specific range. Both objects must be updated when adding new metrics.

### Forced zoom level (`nivelForcado`)

`main.jsx` has a `nivelForcado` React state (`null` by default). When non-null it overrides the zoom-derived level without changing the viewport — lets the user lock to ESTADUAL while zoomed past zoom 8.

### Metadata API (`api/server.py`)

Minimal stdlib Python HTTP server (no framework). Runs as the `brasil_api` container (internal port 8001, no external port). Exposes `GET /anos` only. The Python server sets `Access-Control-Allow-Origin: *` — do **not** also set it in the nginx `location /api/` block or the browser will reject due to duplicate CORS headers.

`FALLBACK` dict in `server.py` must mirror `ANOS_POR_METRICA_DEFAULT` in `cross_filter.js` — both must be updated when adding a new metric.

---

## Pipeline scripts

All scripts run inside the `brasil_dagster_web` container. The standard deployment pattern:

```bash
docker cp pipeline/load_X.py brasil_dagster_web:/tmp/load_X.py
docker exec -d brasil_dagster_web bash -c "python -u /tmp/load_X.py [args] > /tmp/load_X.log 2>&1"
docker exec brasil_dagster_web tail -f /tmp/load_X.log
```

All scripts write to `api.metricas_municipio` via the same `upsert_metricas()` helper using `ON CONFLICT DO UPDATE`.

### Script inventory

| Script | Source | Key flags |
|---|---|---|
| `load_sim.py` | DataSUS FTP (PySUS) | `--anos`, `--ufs`, `--workers 1` |
| `load_economic_data.py` | IBGE SIDRA T5938 + Siconfi RREO | `--anos-pib`, `--anos-siconfi` |
| `load_metricas_ibge.py` | IBGE SIDRA (Censo 2022, RC, PAM, CEMPRE) | `--skip-*` flags per group |
| `load_censo_basico.py` | IBGE SIDRA Censo 2022 (demográficos) | — |
| `load_censo_habitacional.py` | IBGE SIDRA Censo 2022 (habitação) | — |
| `load_censo_equipamentos.py` | IBGE SIDRA Censo 2022 (bens duráveis) | — |
| `load_censo_escolar.py` | INEP (TRE/TDI ZIP→XLSX) | `--anos`, `--skip-rendimento`, `--skip-distorcao` |
| `load_ppm.py` | IBGE SIDRA T3939 + T74 | `--anos`, `--skip-bovino`, etc. |
| `load_sinan.py` | DataSUS FTP (PySUS SINAN) | `--anos`, `--doencas`, `--workers 1` |
| `load_sih.py` | DataSUS FTP (PySUS SIH) | `--anos`, `--ufs`, `--workers 1` |
| `load_senatran.py` | dados.transportes.gov.br CKAN | `--anos`, `--skip-onibus` |
| `load_populacao_demografica.py` | IBGE SIDRA T9605/T9514 | — |
| `load_sinasc.py` | DataSUS (nascidos vivos) | `--anos` |
| `load_cnes.py` | DataSUS CNES | — |
| `load_setores.py` | IBGE geoftp (setores censitários) | — |
| `load_cnefe.py` | IBGE CNEFE (111M endereços) | — |
| `load_ideb.py` | INEP IDEB | — |

### PySUS v1.x API (critical — signatures changed from v0.x)

```python
# SIM
from pysus.online_data import SIM
parquet_set = SIM.download("CID10", uf, ano, data_dir=tmpdir)
df = parquet_set.to_dataframe()

# SINAN — positional args: diseases, years; keyword: data_path (NOT data_dir)
from pysus.online_data import SINAN
parquet_set = SINAN.download(dis_code, ano, data_path=tmpdir)

# SIH — positional: states, years, months, groups; keyword: data_dir
from pysus.online_data import SIH
result = SIH.download(uf, ano, list(range(1, 13)), "RD", data_dir=tmpdir)
# SIH returns a list of ParquetSets when multiple months are passed:
if hasattr(result, "to_dataframe"):
    df = result.to_dataframe()
else:
    df = pd.concat([ps.to_dataframe() for ps in result if hasattr(ps, "to_dataframe")], ignore_index=True)
```

Before inserting into PostgreSQL, convert nullable pandas integer columns:
```python
for col in batch.select_dtypes(include=["Int8","Int16","Int32","Int64"]).columns:
    batch[col] = batch[col].astype(object).where(batch[col].notna(), None)
```

### DataSUS FTP rate limiting

Always use `--workers 1` for SIM, SIH, and SINAN scripts. Running ≥2 parallel downloads triggers `Connection refused` / `Connection reset by peer`. For SIH, use a `tempfile.TemporaryDirectory()` per UF+year call and delete it immediately after conversion to DataFrame (12 months × 27 UFs × 5 years = large disk footprint if left open).

### PPM (Pesquisa Pecuária Municipal) — T3939

T3939 only has variable V105 ("Efetivo dos rebanhos"). Animal type is selected via classification parameter `79[cat_id]`, not separate variables:

```python
# SIDRA URL format: /periodos/{ano}/variaveis/{variavel}?localidades=N6[all]&classificacao=79[{cat_id}]
REBANHO_CATS = {
    "bovino": 2670, "equino": 2672, "suino": 32794,
    "ovino": 2677, "caprino": 2681, "galinaceos": 32796,
}
```

T74 (leite/mel/ovos production) is intermittently returning HTTP 500 from SIDRA — this is a known upstream issue.

### INEP Censo Escolar — correct URL pattern

Files are ZIP archives (not XLSX directly). The URL changed — the old pattern (`TRE_municipios_{ano}.xlsx`) returns 404 for all years:

```
TRE: https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/{ano}/tx_rend_municipios_{ano}.zip
TDI: https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/{ano}/TDI_{ano}_MUNICIPIOS.zip
```

TRE is available from 2019 onwards; TDI from 2016 onwards.

The XLSX inside has a dual-header structure. For 2020+, row 8 (0-indexed) contains machine column names (`NU_ANO_CENSO`, `CO_MUNICIPIO`, `1_CAT_FUN` for EF approval total, etc.). For 2019 TRE, row 8 is all-NaN — use positional columns instead (col 3 = municipality code, col 7 = EF approval total, col 19 = EM approval total, col 25 = EF reprovação, col 43 = EF abandono, col 55 = EM abandono). The `load_censo_escolar.py` script detects the format automatically.

Filter for `NO_CATEGORIA == 'Total'` and `NO_DEPENDENCIA == 'Total'` to get the all-schools municipal aggregate (yields exactly 5,570 rows per year).

### SENATRAN — mixed CSV formats

SENATRAN CSVs vary by year:
- **Tall format** (2020, 2022): columns `UF, MUNICIPIO, TIPO DE VEICULO, QUANTIDADE` — one row per vehicle type per municipality
- **Wide format** (2021): columns `UF, MUNICIPIO, AUTOMOVEL, BONDE, CAMINHAO, ...` — one row per municipality, one column per type

`load_senatran.py` detects the format via `_is_wide_format()` (checks for `AUTOMOVEL` column + absence of `TIPO` column). Known working years: 2020–2022. Resource URLs for those years are hardcoded in `RESOURCE_URLS_FALLBACK`; other years are discovered via the CKAN API at `dados.transportes.gov.br`.

---

## External API quirks

### IBGE SIDRA v3

- Use `N6[all]` to fetch all 5,570 municipalities in one call — never use pipe `|` as separator (causes HTTP 500)
- URL format: `/api/v3/agregados/{tabela}/periodos/{ano}/variaveis/{variavel}?localidades=N6[all]`
  - Note: `periodos` must be a path segment, not a query param; the query-param form returns HTTP 500
- Age table (9514): `N6[all]` + multiple classification 287 categories returns HTTP 500 — must fetch one category at a time
- `area_km2` from PostgreSQL returns `decimal.Decimal`; cast to `float()` before arithmetic

### Siconfi RREO API

- All server-side filter params (`no_conta`, `co_conta`, `no_coluna`) are **ignored** — response always returns all ~4034 rows. Filter locally.
- Only ~3314/5570 municipalities report to Siconfi. Missing data is expected.
- `limit=5000` covers all rows without pagination.

Filter combinations:

| Field | `cod_conta` | `coluna` |
|---|---|---|
| `receita_total` | `"ReceitasExcetoIntraOrcamentarias"` | `"Até o Bimestre (c)"` |
| `despesa_saude` | `"AplicacaoTotalDasDespesasComAcoesEServicosPublicosDeSaude"` | `"Valor Apurado Até o Bimestre"` |
| `despesa_educacao` | `"MinimoAnualDasReceitasDeImpostosNaManutencaoEDesenvolvimentoDoEnsinoDemonstrativoSimplificado"` | `"Valor Apurado Até o Bimestre"` |

---

## SIM/DataSUS specifics

### Sexo encoding

`saude.sim_mortalidade.sexo` stores DataSUS numeric strings: `'1'` = Masculino, `'2'` = Feminino. The tile functions map frontend `'M'`/`'F'` to these values:
```sql
AND (v_sexo IS NULL OR (v_sexo = 'M' AND s.sexo = '1') OR (v_sexo = 'F' AND s.sexo = '2'))
```

Known pysus bug: some years deliver DBC with character-format sex codes. Verify after loading: `SELECT sexo, COUNT(*) FROM saude.sim_mortalidade WHERE ano=2023 GROUP BY sexo` — should show only `'1'`, `'2'`, `NULL`.

### Homicídio methodology

Derived from SIM using CID-10 X85–Y09 (external causes — assaults), same as Atlas da Violência (IPEA/FBSP). `seguranca.sinesp_ocorrencias` is empty (SINESP not yet ingested).

### Demographic denominators

`censo.populacao_raca_municipio` and `censo.populacao_faixa_municipio` store Censo 2022 subgroup populations (loaded from SIDRA T9605/T9514 by `load_populacao_demografica.py`). Tile functions use these as denominators when demographic filters are active. With both race + age filters: `pop_race × pop_age_bands / pop_total` (independence approximation).

Municipality code alignment: `sim_mortalidade.cod_municipio` = 6-digit; `populacao_raca_municipio.cod_municipio` = 7-digit. Join via `ma.cod_municipio = m.cod_ibge_7 / 10`.

---

## Adding a new metric

1. **Load data** into `api.metricas_municipio` using `upsert_metricas()` — `cod_municipio` must be 7-digit IBGE
2. **Refresh views**: `REFRESH MATERIALIZED VIEW CONCURRENTLY api.indicadores_municipio; REFRESH MATERIALIZED VIEW CONCURRENTLY api.indicadores_uf;`
3. **Frontend dropdown**: add `{ value: "...", label: "..." }` to the appropriate group in `frontend/src/components/PainelControles.jsx`
4. **Fallback years**: add entry to `ANOS_POR_METRICA_DEFAULT` in `frontend/src/filters/cross_filter.js`
5. **Color ranges**: add entry to `METRICAS_RANGES` in `frontend/src/main.jsx`
6. **API fallback**: add entry to `FALLBACK` dict in `api/server.py`

No SQL changes needed unless the metric requires a custom join (SIM records, CNES, etc.) — those need a new `CASE WHEN` branch in `database/init/04_tile_functions.sql`.

## Martin config

Martin connects directly to PostGIS (`postgis:5432`), not through PgBouncer. PgBouncer is in transaction pooling mode which is incompatible with Martin's connection pool prepared statements.

Martin auto-publishes all tables from schemas `geo`, `api`, `censo` and all functions from schema `api`. PMTiles files in `tileserver/pmtiles/` are served as a fallback.
