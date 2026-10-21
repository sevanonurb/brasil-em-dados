#!/usr/bin/env bash
# Rebuilds the static demo (published to GitHub Pages from the gh-pages branch).
# Needs only the postgis service up:  docker compose up -d postgis
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
PG="PG:host=127.0.0.1 port=5432 dbname=$POSTGRES_DB user=$POSTGRES_USER password=$POSTGRES_PASSWORD"
mkdir -p demo/web

# 1. catalogue: the API's own list of indicators and years
python3 - <<'PY'
import json, importlib.util
s = importlib.util.spec_from_file_location("server", "api/server.py"); m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
json.dump(m.query_anos(), open("demo/anos.json", "w"), default=int)
json.dump(m._query_municipios_db(), open("demo/web/municipios.json", "w"), ensure_ascii=False, separators=(",", ":"))
PY
cp demo/anos.json demo/web/anos.json

# 2. geometry, once (values are NOT in here)
ogr2ogr -overwrite -f PMTiles demo/web/ufs.pmtiles "$PG" -sql "select cod_uf, sigla, nome, regiao, populacao_2022, geom from geo.ufs" -nln ufs -dsco MINZOOM=0 -dsco MAXZOOM=7
ogr2ogr -overwrite -f PMTiles demo/web/municipios.pmtiles "$PG" -sql "select cod_ibge_7, cod_uf, nome as nome_municipio, capital, populacao_2022, geom from geo.municipios" -nln municipios -dsco MINZOOM=3 -dsco MAXZOOM=10
ogr2ogr -overwrite -f PMTiles demo/web/labels_ufs.pmtiles "$PG" -sql "select sigla, rank() over (order by populacao_2022 desc)::int as prioridade, ST_PointOnSurface(geom) as geom from geo.ufs" -nln labels_ufs -dsco MINZOOM=0 -dsco MAXZOOM=8
ogr2ogr -overwrite -f PMTiles demo/web/labels_municipios.pmtiles "$PG" -sql "select nome, populacao_2022 as populacao, capital, ST_PointOnSurface(geom) as geom from geo.municipios" -nln labels_municipios -dsco MINZOOM=3 -dsco MAXZOOM=12

# 3. values: every indicator-year pair, from the same api.tiles_* functions the panel uses (resumable)
python3 demo/extrair_catalogo.py

# 4. frontend in demo mode
(cd frontend && VITE_DEMO=1 VITE_MARTIN_URL=/martin VITE_API_URL= npx vite build --base=/brasil-em-dados/ --outDir ../demo/dist --emptyOutDir)
mkdir -p demo/dist/demo && cp demo/web/* demo/dist/demo/ && cp -r demo/dados demo/dist/demo/dados
touch demo/dist/.nojekyll
du -sh demo/dist
