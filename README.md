# brasil_em_dados — continental-scale geospatial panel for Brazilian public data

An interactive panel that serves **244 public indicators** for Brazil — from state level down
to **census tract** — as vector tiles generated directly from PostGIS.

Built to answer one question well: *what does this indicator look like across the whole
country, at the finest public resolution available, without waiting for a page to load?*

---

## What it does

- **Four geographic levels**: states (`geo.ufs`), municipalities (`geo.municipios`),
  census tracts (`geo.setores_censitarios`) and subdivided tracts.
- **244 indicators** across health, education, demography, housing, economy, public finance
  and vehicle fleet — see `frontend/src/utils/metricas.js`.
- **Cross-filtering** between map, legend and detail panel.
- **Export** of the current view.
- Tiles are generated **on demand from PostGIS functions**, not pre-baked — changing the
  metric or the year re-renders without a rebuild.

## Data sources

All public, all Brazilian federal:

| source | what |
|---|---|
| **IBGE** | census (basic, housing, equipment), territorial meshes, census tracts, PPM, indicators |
| **DataSUS** | CNES, SIH, SIM, SINAN, SINASC |
| **INEP** | school census, IDEB, educational indicators |
| **Tesouro Nacional / SICONFI** | fiscal management reports (RGF) |
| **SENATRAN** | vehicle fleet |
| **CNEFE** | national address registry |

18 loaders in `pipeline/`.

## Stack

```
PostGIS ──► pgBouncer ──► Martin (vector tiles, Rust) ──► nginx ──► React + deck.gl + MapLibre
    ▲                                                  │
    └── Dagster (orchestration)                   metadata API
                        Prometheus + Grafana (observability)
```

Frontend: **deck.gl 9.3**, **MapLibre GL 4.3**, **PMTiles 3.2**, Apache Arrow 15 + GeoArrow.

## Running it

Requires Docker and Docker Compose.

```bash
git clone <this repo> && cd brasil_em_dados
docker compose up -d
# panel at http://localhost       · Dagster at :3001 · Grafana at :3002
```

The database starts empty. Load data with the scripts in `pipeline/`, then refresh the
materialized views:

```bash
docker exec brasil_postgis psql -U brasil -d brasil_dados -c "
  REFRESH MATERIALIZED VIEW CONCURRENTLY api.indicadores_municipio;
  REFRESH MATERIALIZED VIEW CONCURRENTLY api.indicadores_uf;"
```

More commands in [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## Known limits — stated on purpose

This is an **independent build**, not a maintained product. What it does not have:

- **No automated tests.** Dagster orchestrates the pipeline but there is no test suite.
- **Data does not refresh by itself.** Dagster is wired in but no schedule is defined —
  loaders are run manually.
- **The metadata API is stdlib `http.server`** (`api/server.py`, 438 lines), not FastAPI.
  It works; it has no OpenAPI schema, no request validation and no auth.
- **No hosted demo yet.** Evaluating it currently means bringing up 14 containers locally.
  A static PMTiles build is the planned fix — the client library is already a dependency.
- Coverage and freshness follow the upstream sources, which vary by dataset and by year.

## License

MIT — see [LICENSE](LICENSE).
