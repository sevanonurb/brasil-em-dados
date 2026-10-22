/**
 * demo.js — static demo mode (VITE_DEMO=1): the panel runs without PostGIS, Martin or the API.
 *
 * Geometry never changes, values do. So the demo ships:
 *   - ufs.pmtiles / municipios.pmtiles   outlines + fixed properties, generated once by GDAL
 *   - dados/<metrica>/<ano>.json         {"m": {cod_ibge_7: value}, "u": {cod_uf: value}}
 *
 * Values were extracted from the SAME api.tiles_* functions the live panel uses (default
 * filters), so the demo cannot drift from the panel. This module intercepts the panel's own
 * requests and answers them from those files: the rest of the code is unchanged.
 *
 * Not available in the demo: census tracts, CNEFE addresses, and the cause/sex/race/age filters.
 */
import { PMTiles } from "pmtiles";
import Pbf from "pbf";
import { VectorTile } from "@mapbox/vector-tile";
import vtpbf from "vt-pbf";

export const DEMO = import.meta.env.VITE_DEMO === "1";
const BASE = import.meta.env.BASE_URL + "demo/";

const arquivos = {
  ufs: new PMTiles(BASE + "ufs.pmtiles"),
  municipios: new PMTiles(BASE + "municipios.pmtiles"),
};
const CAMADA = { ufs: "ufs", municipios: "municipios" };
const CHAVE = { ufs: ["u", "cod_uf"], municipios: ["m", "cod_ibge_7"] };

const valoresCache = new Map();
function valores(metrica, ano) {
  const k = `${metrica}/${ano}`;
  if (!valoresCache.has(k)) {
    valoresCache.set(k, fetchOriginal(`${BASE}dados/${k}.json`).then(r => (r.ok ? r.json() : { m: {}, u: {} })));
  }
  return valoresCache.get(k);
}

// a VectorTile layer proxy that adds valor_metrica (and drops features outside cod_uf)
function camadaComValores(layer, tabela, chave, codUf) {
  const idx = [];
  for (let i = 0; i < layer.length; i++) {
    const f = layer.feature(i);
    if (codUf == null || Number(f.properties.cod_uf) === codUf) idx.push(i);
  }
  return {
    version: layer.version, name: layer.name, extent: layer.extent, length: idx.length,
    feature(i) {
      const f = layer.feature(idx[i]);
      const v = tabela[String(f.properties[chave])];
      return {
        type: f.type, id: f.id,
        properties: v == null ? f.properties : { ...f.properties, valor_metrica: v },
        loadGeometry: () => f.loadGeometry(),
      };
    },
  };
}

// a rede do Pages às vezes corta uma leitura parcial ("Failed to fetch"): uma segunda tentativa
// resolve; cancelamento (o mapa saiu dali) sobe como AbortError, que o deck.gl ignora em silêncio
async function lerTile(tipo, z, x, y, sinal) {
  try {
    return await arquivos[tipo].getZxy(z, x, y, sinal);
  } catch (e) {
    if (sinal?.aborted || e?.name === "AbortError") throw e;
    await new Promise(ok => setTimeout(ok, 300));
    return arquivos[tipo].getZxy(z, x, y, sinal);
  }
}

async function tile(tipo, z, x, y, params, sinal) {
  const r = await lerTile(tipo, z, x, y, sinal);
  if (!r?.data) return new Response(null, { status: 204 });
  const vt = new VectorTile(new Pbf(new Uint8Array(r.data)));
  const camada = vt.layers[CAMADA[tipo]];
  if (!camada) return new Response(null, { status: 204 });
  const [tabelaKey, chave] = CHAVE[tipo];
  const metrica = params.get("metrica") || "taxa_mortalidade";
  const ano = params.get("ano") || "2023";
  const tabela = (await valores(metrica, ano))[tabelaKey] || {};
  const codUf = params.get("cod_uf") ? Number(params.get("cod_uf")) : null;
  const bytes = vtpbf({ layers: { [CAMADA[tipo]]: camadaComValores(camada, tabela, chave, tipo === "municipios" ? codUf : null) } });
  return new Response(bytes, { headers: { "Content-Type": "application/x-protobuf" } });
}

const fetchOriginal = window.fetch.bind(window);

if (DEMO) {
  window.fetch = async (entrada, opcoes) => {
    const url = new URL(typeof entrada === "string" ? entrada : entrada.url, location.href);
    const m = url.pathname.match(/\/tiles_(ufs|municipios|setores|cnefe)\/(\d+)\/(\d+)\/(\d+)/);
    if (m) {
      const [, tipo, z, x, y] = m;
      if (tipo === "setores" || tipo === "cnefe") return new Response(null, { status: 204 });
      return tile(tipo, +z, +x, +y, url.searchParams, opcoes?.signal ?? (typeof entrada === "string" ? undefined : entrada.signal));
    }
    if (/\/api\/anos\/?$/.test(url.pathname)) return fetchOriginal(BASE + "anos.json", opcoes);
    if (/\/api\/municipios\/?$/.test(url.pathname)) return fetchOriginal(BASE + "municipios.json", opcoes);
    return fetchOriginal(entrada, opcoes);
  };
}

// MapLibre loads label tiles in a worker (window.fetch is not seen there): point its sources at PMTiles.
export function fontesDeRotulosDemo(estilo) {
  if (!DEMO) return estilo;
  const abs = p => new URL(BASE + p, location.href).href;
  return {
    ...estilo,
    sources: {
      ...estilo.sources,
      "martin-labels": { type: "vector", url: `pmtiles://${abs("labels_municipios.pmtiles")}` },
      "martin-labels-uf": { type: "vector", url: `pmtiles://${abs("labels_ufs.pmtiles")}` },
    },
  };
}
