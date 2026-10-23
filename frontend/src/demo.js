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
 * Mortality filters (cause × sex × race × age) are computed in the browser from a count cube
 * (demo/cubo/, see taxasDoCubo). Not available in the demo: census tracts and CNEFE addresses.
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

// ── Cubo de mortalidade: qualquer combinação de causa × sexo × cor/raça × idade ─────────────
// As ~460 mil combinações prontas dariam ~15 GB; as contagens elementares cabem em ~7 MB
// (demo/extrair_cubo.py). A conta é a mesma de api.tiles_*:
//   taxa = round(óbitos do subgrupo × 100000 / população do mesmo subgrupo, 1)
// e sem filtro demográfico o denominador é populacao_2022, como no banco.
const METRICAS_CUBO = new Set(["taxa_mortalidade", "taxa_homicidio"]);

async function gunzip(url) {
  const r = await fetchOriginal(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return new Response(r.body.pipeThrough(new DecompressionStream("gzip"))).arrayBuffer();
}

let cuboBase = null;
function base() {
  cuboBase ??= Promise.all([
    fetchOriginal(BASE + "cubo/municipios.json").then(r => r.json()),
    gunzip(BASE + "cubo/populacao.bin.gz").then(b => new Uint32Array(b)),
  ]).then(([muns, pop]) => ({ ...muns, popSub: pop, ufIdx: new Map(muns.ufs.map((u, i) => [u, i])) }));
  return cuboBase;
}

const obitosCache = new Map();
function obitos(ano) {
  if (!obitosCache.has(ano)) {
    obitosCache.set(ano, gunzip(`${BASE}cubo/obitos-${ano}.bin.gz`).then(b => {
      const n = new Uint32Array(b, 0, 1)[0];
      let o = 4;
      const col = (T) => { const a = new T(b, o, n); o += n * T.BYTES_PER_ELEMENT; return a; };
      return { n, mun: col(Uint16Array), cont: col(Uint16Array), causa: col(Uint8Array), sr: col(Uint8Array), faixa: col(Uint8Array) };
    }));
  }
  return obitosCache.get(ano);
}

// round(x, 1) do Postgres: float8 → numeric com 15 dígitos significativos, meio para longe do zero
const arred1 = x => { const y = Number(x.toPrecision(15)); return Math.sign(y) * Math.round(Math.abs(y) * 10 + 1e-9) / 10; };

function filtrosDemograficos(params) {
  const fmin = Number(params.get("faixa_etaria_min") ?? 0), fmax = Number(params.get("faixa_etaria_max") ?? 17);
  return {
    metrica: params.get("metrica"),
    cid: params.get("cid10_capitulo") || null,
    sexo: params.get("sexo") || null,
    raca: params.get("cor_raca") ? Number(params.get("cor_raca")) : null,
    fmin, fmax, faixa: fmin !== 0 || fmax !== 17,
  };
}

function precisaDoCubo(params) {
  const f = filtrosDemograficos(params);
  return METRICAS_CUBO.has(f.metrica) && Boolean(f.sexo || f.raca != null || f.faixa || (f.metrica === "taxa_mortalidade" && f.cid));
}

async function taxasDoCubo(params) {
  const f = filtrosDemograficos(params);
  const ano = Number(params.get("ano") || 2023);
  const [B, O] = await Promise.all([base(), obitos(ano)]);
  const nMun = B.cod.length, nUf = B.ufs.length;

  // numerador: óbitos do subgrupo por município (e por UF, inclusive os sem município válido)
  const cap = f.cid && f.cid !== "suicidio" ? f.cid.charCodeAt(0) - 65 : -1;
  const sexo = f.sexo === "M" ? 1 : f.sexo === "F" ? 2 : 0;
  const porMun = new Float64Array(nMun), porUf = new Float64Array(nUf);
  for (let i = 0; i < O.n; i++) {
    const c = O.causa[i], sr = O.sr[i];
    if (f.metrica === "taxa_homicidio") { if (!((c >> 6) & 1)) continue; }
    else if (f.cid === "suicidio") { if (!((c >> 5) & 1)) continue; }
    else if (cap >= 0 && (c & 31) !== cap) continue;
    if (sexo && (sr & 3) !== sexo) continue;
    if (f.raca != null && (sr >> 2) !== f.raca) continue;
    if (f.faixa && (O.faixa[i] < f.fmin || O.faixa[i] > f.fmax)) continue;
    const m = O.mun[i];
    if (m < nMun) { porMun[m] += O.cont[i]; porUf[B.ufIdx.get(B.uf[m])] += O.cont[i]; }
    else porUf[m - nMun] += O.cont[i];
  }

  // denominador: a população do MESMO subgrupo (Censo 2022, SIDRA 9606), ou a total sem filtro demográfico
  const demografico = Boolean(f.sexo || f.raca != null || f.faixa);
  const denMun = new Float64Array(nMun), denUf = new Float64Array(nUf);
  const sexos = f.sexo === "M" ? [0] : f.sexo === "F" ? [1] : [0, 1];
  const r = f.raca ?? 0;
  for (let m = 0; m < nMun; m++) {
    let p = 0;
    if (demografico) {
      for (const s of sexos) {
        const o = ((m * 6 + r) * 2 + s) * 18;
        for (let k = f.fmin; k <= f.fmax; k++) p += B.popSub[o + k];
      }
    } else p = B.pop[m];
    denMun[m] = p;
    denUf[B.ufIdx.get(B.uf[m])] += p;
  }
  if (!demografico) B.pop_uf.forEach((p, i) => { denUf[i] = p; });

  const taxa = (num, den) => (den > 0 ? arred1(num * 100000 / den) : null);
  const res = { m: {}, u: {} };
  for (let m = 0; m < nMun; m++) { const v = taxa(porMun[m], denMun[m]); if (v != null) res.m[B.cod[m]] = v; }
  for (let i = 0; i < nUf; i++) { const v = taxa(porUf[i], denUf[i]); if (v != null) res.u[B.ufs[i]] = v; }
  return res;
}

const cuboCache = new Map();
function valoresFiltrados(params) {
  const k = [...params].filter(([c]) => c !== "cod_uf").sort().join("&");
  if (!cuboCache.has(k)) {
    if (cuboCache.size > 40) cuboCache.delete(cuboCache.keys().next().value);
    cuboCache.set(k, taxasDoCubo(params));
  }
  return cuboCache.get(k);
}

if (DEMO) window.__demoTaxas = (q) => taxasDoCubo(new URLSearchParams(q));   // para o validador contra o banco

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
  const tabela = (await (precisaDoCubo(params) ? valoresFiltrados(params) : valores(metrica, ano)))[tabelaKey] || {};
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
