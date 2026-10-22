/**
 * main.jsx — Painel Geoespacial do Brasil
 *
 * Deck.gl v9 + MapLibre GL JS — arquitetura integrada:
 * MapboxOverlay (interleaved) renderiza deck.gl DENTRO do MapLibre.
 * Basemap vetorial com camadas togáveis (ruas, labels) acima do choropleth.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import maplibregl from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { Deck } from "@deck.gl/core";
import { MVTLayer } from "@deck.gl/geo-layers";
import { Protocol } from "pmtiles";

import {
  getNivelSemantico,
  getTileUrl,
  calcularOpacidade,
  NIVEL_METADATA,
} from "./layers/semantic_zoom.js";
import { useFiltrosStore, CID10_LABELS } from "./filters/cross_filter.js";
import { METRICA_LABEL_CURTO, formatarParaTooltip } from "./utils/metricas.js";
import { gerarReport, gerarPreviewCarta } from "./utils/report.js";
import { PainelControles, UFS_BRASIL } from "./components/PainelControles.jsx";
import { PainelDetalhes } from "./components/PainelDetalhes.jsx";
import { PainelVisual } from "./components/PainelVisual.jsx";
import { PainelExportar } from "./components/PainelExportar.jsx";
import { Legenda } from "./components/Legenda.jsx";
import { BuscaMunicipio } from "./components/BuscaMunicipio.jsx";
import { DEMO, fontesDeRotulosDemo } from "./demo.js";

// Registra protocolo PMTiles no MapLibre
const pmtilesProtocol = new Protocol();
maplibregl.addProtocol("pmtiles", pmtilesProtocol.tile);

// ── Estilo vetorial do basemap ────────────────────────────────────────────────
// CARTO vector tiles (OpenMapTiles schema) — camadas individuais togáveis.
// O choropleth deck.gl é intercalado ANTES da camada "roads" via MapboxOverlay.
const BASEMAP_STYLE = {
  version: 8,
  sources: {
    carto: {
      type: "vector",
      tiles: [
        "https://tiles-a.basemaps.cartocdn.com/vectortiles/carto.streets/v1/{z}/{x}/{y}.mvt",
        "https://tiles-b.basemaps.cartocdn.com/vectortiles/carto.streets/v1/{z}/{x}/{y}.mvt",
        "https://tiles-c.basemaps.cartocdn.com/vectortiles/carto.streets/v1/{z}/{x}/{y}.mvt",
      ],
      maxzoom: 14,
      attribution: "© CARTO / OSM contributors",
    },
    satelite: {
      type: "raster",
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
      tileSize: 256,
      attribution: "© Esri",
    },
    "martin-labels": {
      type: "vector",
      tiles: [`${import.meta.env.VITE_MARTIN_URL}/tiles_labels_municipios/{z}/{x}/{y}`],
      maxzoom: 14,
    },
    "martin-labels-uf": {
      type: "vector",
      tiles: [`${import.meta.env.VITE_MARTIN_URL}/tiles_labels_ufs/{z}/{x}/{y}`],
      maxzoom: 8,
    },
  },
  glyphs: "https://tiles.basemaps.cartocdn.com/fonts/{fontstack}/{range}.pbf",
  layers: [
    // ── Fundo ──
    { id: "background", type: "background", paint: { "background-color": "#0d0f16" } },
    // ── Satélite (off por padrão) ──
    { id: "satelite", type: "raster", source: "satelite",
      layout: { visibility: "none" },
      paint: { "raster-opacity": 0.4 },
    },
    // ── Terra/água sutis ──
    { id: "water", type: "fill", source: "carto", "source-layer": "water",
      paint: { "fill-color": "#14171f" },
    },
    { id: "landcover", type: "fill", source: "carto", "source-layer": "landcover",
      paint: { "fill-color": "#181c28", "fill-opacity": 0.3 },
    },
    // ──────────────────────────────────────────────────────────────────────────
    // MARCADOR: deck.gl insere o choropleth AQUI (beforeId: "roads")
    // ──────────────────────────────────────────────────────────────────────────
    // ── Ruas (off por padrão) ──
    { id: "roads", type: "line", source: "carto", "source-layer": "transportation",
      layout: { visibility: "none", "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#3a4050", "line-width": ["interpolate", ["linear"], ["zoom"], 5, 0.3, 10, 0.8, 14, 1.5], "line-opacity": 0.7 },
      filter: ["all", ["!=", "class", "rail"]],
    },
    { id: "roads-major", type: "line", source: "carto", "source-layer": "transportation",
      layout: { visibility: "none", "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#505870", "line-width": ["interpolate", ["linear"], ["zoom"], 5, 0.5, 10, 1.5, 14, 3], "line-opacity": 0.8 },
      filter: ["in", "class", "motorway", "trunk", "primary"],
    },
    // ── Labels de UFs (zooms baixos — nível nacional) ──
    { id: "uf-labels", type: "symbol", source: "martin-labels-uf", "source-layer": "labels_ufs",
      minzoom: 0, maxzoom: 7,
      layout: {
        visibility: "none",
        "text-field": "{sigla}",
        "text-size": ["interpolate", ["linear"], ["zoom"], 2, 12, 4, 16, 6, 14],
        "text-font": ["Open Sans Bold"],
        "text-letter-spacing": 0.15,
        "text-anchor": "center",
        "text-max-width": 6,
        "text-padding": 2,
        "symbol-sort-key": ["get", "prioridade"],
        "text-allow-overlap": false,
      },
      paint: {
        "text-color": "#e2e8f0",
        "text-halo-color": "rgba(0,0,0,0.7)",
        "text-halo-width": 2,
        "text-opacity": ["interpolate", ["linear"], ["zoom"], 5, 1, 7, 0],
      },
    },
    // ── Labels de municípios brasileiros (Martin — somente Brasil) ──
    { id: "place-labels", type: "symbol", source: "martin-labels", "source-layer": "labels_municipios",
      layout: {
        visibility: "none",
        "text-field": "{nome}",
        "text-size": [
          "interpolate", ["linear"], ["zoom"],
          3, ["case", [">=", ["get", "populacao"], 1000000], 14, [">=", ["get", "populacao"], 500000], 12, 10],
          6, ["case", [">=", ["get", "populacao"], 1000000], 16, [">=", ["get", "populacao"], 200000], 14, [">=", ["get", "populacao"], 50000], 12, 11],
          10, ["case", [">=", ["get", "populacao"], 500000], 18, [">=", ["get", "populacao"], 100000], 15, 13],
          14, 14,
        ],
        "text-font": ["Open Sans Bold"],
        "text-transform": ["case", ["get", "capital"], "uppercase", "none"],
        "text-anchor": "center",
        "text-max-width": 8,
        "text-padding": 3,
        "symbol-sort-key": ["get", "prioridade"],
        "text-allow-overlap": false,
        "text-optional": false,
      },
      paint: {
        "text-color": [
          "case", ["get", "capital"], "#ffffff", "#c0c8d8",
        ],
        "text-halo-color": "#0d0f16",
        "text-halo-width": [
          "case", [">=", ["get", "populacao"], 500000], 2, 1.5,
        ],
      },
    },
    // ── Símbolos (pontos) de cidades ──
    { id: "place-dots", type: "circle", source: "martin-labels", "source-layer": "labels_municipios",
      layout: { visibility: "none" },
      paint: {
        "circle-radius": [
          "interpolate", ["linear"], ["zoom"],
          3, ["case", ["get", "capital"], 5, [">=", ["get", "populacao"], 1000000], 4, [">=", ["get", "populacao"], 500000], 3, 2],
          7, ["case", ["get", "capital"], 6, [">=", ["get", "populacao"], 1000000], 5, [">=", ["get", "populacao"], 200000], 4, 3],
          12, ["case", ["get", "capital"], 5, [">=", ["get", "populacao"], 500000], 4, 3],
        ],
        "circle-color": ["case", ["get", "capital"], "#ffffff", "#c0c8d8"],
        "circle-stroke-color": "#0d0f16",
        "circle-stroke-width": ["case", ["get", "capital"], 2, 1],
        "circle-opacity": 0.9,
      },
    },
    { id: "road-labels", type: "symbol", source: "carto", "source-layer": "transportation_name",
      layout: {
        visibility: "none",
        "text-field": "{name}", "text-size": ["interpolate", ["linear"], ["zoom"], 10, 9, 14, 12],
        "text-font": ["Open Sans Regular"],
        "symbol-placement": "line", "text-max-angle": 30,
      },
      paint: { "text-color": "#8090a0", "text-halo-color": "#0d0f16", "text-halo-width": 1 },
      minzoom: 12,
    },
  ],
};

// Intervalos realistas por métrica × nível semântico
// Derivados dos dados reais: SIM 2023, 5570 municípios, 27 UFs
const METRICAS_RANGES = {
  taxa_mortalidade: {
    NACIONAL: { min: 300,  max: 1000  },  // UF: 404–919 /100k
    ESTADUAL: { min: 0,    max: 1500  },  // Município: 163–1467 /100k
    MUNICIPAL: { min: 0,   max: 2000  },
  },
  taxa_homicidio: {
    NACIONAL: { min: 0, max: 60 },
    ESTADUAL: { min: 0, max: 150 },
    MUNICIPAL: { min: 0, max: 200 },
  },
  mortalidade_infantil: {
    NACIONAL:  { min: 0, max: 30  },   // Brasil 2022: ~10.7/1k
    ESTADUAL:  { min: 0, max: 60  },
    MUNICIPAL: { min: 0, max: 100 },
  },
  pib_per_capita: {
    NACIONAL: { min: 0, max: 80000 },
    ESTADUAL: { min: 0, max: 200000 },
    MUNICIPAL: { min: 0, max: 200000 },
  },
  receita_per_capita: {
    NACIONAL: { min: 0, max: 8000 },
    ESTADUAL: { min: 0, max: 20000 },
    MUNICIPAL: { min: 0, max: 20000 },
  },
  despesa_saude_per_capita: {
    NACIONAL:  { min: 0, max: 2000 },
    ESTADUAL:  { min: 0, max: 5000 },
    MUNICIPAL: { min: 0, max: 5000 },
  },
  despesa_educacao_per_capita: {
    NACIONAL:  { min: 0, max: 2000 },
    ESTADUAL:  { min: 0, max: 5000 },
    MUNICIPAL: { min: 0, max: 5000 },
  },
  // Densidade demográfica (hab/km²) — escala própria de setor censitário
  densidade_pop: {
    NACIONAL: { min: 0, max: 400 },
    ESTADUAL: { min: 0, max: 400 },
    MUNICIPAL: { min: 0, max: 20000 },
  },
  densidade_domiciliar: {
    NACIONAL: { min: 0, max: 150 },
    ESTADUAL: { min: 0, max: 150 },
    MUNICIPAL: { min: 0, max: 7000 },
  },
  populacao_absoluta: {
    NACIONAL:  { min: 0, max: 45000000 },
    ESTADUAL:  { min: 0, max: 500000 },
    MUNICIPAL: { min: 0, max: 2000 },
  },
  domicilios_absoluto: {
    NACIONAL:  { min: 0, max: 16000000 },
    ESTADUAL:  { min: 0, max: 200000 },
    MUNICIPAL: { min: 0, max: 800 },
  },
  area_territorial: {
    NACIONAL:  { min: 0, max: 1600000 },
    ESTADUAL:  { min: 0, max: 50000 },
    MUNICIPAL: { min: 0, max: 200 },
  },
  // Saneamento — Censo 2022 — percentual de domicílios (0–100%)
  acesso_agua: {
    NACIONAL:  { min: 50, max: 100 },
    ESTADUAL:  { min: 20, max: 100 },
    MUNICIPAL: { min: 0,  max: 100 },
  },
  acesso_esgoto: {
    NACIONAL:  { min: 0, max: 100 },
    ESTADUAL:  { min: 0, max: 100 },
    MUNICIPAL: { min: 0, max: 100 },
  },
  coleta_lixo: {
    NACIONAL:  { min: 40, max: 100 },
    ESTADUAL:  { min: 20, max: 100 },
    MUNICIPAL: { min: 0,  max: 100 },
  },
  // Saúde — SINASC: nascidos vivos por 1000 hab.
  taxa_natalidade: {
    NACIONAL:  { min: 8,  max: 25 },
    ESTADUAL:  { min: 5,  max: 35 },
    MUNICIPAL: { min: 0,  max: 50 },
  },
  // Saúde — CNES: leitos SUS por 1000 hab. (~1–3 nos municípios com hospital)
  leitos_sus_por_1k: {
    NACIONAL:  { min: 0, max: 3  },
    ESTADUAL:  { min: 0, max: 10 },
    MUNICIPAL: { min: 0, max: 20 },
  },
  // Saúde — CNES: médicos por 10.000 hab. (~2 interior, ~20 capitais)
  medicos_por_10k: {
    NACIONAL:  { min: 0, max: 30  },
    ESTADUAL:  { min: 0, max: 80  },
    MUNICIPAL: { min: 0, max: 150 },
  },
  // Educação — IDEB: escala 0–10 (meta nacional ~6)
  ideb_anos_iniciais: {
    NACIONAL:  { min: 3, max: 9 },
    ESTADUAL:  { min: 2, max: 9 },
    MUNICIPAL: { min: 1, max: 9 },
  },
  ideb_anos_finais: {
    NACIONAL:  { min: 3, max: 9 },
    ESTADUAL:  { min: 2, max: 9 },
    MUNICIPAL: { min: 1, max: 9 },
  },
  // Educação — Alfabetização (%)
  taxa_alfabetizacao: {
    NACIONAL:  { min: 75, max: 100 },
    ESTADUAL:  { min: 60, max: 100 },
    MUNICIPAL: { min: 40, max: 100 },
  },
  // Demográfico — Índice de envelhecimento: (pop 60+/pop 0-14)×100
  taxa_envelhecimento: {
    NACIONAL:  { min: 0, max: 200 },
    ESTADUAL:  { min: 0, max: 400 },
    MUNICIPAL: { min: 0, max: 600 },
  },
  // Demográfico — Razão de sexo: homens por 100 mulheres
  razao_sexo: {
    NACIONAL:  { min: 85, max: 115 },
    ESTADUAL:  { min: 75, max: 130 },
    MUNICIPAL: { min: 60, max: 160 },
  },
  // Demográfico — Média de moradores por domicílio
  media_moradores: {
    NACIONAL:  { min: 2.0, max: 4.0 },
    ESTADUAL:  { min: 1.5, max: 5.0 },
    MUNICIPAL: { min: 1.0, max: 6.0 },
  },
  // Domicílios com internet (%)
  domicilios_internet: {
    NACIONAL:  { min: 40, max: 100 },
    ESTADUAL:  { min: 20, max: 100 },
    MUNICIPAL: { min: 0,  max: 100 },
  },
  // % da população em aglomerados subnormais (favelas)
  pop_favelas_pct: {
    NACIONAL:  { min: 0, max: 25  },
    ESTADUAL:  { min: 0, max: 50  },
    MUNICIPAL: { min: 0, max: 100 },
  },
  // VBP agrícola per capita (R$)
  vbp_agricola_per_capita: {
    NACIONAL:  { min: 0, max: 10000  },
    ESTADUAL:  { min: 0, max: 40000  },
    MUNICIPAL: { min: 0, max: 100000 },
  },
  vbp_pecuaria_per_capita: {
    NACIONAL:  { min: 0, max: 3000  },
    ESTADUAL:  { min: 0, max: 10000 },
    MUNICIPAL: { min: 0, max: 30000 },
  },
  // Fiscal — Dívida Consolidada / RCL (%) — limite LRF = 120%
  divida_rcl: {
    NACIONAL:  { min: 0, max: 100 },
    ESTADUAL:  { min: 0, max: 200 },
    MUNICIPAL: { min: 0, max: 300 },
  },
  // Fiscal — Despesa de Pessoal / RCL (%) — limite LRF = 54%
  despesa_pessoal_rcl: {
    NACIONAL:  { min: 20, max: 60  },
    ESTADUAL:  { min: 0,  max: 80  },
    MUNICIPAL: { min: 0,  max: 120 },
  },
  // Renda (Censo 2022 Amostra) — em R$ nominais
  renda_domiciliar_per_capita: {
    NACIONAL:  { min: 500,  max: 3000  },
    ESTADUAL:  { min: 300,  max: 6000  },
    MUNICIPAL: { min: 200,  max: 8000  },
  },
  renda_domiciliar_mediana_pc: {
    NACIONAL:  { min: 400,  max: 2000  },
    ESTADUAL:  { min: 200,  max: 4000  },
    MUNICIPAL: { min: 100,  max: 5000  },
  },
  renda_media_trabalho: {
    NACIONAL:  { min: 1000, max: 5000  },
    ESTADUAL:  { min: 800,  max: 8000  },
    MUNICIPAL: { min: 600,  max: 10000 },
  },
  renda_mediana_trabalho: {
    NACIONAL:  { min: 800,  max: 3000  },
    ESTADUAL:  { min: 600,  max: 5000  },
    MUNICIPAL: { min: 400,  max: 6000  },
  },
  // Educação (Censo 2022 Amostra)
  media_anos_estudo: {
    NACIONAL:  { min: 4,  max: 12 },
    ESTADUAL:  { min: 2,  max: 14 },
    MUNICIPAL: { min: 1,  max: 16 },
  },
  pct_superior_completo: {
    NACIONAL:  { min: 0,  max: 25 },
    ESTADUAL:  { min: 0,  max: 40 },
    MUNICIPAL: { min: 0,  max: 50 },
  },
  taxa_deficiencia: {
    NACIONAL:  { min: 3,  max: 12 },
    ESTADUAL:  { min: 0,  max: 15 },
    MUNICIPAL: { min: 0,  max: 20 },
  },
  taxa_ocupacao: {
    NACIONAL:  { min: 35, max: 70 },
    ESTADUAL:  { min: 30, max: 75 },
    MUNICIPAL: { min: 20, max: 80 },
  },
  idade_mediana: {
    NACIONAL:  { min: 20, max: 45 },
    ESTADUAL:  { min: 15, max: 55 },
    MUNICIPAL: { min: 15, max: 60 },
  },
  // PIB setorial (%) — São Paulo: agro 0.01%, ind 12%, srv 83%
  pct_pib_agropecuaria: {
    NACIONAL:  { min: 0,  max: 30 },
    ESTADUAL:  { min: 0,  max: 60 },
    MUNICIPAL: { min: 0,  max: 80 },
  },
  pct_pib_industria: {
    NACIONAL:  { min: 0,  max: 30 },
    ESTADUAL:  { min: 0,  max: 50 },
    MUNICIPAL: { min: 0,  max: 70 },
  },
  pct_pib_servicos: {
    NACIONAL:  { min: 30, max: 90 },
    ESTADUAL:  { min: 20, max: 95 },
    MUNICIPAL: { min: 10, max: 98 },
  },
  // Raça/Etnia (Censo 2022)
  pct_indigena: {
    NACIONAL:  { min: 0, max: 10  },
    ESTADUAL:  { min: 0, max: 30  },
    MUNICIPAL: { min: 0, max: 95  },
  },
  pct_quilombola: {
    NACIONAL:  { min: 0, max: 5   },
    ESTADUAL:  { min: 0, max: 20  },
    MUNICIPAL: { min: 0, max: 85  },
  },
  // Censo Agropecuário 2017 — agricultura familiar
  pct_agrofamiliar: {
    NACIONAL:  { min: 0, max: 100 },
    ESTADUAL:  { min: 0, max: 100 },
    MUNICIPAL: { min: 0, max: 100 },
  },
  // CEMPRE — empresas por mil hab.
  empresas_por_1k: {
    NACIONAL:  { min: 0, max: 80  },
    ESTADUAL:  { min: 0, max: 150 },
    MUNICIPAL: { min: 0, max: 300 },
  },
  // Censo Agropecuário 2017 — mecanização e crédito
  pct_mecanizado: {
    NACIONAL:  { min: 0, max: 80  },
    ESTADUAL:  { min: 0, max: 100 },
    MUNICIPAL: { min: 0, max: 100 },
  },
  pct_financiamento: {
    NACIONAL:  { min: 0, max: 30  },
    ESTADUAL:  { min: 0, max: 60  },
    MUNICIPAL: { min: 0, max: 80  },
  },
  // Censo 2022 — migração e escolarização
  taxa_migracao: {
    NACIONAL:  { min: 0, max: 15  },
    ESTADUAL:  { min: 0, max: 30  },
    MUNICIPAL: { min: 0, max: 60  },
  },
  taxa_escolarizacao_1517: {
    NACIONAL:  { min: 50, max: 100 },
    ESTADUAL:  { min: 40, max: 100 },
    MUNICIPAL: { min: 40, max: 100 },
  },
  taxa_desemprego: {
    NACIONAL:  { min: 0, max: 15  },
    ESTADUAL:  { min: 0, max: 25  },
    MUNICIPAL: { min: 0, max: 40  },
  },
  taxa_pendular: {
    NACIONAL:  { min: 0, max: 20  },
    ESTADUAL:  { min: 0, max: 40  },
    MUNICIPAL: { min: 0, max: 70  },
  },
  taxa_informalidade: {
    NACIONAL:  { min: 0, max: 50  },
    ESTADUAL:  { min: 0, max: 70  },
    MUNICIPAL: { min: 0, max: 90  },
  },
  pct_baixa_renda: {
    NACIONAL:  { min: 0, max: 30  },
    ESTADUAL:  { min: 0, max: 50  },
    MUNICIPAL: { min: 0, max: 70  },
  },
  pct_renda_trabalho: {
    NACIONAL:  { min: 20, max: 90 },
    ESTADUAL:  { min: 15, max: 95 },
    MUNICIPAL: { min: 10, max: 98 },
  },
  pct_chefia_feminina: {
    NACIONAL:  { min: 25, max: 65 },
    ESTADUAL:  { min: 20, max: 70 },
    MUNICIPAL: { min: 15, max: 75 },
  },
  domicilios_maquina_lavar: {
    NACIONAL:  { min: 0,  max: 100 },
    ESTADUAL:  { min: 0,  max: 100 },
    MUNICIPAL: { min: 0,  max: 100 },
  },
  superlotacao_domiciliar: {
    NACIONAL:  { min: 0,  max: 10  },
    ESTADUAL:  { min: 0,  max: 20  },
    MUNICIPAL: { min: 0,  max: 60  },
  },
  domicilios_alugados: {
    NACIONAL:  { min: 0,  max: 40  },
    ESTADUAL:  { min: 0,  max: 55  },
    MUNICIPAL: { min: 0,  max: 55  },
  },
  media_filhos_mulher: {
    NACIONAL:  { min: 0.5, max: 3.5 },
    ESTADUAL:  { min: 0.5, max: 3.5 },
    MUNICIPAL: { min: 0.5, max: 3.5 },
  },
  domicilios_monoparentais: {
    NACIONAL:  { min: 5,  max: 25  },
    ESTADUAL:  { min: 5,  max: 28  },
    MUNICIPAL: { min: 4,  max: 28  },
  },
  // Urbanização e Qualidade Habitacional — Censo 2022
  pct_urbano: {
    NACIONAL:  { min: 0,  max: 100 },
    ESTADUAL:  { min: 0,  max: 100 },
    MUNICIPAL: { min: 0,  max: 100 },
  },
  pct_alvenaria: {
    NACIONAL:  { min: 20, max: 100 },
    ESTADUAL:  { min: 10, max: 100 },
    MUNICIPAL: { min: 5,  max: 100 },
  },
  pct_banheiro_exclusivo: {
    NACIONAL:  { min: 30, max: 100 },
    ESTADUAL:  { min: 20, max: 100 },
    MUNICIPAL: { min: 10, max: 100 },
  },
  taxa_nupcialidade: {
    NACIONAL:  { min: 0, max: 10 },
    ESTADUAL:  { min: 0, max: 15 },
    MUNICIPAL: { min: 0, max: 20 },
  },
  taxa_divorcialidade: {
    NACIONAL:  { min: 0, max: 5 },
    ESTADUAL:  { min: 0, max: 8 },
    MUNICIPAL: { min: 0, max: 12 },
  },
  // Registro Civil — Separações e Óbitos Fetais
  taxa_separacao: {
    NACIONAL:  { min: 0, max: 1.5 },
    ESTADUAL:  { min: 0, max: 3   },
    MUNICIPAL: { min: 0, max: 6   },
  },
  taxa_obito_fetal: {
    NACIONAL:  { min: 5,  max: 20 },
    ESTADUAL:  { min: 0,  max: 35 },
    MUNICIPAL: { min: 0,  max: 60 },
  },
  // Equipamentos Domésticos — Censo 2022 (% domicílios)
  pct_geladeira: {
    NACIONAL:  { min: 80, max: 100 },
    ESTADUAL:  { min: 60, max: 100 },
    MUNICIPAL: { min: 40, max: 100 },
  },
  pct_ar_condicionado: {
    NACIONAL:  { min: 0,  max: 60  },
    ESTADUAL:  { min: 0,  max: 80  },
    MUNICIPAL: { min: 0,  max: 100 },
  },
  pct_freezer: {
    NACIONAL:  { min: 0,  max: 60  },
    ESTADUAL:  { min: 0,  max: 80  },
    MUNICIPAL: { min: 0,  max: 100 },
  },
  pct_tv: {
    NACIONAL:  { min: 60, max: 100 },
    ESTADUAL:  { min: 50, max: 100 },
    MUNICIPAL: { min: 30, max: 100 },
  },
  pct_automovel_domicilio: {
    NACIONAL:  { min: 0,  max: 70  },
    ESTADUAL:  { min: 0,  max: 80  },
    MUNICIPAL: { min: 0,  max: 100 },
  },
  pct_motocicleta_domicilio: {
    NACIONAL:  { min: 0,  max: 60  },
    ESTADUAL:  { min: 0,  max: 70  },
    MUNICIPAL: { min: 0,  max: 100 },
  },
  pct_microondas: {
    NACIONAL:  { min: 0,  max: 90  },
    ESTADUAL:  { min: 0,  max: 100 },
    MUNICIPAL: { min: 0,  max: 100 },
  },
  pct_computador: {
    NACIONAL:  { min: 0,  max: 80  },
    ESTADUAL:  { min: 0,  max: 90  },
    MUNICIPAL: { min: 0,  max: 100 },
  },
  // PPM — Rebanhos (cabeças/hab. ou cabeças/km²)
  rebanho_bovino_por_km2: {
    NACIONAL:  { min: 0, max: 0.6  },
    ESTADUAL:  { min: 0, max: 2    },
    MUNICIPAL: { min: 0, max: 8    },
  },
  rebanho_bovino_por_hab: {
    NACIONAL:  { min: 0, max: 6    },
    ESTADUAL:  { min: 0, max: 25   },
    MUNICIPAL: { min: 0, max: 80   },
  },
  rebanho_equino_por_hab: {
    NACIONAL:  { min: 0, max: 0.3  },
    ESTADUAL:  { min: 0, max: 1    },
    MUNICIPAL: { min: 0, max: 4    },
  },
  rebanho_suino_por_hab: {
    NACIONAL:  { min: 0, max: 1.5  },
    ESTADUAL:  { min: 0, max: 5    },
    MUNICIPAL: { min: 0, max: 20   },
  },
  rebanho_ovino_por_hab: {
    NACIONAL:  { min: 0, max: 0.8  },
    ESTADUAL:  { min: 0, max: 3    },
    MUNICIPAL: { min: 0, max: 15   },
  },
  rebanho_caprino_por_hab: {
    NACIONAL:  { min: 0, max: 0.4  },
    ESTADUAL:  { min: 0, max: 1.5  },
    MUNICIPAL: { min: 0, max: 8    },
  },
  rebanho_galinaceos_por_hab: {
    NACIONAL:  { min: 0, max: 30   },
    ESTADUAL:  { min: 0, max: 80   },
    MUNICIPAL: { min: 0, max: 300  },
  },
  // PPM — Produção Pecuária
  producao_leite_por_vaca: {
    NACIONAL:  { min: 500,  max: 4000  },
    ESTADUAL:  { min: 200,  max: 6000  },
    MUNICIPAL: { min: 0,    max: 8000  },
  },
  producao_leite_per_capita: {
    NACIONAL:  { min: 0, max: 1500  },
    ESTADUAL:  { min: 0, max: 5000  },
    MUNICIPAL: { min: 0, max: 15000 },
  },
  producao_mel_por_colmeia: {
    NACIONAL:  { min: 5,  max: 35  },
    ESTADUAL:  { min: 2,  max: 50  },
    MUNICIPAL: { min: 0,  max: 80  },
  },
  producao_mel_kg: {
    NACIONAL:  { min: 0, max: 8000000  },
    ESTADUAL:  { min: 0, max: 600000   },
    MUNICIPAL: { min: 0, max: 100000   },
  },
  producao_ovos_total: {
    NACIONAL:  { min: 0, max: 600000   },
    ESTADUAL:  { min: 0, max: 60000    },
    MUNICIPAL: { min: 0, max: 10000    },
  },
  producao_ovos_per_capita: {
    NACIONAL:  { min: 0, max: 50   },
    ESTADUAL:  { min: 0, max: 150  },
    MUNICIPAL: { min: 0, max: 500  },
  },
  // SINAN — Epidemiologia (/100k hab.)
  incidencia_dengue: {
    NACIONAL:  { min: 0, max: 2000  },
    ESTADUAL:  { min: 0, max: 6000  },
    MUNICIPAL: { min: 0, max: 15000 },
  },
  incidencia_tuberculose: {
    NACIONAL:  { min: 0, max: 60   },
    ESTADUAL:  { min: 0, max: 120  },
    MUNICIPAL: { min: 0, max: 250  },
  },
  incidencia_hanseniase: {
    NACIONAL:  { min: 0, max: 30  },
    ESTADUAL:  { min: 0, max: 60  },
    MUNICIPAL: { min: 0, max: 120 },
  },
  incidencia_leishmaniose: {
    NACIONAL:  { min: 0, max: 15  },
    ESTADUAL:  { min: 0, max: 30  },
    MUNICIPAL: { min: 0, max: 80  },
  },
  // SIH — Internações SUS
  taxa_internacao_sus: {
    NACIONAL:  { min: 40, max: 130  },   // /1k hab. — Brasil ~95/1k
    ESTADUAL:  { min: 20, max: 180  },
    MUNICIPAL: { min: 0,  max: 250  },
  },
  taxa_internacao_cardiovascular: {
    NACIONAL:  { min: 0, max: 250  },    // /100k hab.
    ESTADUAL:  { min: 0, max: 500  },
    MUNICIPAL: { min: 0, max: 800  },
  },
  taxa_internacao_respiratoria: {
    NACIONAL:  { min: 0, max: 120  },
    ESTADUAL:  { min: 0, max: 250  },
    MUNICIPAL: { min: 0, max: 500  },
  },
  taxa_internacao_mental: {
    NACIONAL:  { min: 0, max: 60   },
    ESTADUAL:  { min: 0, max: 120  },
    MUNICIPAL: { min: 0, max: 250  },
  },
  media_permanencia_sus: {
    NACIONAL:  { min: 3, max: 8    },    // dias
    ESTADUAL:  { min: 2, max: 12   },
    MUNICIPAL: { min: 0, max: 20   },
  },
  // Censo Escolar INEP — Rendimento (%)
  taxa_aprovacao_ef: {
    NACIONAL:  { min: 70, max: 100 },
    ESTADUAL:  { min: 60, max: 100 },
    MUNICIPAL: { min: 50, max: 100 },
  },
  taxa_reprovacao_ef: {
    NACIONAL:  { min: 0, max: 20   },
    ESTADUAL:  { min: 0, max: 25   },
    MUNICIPAL: { min: 0, max: 35   },
  },
  taxa_abandono_ef: {
    NACIONAL:  { min: 0, max: 10   },
    ESTADUAL:  { min: 0, max: 15   },
    MUNICIPAL: { min: 0, max: 30   },
  },
  taxa_aprovacao_em: {
    NACIONAL:  { min: 65, max: 100 },
    ESTADUAL:  { min: 55, max: 100 },
    MUNICIPAL: { min: 40, max: 100 },
  },
  taxa_abandono_em: {
    NACIONAL:  { min: 0, max: 15   },
    ESTADUAL:  { min: 0, max: 25   },
    MUNICIPAL: { min: 0, max: 40   },
  },
  distorcao_idade_serie_ef: {
    NACIONAL:  { min: 0, max: 40   },
    ESTADUAL:  { min: 0, max: 60   },
    MUNICIPAL: { min: 0, max: 80   },
  },
  distorcao_idade_serie_em: {
    NACIONAL:  { min: 0, max: 30   },
    ESTADUAL:  { min: 0, max: 50   },
    MUNICIPAL: { min: 0, max: 70   },
  },
  // SENATRAN — Frota Veicular (/1k hab.)
  frota_automovel_por_1k: {
    NACIONAL:  { min: 50,  max: 400  },
    ESTADUAL:  { min: 20,  max: 600  },
    MUNICIPAL: { min: 0,   max: 900  },
  },
  frota_moto_por_1k: {
    NACIONAL:  { min: 30,  max: 350  },
    ESTADUAL:  { min: 10,  max: 500  },
    MUNICIPAL: { min: 0,   max: 800  },
  },
  frota_caminhao_por_1k: {
    NACIONAL:  { min: 0, max: 35   },
    ESTADUAL:  { min: 0, max: 60   },
    MUNICIPAL: { min: 0, max: 120  },
  },
  frota_onibus_por_1k: {
    NACIONAL:  { min: 0, max: 15   },
    ESTADUAL:  { min: 0, max: 25   },
    MUNICIPAL: { min: 0, max: 50   },
  },
  frota_total_por_1k: {
    NACIONAL:  { min: 80,  max: 900  },
    ESTADUAL:  { min: 50,  max: 1200 },
    MUNICIPAL: { min: 0,   max: 2000 },
  },
};

// Escalas por capítulo CID-10 (taxas /100k bem menores que mortalidade geral ~700/100k)
// NACIONAL = UF-level, ESTADUAL = município-level (maior variação)
const CID10_RANGES = {
  // Doenças crônicas — causas líderes de morte no Brasil
  I:        { NACIONAL: { min: 0, max: 400 }, ESTADUAL: { min: 0, max: 800  } }, // Cardiovascular: ~170/100k nac.
  C:        { NACIONAL: { min: 0, max: 200 }, ESTADUAL: { min: 0, max: 400  } }, // Neoplasias: ~103/100k nac.
  J:        { NACIONAL: { min: 0, max: 100 }, ESTADUAL: { min: 0, max: 200  } }, // Respiratório: ~72/100k nac.
  E:        { NACIONAL: { min: 0, max: 60  }, ESTADUAL: { min: 0, max: 150  } }, // Diabetes: ~40/100k nac.
  K:        { NACIONAL: { min: 0, max: 50  }, ESTADUAL: { min: 0, max: 120  } }, // Digestivo: ~32/100k nac.
  N:        { NACIONAL: { min: 0, max: 40  }, ESTADUAL: { min: 0, max: 100  } }, // Renal: ~21/100k nac.
  G:        { NACIONAL: { min: 0, max: 40  }, ESTADUAL: { min: 0, max: 100  } }, // Neurológico: ~21/100k nac.
  // Doenças infecciosas
  B:        { NACIONAL: { min: 0, max: 80  }, ESTADUAL: { min: 0, max: 200  } }, // HIV/Hepatite: ~47/100k nac.
  A:        { NACIONAL: { min: 0, max: 30  }, ESTADUAL: { min: 0, max: 80   } }, // TB/Cólera: ~17/100k nac.
  // Causas externas
  suicidio: { NACIONAL: { min: 0, max: 20  }, ESTADUAL: { min: 0, max: 50   } }, // Suicídio: ~8/100k nac.
  V:        { NACIONAL: { min: 0, max: 40  }, ESTADUAL: { min: 0, max: 100  } }, // Acidente transporte: ~16/100k
  W:        { NACIONAL: { min: 0, max: 30  }, ESTADUAL: { min: 0, max: 80   } }, // Quedas/afogamentos: ~13/100k
  X:        { NACIONAL: { min: 0, max: 60  }, ESTADUAL: { min: 0, max: 150  } }, // Causas externas diversas
  Y:        { NACIONAL: { min: 0, max: 20  }, ESTADUAL: { min: 0, max: 50   } }, // Causas ext. indeterminadas
  // Populações específicas
  O:        { NACIONAL: { min: 0, max: 8   }, ESTADUAL: { min: 0, max: 20   } }, // Materna: ~1/100k nac.
  P:        { NACIONAL: { min: 0, max: 20  }, ESTADUAL: { min: 0, max: 50   } }, // Perinatais: ~9/100k nac.
  F:        { NACIONAL: { min: 0, max: 15  }, ESTADUAL: { min: 0, max: 40   } }, // Transtornos mentais: ~7/100k
  Q:        { NACIONAL: { min: 0, max: 12  }, ESTADUAL: { min: 0, max: 30   } }, // Malformações: ~5/100k nac.
};

const METRICAS_SEM_DADOS = [];

// Métricas onde ALTO = BOM → escala invertida (vermelho=baixo/ruim, verde=alto/bom)
const METRICAS_INVERTIDAS = new Set([
  // Saneamento básico
  "acesso_agua", "acesso_esgoto", "coleta_lixo",
  // Saúde — oferta de recursos
  "medicos_por_10k", "leitos_sus_por_1k",
  // Educação — qualidade e desempenho
  "ideb_anos_iniciais", "ideb_anos_finais",
  "taxa_alfabetizacao", "media_anos_estudo", "pct_superior_completo",
  "taxa_escolarizacao_1517",
  "taxa_aprovacao_ef", "taxa_aprovacao_em",
  // Renda e produto econômico
  "pib_per_capita", "receita_per_capita",
  "renda_domiciliar_per_capita", "renda_domiciliar_mediana_pc",
  "renda_media_trabalho", "renda_mediana_trabalho",
  // Gasto público — investimento social
  "despesa_saude_per_capita", "despesa_educacao_per_capita",
  // Mercado de trabalho formal
  "taxa_ocupacao", "pct_renda_trabalho",
  // Infraestrutura digital
  "domicilios_internet",
  // Habitação — qualidade construtiva
  "pct_alvenaria", "pct_banheiro_exclusivo",
  // Acesso a bens essenciais
  "pct_geladeira", "pct_computador", "domicilios_maquina_lavar",
  // Agropecuária — desenvolvimento tecnológico
  "pct_mecanizado", "pct_financiamento", "pct_agrofamiliar",
  // Atividade econômica formal
  "empresas_por_1k",
]);

// Busca os anos disponíveis no banco via API e atualiza o store
function useAnosDisponiveis() {
  const setAnosDisponiveis = useFiltrosStore(s => s.setAnosDisponiveis);
  useEffect(() => {
    const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:80";
    fetch(`${apiUrl}/api/anos`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => { if (data) setAnosDisponiveis(data); })
      .catch(err => {
        // Mantém ANOS_POR_METRICA_DEFAULT como fallback, mas torna a falha visível.
        console.warn(`[anos] falha ao buscar ${apiUrl}/api/anos — usando fallback:`, err.message);
      });
  }, [setAnosDisponiveis]);
}

// Retorna uma função getTooltip que mostra o indicador atualmente selecionado.
function makeTooltip(metrica, cid10) {
  const TOOLTIP_STYLE = {
    backgroundColor: "#1a202c",
    color: "#e2e8f0",
    border: "1px solid #4a5568",
    borderRadius: "6px",
    padding: "8px 12px",
    fontSize: "12px",
    maxWidth: "240px",
  };

  return ({ object }) => {
    if (!object?.properties) return null;
    const p = object.properties;
    const nome = p.nome_municipio || p.nome || p.sigla || `Setor ${p.cod_setor}`;

    let label = METRICA_LABEL_CURTO[metrica] || metrica;
    if (metrica === "taxa_mortalidade" && cid10) {
      label = CID10_LABELS[cid10] ?? `Mortalidade CID-${cid10}`;
    }

    const formatado = formatarParaTooltip(p.valor_metrica, metrica);

    const pop = p.populacao_2022 ?? p.populacao_total;
    const popLine = pop != null
      ? `<br/>Pop.: <b>${Number(pop).toLocaleString("pt-BR")}</b>`
      : "";

    return {
      html: `<strong>${nome}</strong><br/>${label}: ${formatado}${popLine}`,
      style: TOOLTIP_STYLE,
    };
  };
}

const INITIAL_VIEW = {
  longitude: -51.9253,
  latitude: -14.235,
  zoom: 4,
  pitch: 0,
  bearing: 0,
};

/**
 * Gera a cor coroplética para um valor normalizado [0,1].
 * - Padrão (invertida=false): ciano → amarelo → vermelho  (baixo=neutro/bom, alto=ruim)
 * - Invertida (invertida=true): vermelho → amarelo → verde (baixo=ruim, alto=bom)
 */
// Rampa de 6 paradas — perceptualmente distinta em cada faixa percentil.
// Com normalização quantílica, cada ~17% dos municípios recebe uma cor própria.
// Ultra-violeta no extremo sinaliza outliers sem se confundir com o resto.
//   t=0.0  Azul         — valor mais baixo
//   t=0.2  Ciano/Teal   — baixo-médio
//   t=0.4  Verde-lima   — médio-baixo
//   t=0.6  Amarelo/Ouro — médio-alto
//   t=0.8  Laranja-verm — alto
//   t=1.0  Violeta      — extremo (ultra-violeta)
const RAMPA_COR = [
  [40, 130, 255],   // 0.0 — Azul
  [0,  210, 190],   // 0.2 — Teal
  [100, 230, 50],   // 0.4 — Verde-lima
  [255, 220, 0],    // 0.6 — Amarelo/Ouro
  [255, 65,  15],   // 0.8 — Laranja-vermelho
  [175, 20, 220],   // 1.0 — Violeta (ultra-violeta)
];

function getCorCoroplética(valorNormalizado, opacity = 220, invertida = false) {
  const t = Math.max(0, Math.min(1, invertida ? 1 - valorNormalizado : valorNormalizado));
  const scaled = t * (RAMPA_COR.length - 1);
  const i = Math.min(Math.floor(scaled), RAMPA_COR.length - 2);
  const f = scaled - i;
  const c0 = RAMPA_COR[i], c1 = RAMPA_COR[i + 1];
  return [
    Math.round(c0[0] + f * (c1[0] - c0[0])),
    Math.round(c0[1] + f * (c1[1] - c0[1])),
    Math.round(c0[2] + f * (c1[2] - c0[2])),
    opacity,
  ];
}

function normalizarValor(v, min, max) {
  if (max === min) return 0.5;
  const n = typeof v === "number" ? v : Number(v);
  if (!isFinite(n)) return 0;
  return Math.max(0, Math.min(1, (n - min) / (max - min)));
}

/**
 * Computa os percentis P2 e P98 de um array de valores numéricos.
 * Usado para os rótulos da legenda (referência absoluta min/max visível).
 */
function computePercentileBounds(values, pLow = 0.02, pHigh = 0.98) {
  if (values.length < 20) return null;
  const sorted = values.slice().sort((a, b) => a - b);
  const lo = sorted[Math.floor(sorted.length * pLow)];
  const hi = sorted[Math.min(Math.floor(sorted.length * pHigh), sorted.length - 1)];
  if (!isFinite(lo) || !isFinite(hi) || lo >= hi) return null;
  return { min: lo, max: hi };
}

/**
 * Normalização por quantil: retorna o rank percentual de v no array ordenado.
 * Resolve distribuições assimétricas (skewed) — garante que ~50% dos valores
 * ficam em cada metade da escala, independente de concentração ou outliers.
 * Usa busca binária: O(log n) por chamada.
 */
function quantileNormalizar(v, sortedValues) {
  const n = typeof v === "number" ? v : Number(v);
  if (!isFinite(n) || !sortedValues || sortedValues.length === 0) return null;
  let lo = 0, hi = sortedValues.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (sortedValues[mid] < n) lo = mid + 1;
    else hi = mid;
  }
  return lo / sortedValues.length;
}

// ─────────────────────────────────────────────────────────────────────────────
export default function App() {
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);
  const overlayRef = useRef(null);   // MapboxOverlay (interleaved)
  const deckCompareRef = useRef(null);

  const [viewState, setViewState] = useState(INITIAL_VIEW);
  const [featureSelecionada, setFeatureSelecionada] = useState(null);
  const [estatisticas, setEstatisticas] = useState({ min: 0, max: 100 });
  const [flyTarget, setFlyTarget] = useState(null);

  // Normalização adaptativa: coleta valores dos tiles carregados e computa distribuição real
  const [normBounds, setNormBounds] = useState(null); // {min: P2, max: P98} para rótulos da legenda
  const [normSorted, setNormSorted] = useState(null); // array ordenado para normalização por quantil
  const valoresColetados = useRef([]);                 // valores acumulados dos tiles
  const debounceTimer    = useRef(null);               // debounce para o cálculo
  const boundsComputados = useRef(false);              // trava: calcula só uma vez por contexto

  const filtros = useFiltrosStore();
  useAnosDisponiveis(); // busca anos disponíveis do banco na inicialização

  // Escolher um estado sem mover o mapa não mudava nada visível na escala nacional:
  // voa até a caixa dos municípios daquela UF (a mesma lista da busca).
  const municipiosRef = useRef(null);
  const escolherUF = useCallback(async (cod) => {
    filtros.setUF(cod);
    if (!cod) { setFlyTarget({ ...INITIAL_VIEW, transitionDuration: 1200 }); return; }
    const sigla = UFS_BRASIL.find(u => u.cod === cod)?.sigla;
    try {
      if (!municipiosRef.current) {
        const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:80";
        const r = await fetch(`${apiUrl}/api/municipios`);
        municipiosRef.current = r.ok ? await r.json() : [];
      }
      const pts = municipiosRef.current.filter(m => m.uf === sigla);
      if (!pts.length) return;
      const lons = pts.map(m => m.lon), lats = pts.map(m => m.lat);
      const [x0, x1, y0, y1] = [Math.min(...lons), Math.max(...lons), Math.min(...lats), Math.max(...lats)];
      const vao = Math.max(x1 - x0, (y1 - y0) * 1.2, 0.5);
      setFlyTarget({
        longitude: (x0 + x1) / 2, latitude: (y0 + y1) / 2,
        zoom: Math.min(8, Math.log2(360 / vao) - 0.4),
        pitch: 0, bearing: 0, transitionDuration: 1200,
      });
    } catch { /* sem a lista o filtro continua valendo, só não há voo */ }
  }, [filtros.setUF]);

  // null = automático (segue o zoom); string = nível forçado pelo painel
  const [nivelForcado, setNivelForcado] = useState(null);

  // Controles visuais — não afetam dados, apenas renderização
  const [visual, setVisual] = useState({
    opacidadeOverlay: 1.0,        // 0–1: opacidade das camadas coropléticas
    bordurasMunicipios: true,     // mostrar bordas dos municípios
    bordurasEstados: true,        // mostrar bordas dos estados/UFs
    opacidadeBasemap: null,       // null = zoom-based automático; 0–1 = manual
    mostrarSulAmerica: false,     // exibe basemap visível em todos os zooms
    mostrarRuas: false,           // camada de ruas/estradas sobreposta
    opacidadeRuas: 0.5,           // opacidade da camada de ruas
    mostrarSatelite: false,       // imagem de satélite por baixo
    opacidadeSatelite: 0.4,       // opacidade do satélite
    mostrarNomesUF: false,        // siglas dos estados
    mostrarNomes: false,          // rótulos de cidades
    tamanhoNomes: 1.0,            // fator de escala dos rótulos (0.5–2.0)
    mostrarSimbolos: false,       // pontos marcadores de cidades
    mostrarCoordenadas: false,    // lat/lon ao mover o mouse
  });
  const updateVisual = useCallback((key, val) => {
    setVisual(prev => ({ ...prev, [key]: val }));
  }, []);

  // Comparação lado-a-lado
  const [comparacao, setComparacao] = useState({
    ativo: false,
    metrica: "pib_per_capita",
    ano: 2022,
  });
  const onComparacaoUpdate = useCallback((key, val) => {
    setComparacao(prev => ({ ...prev, [key]: val }));
  }, []);

  // Coordenadas do mouse
  const [mouseCoords, setMouseCoords] = useState(null);

  // Ferramentas — screenshot, report e tela cheia
  const onScreenshot = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    try {
      const canvas = map.getCanvas();
      const link = document.createElement("a");
      link.download = `brasil-em-dados-${Date.now()}.png`;
      link.href = canvas.toDataURL("image/png");
      link.click();
    } catch (_) { /* canvas tainted — CORS */ }
  }, []);

  // ── Presets de basemap para exportacao ──────────────────────────────────────
  const BASEMAP_PRESETS = {
    escuro: {
      background: "#0d0f16",
      water: "#14171f",
      landcover: "#181c28",
      labelColor: "#c0c8d8",
      labelHalo: "#0d0f16",
      roadColor: "#3a4050",
      roadMajorColor: "#505870",
      satelite: false,
    },
    claro: {
      background: "#e8e6df",
      water: "#b8d4e8",
      landcover: "#d6dbc8",
      labelColor: "#3a3a3a",
      labelHalo: "#f2f1ec",
      roadColor: "#b0a898",
      roadMajorColor: "#8a8070",
      satelite: false,
    },
    satelite: {
      background: "#0a0c14",
      water: "#0a1020",
      landcover: "#101418",
      labelColor: "#ffffff",
      labelHalo: "rgba(0,0,0,0.7)",
      roadColor: "#556070",
      roadMajorColor: "#708090",
      satelite: true,
    },
  };

  const onReport = useCallback(async (formato, opcoes = {}) => {
    const map = mapRef.current;
    if (!map) return;

    const estilo = opcoes.estiloMapa ?? "escuro";
    const preset = BASEMAP_PRESETS[estilo];

    // ── Salvar estado atual do basemap ──
    const saved = {
      background: map.getPaintProperty("background", "background-color"),
      waterColor: map.getPaintProperty("water", "fill-color"),
      waterOp: map.getPaintProperty("water", "fill-opacity"),
      landColor: map.getPaintProperty("landcover", "fill-color"),
      landOp: map.getPaintProperty("landcover", "fill-opacity"),
      labelColor: map.getPaintProperty("place-labels", "text-color"),
      labelHalo: map.getPaintProperty("place-labels", "text-halo-color"),
      labelHaloW: map.getPaintProperty("place-labels", "text-halo-width"),
      roadLabelColor: map.getPaintProperty("road-labels", "text-color"),
      roadLabelHalo: map.getPaintProperty("road-labels", "text-halo-color"),
      roadColor: map.getPaintProperty("roads", "line-color"),
      roadOp: map.getPaintProperty("roads", "line-opacity"),
      roadMajorColor: map.getPaintProperty("roads-major", "line-color"),
      roadMajorOp: map.getPaintProperty("roads-major", "line-opacity"),
      sateliteVis: map.getLayoutProperty("satelite", "visibility"),
      sateliteOp: map.getPaintProperty("satelite", "raster-opacity"),
      ufLabelsVis: map.getLayoutProperty("uf-labels", "visibility"),
      labelsVis: map.getLayoutProperty("place-labels", "visibility"),
      dotsVis: map.getLayoutProperty("place-dots", "visibility"),
      roadsVis: map.getLayoutProperty("roads", "visibility"),
      roadsMajorVis: map.getLayoutProperty("roads-major", "visibility"),
    };

    // ── Aplicar preset de exportacao ──
    if (preset) {
      map.setPaintProperty("background", "background-color", preset.background);
      map.setPaintProperty("water", "fill-color", preset.water);
      map.setPaintProperty("water", "fill-opacity", 1);
      map.setPaintProperty("landcover", "fill-color", preset.landcover);
      map.setPaintProperty("landcover", "fill-opacity", 0.6);
      map.setPaintProperty("uf-labels", "text-color", preset.labelColor);
      map.setPaintProperty("uf-labels", "text-halo-color", preset.labelHalo);
      map.setPaintProperty("place-labels", "text-color", preset.labelColor);
      map.setPaintProperty("place-labels", "text-halo-color", preset.labelHalo);
      map.setPaintProperty("place-labels", "text-halo-width", 2);
      map.setPaintProperty("road-labels", "text-color", preset.labelColor);
      map.setPaintProperty("road-labels", "text-halo-color", preset.labelHalo);
      map.setPaintProperty("roads", "line-color", preset.roadColor);
      map.setPaintProperty("roads", "line-opacity", 0.6);
      map.setPaintProperty("roads-major", "line-color", preset.roadMajorColor);
      map.setPaintProperty("roads-major", "line-opacity", 0.7);
      // Satelite: ligar/desligar
      map.setLayoutProperty("satelite", "visibility", preset.satelite ? "visible" : "none");
      if (preset.satelite) map.setPaintProperty("satelite", "raster-opacity", 0.85);
    }

    // ── Aguardar o render completo ──
    // Precisa de tempo suficiente para MapLibre aplicar paint changes e re-renderizar
    map.triggerRepaint();
    // Esperar 3 frames garantidos + timeout para tiles carregarem
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(r))));
    await new Promise(r => setTimeout(r, 300));
    // Se ainda nao esta idle, esperar o idle event
    if (!map.areTilesLoaded()) {
      await new Promise(resolve => map.once("idle", resolve));
    }
    // Mais 2 frames para o canvas estar atualizado
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));

    // ── Capturar e gerar ──
    const nivelAtualCalc = nivelForcado ?? getNivelSemantico(viewState.zoom);
    const displayRange = normBounds ?? estatisticas;
    const bounds = map.getBounds();
    // Mapear estiloMapa para tema da carta
    const tema = estilo === "claro" ? "claro" : "escuro";
    gerarReport({
      mapCanvas: map.getCanvas(),
      viewState,
      bounds: {
        north: bounds.getNorth(),
        south: bounds.getSouth(),
        east: bounds.getEast(),
        west: bounds.getWest(),
      },
      metrica: filtros.metrica,
      ano: filtros.ano,
      nivel: nivelAtualCalc,
      nivelMeta: NIVEL_METADATA[nivelAtualCalc],
      invertida: METRICAS_INVERTIDAS.has(filtros.metrica),
      range: displayRange,
      adaptativo: normBounds !== null,
      featureSelecionada,
      filtros: {
        cod_uf: filtros.cod_uf,
        cid10_capitulo: filtros.cid10_capitulo,
        sexo: filtros.sexo,
        cor_raca: filtros.cor_raca,
        faixa_etaria_min: filtros.faixa_etaria_min,
        faixa_etaria_max: filtros.faixa_etaria_max,
      },
      cid10Labels: CID10_LABELS,
      formato,
      ...opcoes,
      tema,
    });

    // ── Restaurar estado original ──
    if (preset) {
      map.setPaintProperty("background", "background-color", saved.background);
      map.setPaintProperty("water", "fill-color", saved.waterColor);
      map.setPaintProperty("water", "fill-opacity", saved.waterOp);
      map.setPaintProperty("landcover", "fill-color", saved.landColor);
      map.setPaintProperty("landcover", "fill-opacity", saved.landOp);
      map.setPaintProperty("uf-labels", "text-color", "#e2e8f0");
      map.setPaintProperty("uf-labels", "text-halo-color", "rgba(0,0,0,0.7)");
      map.setPaintProperty("place-labels", "text-color", saved.labelColor);
      map.setPaintProperty("place-labels", "text-halo-color", saved.labelHalo);
      map.setPaintProperty("place-labels", "text-halo-width", saved.labelHaloW ?? 1.5);
      map.setPaintProperty("road-labels", "text-color", saved.roadLabelColor);
      map.setPaintProperty("road-labels", "text-halo-color", saved.roadLabelHalo);
      map.setPaintProperty("roads", "line-color", saved.roadColor);
      map.setPaintProperty("roads", "line-opacity", saved.roadOp ?? 0.7);
      map.setPaintProperty("roads-major", "line-color", saved.roadMajorColor);
      map.setPaintProperty("roads-major", "line-opacity", saved.roadMajorOp ?? 0.8);
      map.setLayoutProperty("satelite", "visibility", saved.sateliteVis ?? "none");
      map.setPaintProperty("satelite", "raster-opacity", saved.sateliteOp ?? 0.4);
      map.setLayoutProperty("uf-labels", "visibility", saved.ufLabelsVis ?? "none");
      map.setLayoutProperty("place-labels", "visibility", saved.labelsVis ?? "none");
      map.setLayoutProperty("place-dots", "visibility", saved.dotsVis ?? "none");
      map.setLayoutProperty("roads", "visibility", saved.roadsVis ?? "none");
      map.setLayoutProperty("roads-major", "visibility", saved.roadsMajorVis ?? "none");
    }
  }, [viewState, nivelForcado, filtros, normBounds, estatisticas, featureSelecionada]);

  const onFullscreen = useCallback(() => {
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      document.documentElement.requestFullscreen().catch(() => {});
    }
  }, []);
  const nivelAtual = nivelForcado ?? getNivelSemantico(viewState.zoom);

  // ── Opts base para preview da carta (sem basemap switch) ──
  const getCartaBaseOpts = useCallback(() => {
    const map = mapRef.current;
    if (!map) return null;
    const b = map.getBounds();
    return {
      mapCanvas: map.getCanvas(),
      viewState,
      bounds: { north: b.getNorth(), south: b.getSouth(), east: b.getEast(), west: b.getWest() },
      metrica: filtros.metrica,
      ano: filtros.ano,
      nivel: nivelAtual,
      nivelMeta: NIVEL_METADATA[nivelAtual],
      invertida: METRICAS_INVERTIDAS.has(filtros.metrica),
      range: normBounds ?? estatisticas,
      adaptativo: normBounds !== null,
      featureSelecionada,
      filtros: {
        cod_uf: filtros.cod_uf,
        cid10_capitulo: filtros.cid10_capitulo,
        sexo: filtros.sexo,
        cor_raca: filtros.cor_raca,
        faixa_etaria_min: filtros.faixa_etaria_min,
        faixa_etaria_max: filtros.faixa_etaria_max,
      },
      cid10Labels: CID10_LABELS,
    };
  }, [viewState, nivelAtual, filtros, normBounds, estatisticas, featureSelecionada]);

  const serverParams = filtros.getServerParams();
  const tileUrlKey = JSON.stringify(serverParams);

  // Atualiza a escala de cores quando a métrica, nível ou filtro CID muda
  useEffect(() => {
    const ranges = METRICAS_RANGES[filtros.metrica];
    if (!ranges) return;
    const level = nivelAtual === "GEOLOCALIZACAO" ? "MUNICIPAL" : nivelAtual;

    // Quando CID-10 está ativo na taxa de mortalidade, usa escala específica da doença
    if (filtros.metrica === "taxa_mortalidade" && filtros.cid10_capitulo) {
      const cidRanges = CID10_RANGES[filtros.cid10_capitulo];
      if (cidRanges) {
        setEstatisticas(cidRanges[level] ?? cidRanges.ESTADUAL);
        return;
      }
    }

    const range = ranges[level] ?? ranges.ESTADUAL;
    setEstatisticas(range);
  }, [filtros.metrica, nivelAtual, filtros.cid10_capitulo]);

  // Reseta a normalização adaptativa ao trocar contexto (métrica, ano, UF, nível)
  useEffect(() => {
    setNormBounds(null);
    setNormSorted(null);
    valoresColetados.current = [];
    boundsComputados.current = false;
    clearTimeout(debounceTimer.current);
  }, [tileUrlKey, nivelAtual]);

  // Callback estável: acumula valores dos tiles e computa distribuição uma vez por contexto.
  // Produz dois artefatos:
  //   normSorted → array ordenado para normalização por quantil (cor)
  //   normBounds → P2/P98 para rótulos da legenda (referência absoluta)
  const handleTileLoad = useCallback((tile) => {
    if (boundsComputados.current) return;
    const features = tile.data;
    if (!Array.isArray(features)) return;
    for (const f of features) {
      const v = f.properties?.valor_metrica;
      if (v != null && v !== "") {
        const n = Number(v);
        if (isFinite(n)) valoresColetados.current.push(n);
      }
    }
    clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => {
      if (boundsComputados.current) return;
      const vals = valoresColetados.current;
      if (vals.length < 20) return;
      const sorted = vals.slice().sort((a, b) => a - b);
      const bounds = computePercentileBounds(vals); // P2/P98 para legenda
      if (bounds) {
        boundsComputados.current = true;
        setNormSorted(sorted); // array completo para quantile rank
        setNormBounds(bounds); // P2/P98 para rótulos min/max da legenda
      }
    }, 250);
  }, []);

  // Animação de flyTo quando flyTarget muda
  useEffect(() => {
    if (!flyTarget || !mapRef.current) return;
    mapRef.current.flyTo({
      center: [flyTarget.longitude, flyTarget.latitude],
      zoom: flyTarget.zoom ?? 4,
      pitch: flyTarget.pitch ?? 0,
      bearing: flyTarget.bearing ?? 0,
      duration: flyTarget.transitionDuration ?? 1400,
    });
    setFlyTarget(null);
  }, [flyTarget]);

  // Inicia MapLibre + MapboxOverlay (interleaved) uma única vez
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: fontesDeRotulosDemo(BASEMAP_STYLE),
      center: [INITIAL_VIEW.longitude, INITIAL_VIEW.latitude],
      zoom: INITIAL_VIEW.zoom,
      preserveDrawingBuffer: true,
    });

    const overlay = new MapboxOverlay({
      interleaved: true,
      layers: [],
      getTooltip: () => null,
    });
    map.addControl(overlay);

    mapRef.current = map;
    overlayRef.current = overlay;

    // Captura viewState do MapLibre → React
    map.on("move", () => {
      const c = map.getCenter();
      setViewState({
        longitude: c.lng,
        latitude: c.lat,
        zoom: map.getZoom(),
        pitch: map.getPitch(),
        bearing: map.getBearing(),
      });
    });
    map.on("mousemove", (e) => {
      setMouseCoords({ lat: e.lngLat.lat, lon: e.lngLat.lng });
    });

    return () => {
      map.removeControl(overlay);
      map.remove();
      mapRef.current = null;
      overlayRef.current = null;
    };
  }, []);

  // ── Visibilidade de camadas vetoriais do basemap ───────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      // Ruas
      const ruasVis = visual.mostrarRuas ? "visible" : "none";
      map.setLayoutProperty("roads", "visibility", ruasVis);
      map.setLayoutProperty("roads-major", "visibility", ruasVis);
      if (visual.mostrarRuas) {
        map.setPaintProperty("roads", "line-opacity", visual.opacidadeRuas ?? 0.7);
        map.setPaintProperty("roads-major", "line-opacity", visual.opacidadeRuas ?? 0.8);
      }
      // Nomes de estados (independente)
      map.setLayoutProperty("uf-labels", "visibility", visual.mostrarNomesUF ? "visible" : "none");
      // Nomes de cidades, símbolos e ruas
      const labelsVis = visual.mostrarNomes ? "visible" : "none";
      map.setLayoutProperty("place-labels", "visibility", labelsVis);
      map.setLayoutProperty("place-dots", "visibility", visual.mostrarNomes && visual.mostrarSimbolos ? "visible" : "none");
      map.setLayoutProperty("road-labels", "visibility", visual.mostrarRuas && visual.mostrarNomes ? "visible" : "none");
      // Escala de tamanho dos rótulos
      if (visual.mostrarNomes) {
        const f = visual.tamanhoNomes ?? 1.0;
        map.setLayoutProperty("place-labels", "text-size", [
          "interpolate", ["linear"], ["zoom"],
          3, ["case", [">=", ["get", "populacao"], 1000000], 14*f, [">=", ["get", "populacao"], 500000], 12*f, 10*f],
          6, ["case", [">=", ["get", "populacao"], 1000000], 16*f, [">=", ["get", "populacao"], 200000], 14*f, [">=", ["get", "populacao"], 50000], 12*f, 11*f],
          10, ["case", [">=", ["get", "populacao"], 500000], 18*f, [">=", ["get", "populacao"], 100000], 15*f, 13*f],
          14, 14*f,
        ]);
      }
      // Satélite
      map.setLayoutProperty("satelite", "visibility", visual.mostrarSatelite ? "visible" : "none");
      if (visual.mostrarSatelite) {
        map.setPaintProperty("satelite", "raster-opacity", visual.opacidadeSatelite ?? 0.4);
      }
      // Opacidade do basemap (água, terreno)
      const baseOp = visual.opacidadeBasemap ?? 0.3;
      map.setPaintProperty("water", "fill-opacity", baseOp);
      map.setPaintProperty("landcover", "fill-opacity", baseOp * 0.3);
    };
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [visual.mostrarRuas, visual.opacidadeRuas, visual.mostrarNomesUF, visual.mostrarNomes, visual.tamanhoNomes, visual.mostrarSimbolos, visual.mostrarSatelite, visual.opacidadeSatelite, visual.opacidadeBasemap]);

  // ── Deck.gl de comparação (lado direito do split) ────────────────────────────
  const compareCanvasRef = useCallback((el) => {
    if (el && !deckCompareRef.current) {
      deckCompareRef.current = new Deck({
        canvas: el,
        width: "100%",
        height: "100%",
        initialViewState: viewState,
        controller: false,
      });
    }
  }, []);

  // Cleanup do deck de comparação quando desativado
  useEffect(() => {
    if (!comparacao.ativo && deckCompareRef.current) {
      deckCompareRef.current.finalize();
      deckCompareRef.current = null;
    }
  }, [comparacao.ativo]);

  // Sincroniza viewport do deck de comparação
  useEffect(() => {
    if (deckCompareRef.current) {
      deckCompareRef.current.setProps({ initialViewState: viewState });
    }
  }, [viewState]);

  // Camadas do deck de comparação
  useEffect(() => {
    if (!deckCompareRef.current || !comparacao.ativo) return;

    const compParams = { ...serverParams, metrica: comparacao.metrica, ano: comparacao.ano };
    const compTileUrl = getTileUrl(nivelAtual === "GEOLOCALIZACAO" ? "MUNICIPAL" : nivelAtual, compParams);
    const compInvertida = METRICAS_INVERTIDAS.has(comparacao.metrica);
    const compRange = METRICAS_RANGES[comparacao.metrica]?.[nivelAtual === "GEOLOCALIZACAO" ? "MUNICIPAL" : nivelAtual] ?? { min: 0, max: 100 };

    const compGetColor = (f) => {
      const raw = f.properties?.valor_metrica;
      if (raw == null || raw === "") return [55, 60, 75, 160];
      const val = Number(raw);
      if (!isFinite(val)) return [55, 60, 75, 160];
      return getCorCoroplética(normalizarValor(val, compRange.min, compRange.max), 220, compInvertida);
    };

    const layers = [];
    if (nivelAtual === "NACIONAL") {
      layers.push(new MVTLayer({
        id: "compare-ufs", data: compTileUrl, pickable: true, autoHighlight: true,
        highlightColor: [255, 255, 255, 80],
        getFillColor: compGetColor,
        getLineColor: [60, 60, 80, 200], getLineWidth: 1, lineWidthMinPixels: 0.8,
        updateTriggers: { getFillColor: [comparacao.metrica, comparacao.ano] },
      }));
    } else if (nivelAtual === "ESTADUAL") {
      layers.push(new MVTLayer({
        id: "compare-municipios", data: compTileUrl, pickable: true, autoHighlight: true,
        highlightColor: [255, 255, 255, 60],
        getFillColor: compGetColor,
        getLineColor: [20, 20, 20, 150], getLineWidth: 0.5, lineWidthMinPixels: 0.3,
        updateTriggers: { getFillColor: [comparacao.metrica, comparacao.ano] },
      }));
    } else {
      layers.push(new MVTLayer({
        id: "compare-setores", data: compTileUrl, pickable: true, autoHighlight: true,
        highlightColor: [255, 255, 255, 60],
        getFillColor: compGetColor,
        getLineColor: [20, 20, 20, 120], getLineWidth: 0.3, lineWidthMinPixels: 0.2,
        updateTriggers: { getFillColor: [comparacao.metrica, comparacao.ano] },
      }));
    }

    deckCompareRef.current.setProps({
      layers,
      getTooltip: makeTooltip(comparacao.metrica, null),
    });
  }, [comparacao, nivelAtual, serverParams]);

  // Atualiza camadas quando estado muda
  useEffect(() => {
    if (!overlayRef.current) return;

    const layers = [];

    // Opacidade base: fade por zoom × opacidade do overlay (controle visual)
    const op = (zIn, zOut) =>
      (nivelForcado ? 1 : calcularOpacidade(viewState.zoom, zIn, zOut)) * visual.opacidadeOverlay;

    // Cores de borda controladas pelo painel visual
    const munLineColor   = visual.bordurasMunicipios ? [20, 20, 20, 150]    : [0, 0, 0, 0];
    const munLineWidth   = visual.bordurasMunicipios ? 0.5  : 0;
    const munLineMinPx   = visual.bordurasMunicipios ? 0.3  : 0;
    const setorLineColor = visual.bordurasMunicipios ? [20, 20, 20, 120]    : [0, 0, 0, 0];
    const setorLineWidth = visual.bordurasMunicipios ? 0.3  : 0;
    const setorLineMinPx = visual.bordurasMunicipios ? 0.2  : 0;
    const ufLineColor    = visual.bordurasEstados    ? [80, 90, 120, 220]   : [0, 0, 0, 0];
    const ufLineWidth    = visual.bordurasEstados    ? 2    : 0;
    const ufLineMinPx    = visual.bordurasEstados    ? 1.5  : 0;

    // Determina se a escala deve ser invertida (alto=bom → verde no topo)
    const metricaInvertida = METRICAS_INVERTIDAS.has(filtros.metrica);

    // Normaliza um valor para t ∈ [0,1]:
    //   - Se normSorted disponível: usa rank percentual (quantil) — distribui bem mesmo com skew
    //   - Fallback: normalização linear com P2/P98 ou METRICAS_RANGES
    const activeRange = normBounds ?? estatisticas;
    const resolverT = (val) => {
      if (normSorted) {
        const t = quantileNormalizar(val, normSorted);
        return t !== null ? t : 0;
      }
      return normalizarValor(val, activeRange.min, activeRange.max);
    };

    // ID unico da feature selecionada para highlight
    const selId = featureSelecionada?.properties?.cod_ibge_7
      ?? featureSelecionada?.properties?.cod_uf
      ?? featureSelecionada?.properties?.cod_setor
      ?? null;

    const isSelected = (f) => {
      if (!selId) return false;
      const p = f.properties;
      return (p?.cod_ibge_7 === selId || p?.cod_uf === selId || p?.cod_setor === selId);
    };

    // Cor coroplética compartilhada — com highlight de selecao
    const getChoroplethColor = (f) => {
      const raw = f.properties?.valor_metrica;
      if (raw == null || raw === "") return [55, 60, 75, 160];
      const val = Number(raw);
      if (!isFinite(val)) return [55, 60, 75, 160];
      const base = getCorCoroplética(resolverT(val), 220, metricaInvertida);
      if (isSelected(f)) return [base[0], base[1], base[2], 255];
      return base;
    };

    // Borda de selecao: feature selecionada recebe borda branca brilhante
    const getSelectionLineColor = (baseColor) => (f) =>
      isSelected(f) ? [255, 255, 255, 240] : baseColor;
    const getSelectionLineWidth = (baseWidth) => (f) =>
      isSelected(f) ? Math.max(baseWidth * 3, 3) : baseWidth;

    // beforeId: "roads" → deck.gl renderiza ABAIXO das camadas vetoriais de ruas/labels
    const BEFORE_ID = "roads";

    // ── Camada de dados ativa (choropleth) ──────────────────────────────────────
    if (nivelAtual === "NACIONAL") {
      layers.push(new MVTLayer({
        id: "ufs-layer",
        beforeId: BEFORE_ID,
        data: getTileUrl("NACIONAL", serverParams),
        opacity: op(0, 6),
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 80],
        onTileLoad: handleTileLoad,
        getFillColor: getChoroplethColor,
        getLineColor: getSelectionLineColor(ufLineColor),
        getLineWidth: getSelectionLineWidth(ufLineWidth),
        lineWidthMinPixels: ufLineMinPx,
        onClick: ({ object }) => object && setFeatureSelecionada(object),
        updateTriggers: {
          getFillColor: [normSorted, activeRange, tileUrlKey, metricaInvertida, selId],
          getLineColor: [visual.bordurasEstados, selId],
          getLineWidth: [selId],
        },
      }));
    }

    if (nivelAtual === "ESTADUAL") {
      if (filtros.cod_uf) {
        layers.push(new MVTLayer({
          id: "ufs-dim-bg",
          beforeId: BEFORE_ID,
          data: `${import.meta.env.VITE_MARTIN_URL}/tiles_ufs/{z}/{x}/{y}`,
          opacity: 1,
          pickable: false,
          getFillColor: [60, 70, 95, 160],
          getLineColor: [0, 0, 0, 0],
          getLineWidth: 0,
        }));
      }

      layers.push(new MVTLayer({
        id: "municipios-layer",
        beforeId: BEFORE_ID,
        data: getTileUrl("ESTADUAL", serverParams),
        opacity: op(5, 12),
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 60],
        onTileLoad: handleTileLoad,
        getFillColor: getChoroplethColor,
        getLineColor: getSelectionLineColor(munLineColor),
        getLineWidth: getSelectionLineWidth(munLineWidth),
        lineWidthMinPixels: munLineMinPx,
        onClick: ({ object }) => object && setFeatureSelecionada(object),
        updateTriggers: {
          getFillColor: [normSorted, activeRange, tileUrlKey, metricaInvertida, selId],
          getLineColor: [visual.bordurasMunicipios, selId],
          getLineWidth: [selId],
        },
      }));
    }

    if (nivelAtual === "MUNICIPAL") {
      layers.push(new MVTLayer({
        id: "setores-layer",
        beforeId: BEFORE_ID,
        data: getTileUrl("MUNICIPAL", serverParams),
        minZoom: 0,
        opacity: op(0, 15),
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 60],
        onTileLoad: handleTileLoad,
        getFillColor: getChoroplethColor,
        getLineColor: getSelectionLineColor(setorLineColor),
        getLineWidth: getSelectionLineWidth(setorLineWidth),
        lineWidthMinPixels: setorLineMinPx,
        pointRadiusMinPixels: 2,
        onClick: ({ object }) => object && setFeatureSelecionada(object),
        updateTriggers: {
          getFillColor: [normSorted, activeRange, tileUrlKey, metricaInvertida, selId],
          getLineColor: [visual.bordurasMunicipios, selId],
          getLineWidth: [selId],
        },
      }));
    }

    if (nivelAtual === "GEOLOCALIZACAO") {
      layers.push(new MVTLayer({
        id: "cnefe-layer",
        beforeId: BEFORE_ID,
        data: getTileUrl("GEOLOCALIZACAO", serverParams),
        minZoom: 0,
        opacity: op(0, 22),
        pickable: false,
        getPointRadius: 3,
        pointRadiusMinPixels: 2,
        getFillColor: [255, 200, 50, 180],
      }));
    }

    // ── Bordas persistentes (sobrepostas ao choropleth em qualquer nível) ─────
    // Bordas de UF: visíveis em todos os níveis (não apenas NACIONAL)
    if (visual.bordurasEstados && nivelAtual !== "NACIONAL") {
      layers.push(new MVTLayer({
        id: "ufs-borders-overlay",
        beforeId: BEFORE_ID,
        data: `${import.meta.env.VITE_MARTIN_URL}/tiles_ufs/{z}/{x}/{y}`,
        pickable: false,
        getFillColor: [0, 0, 0, 0],
        getLineColor: ufLineColor,
        getLineWidth: ufLineWidth,
        lineWidthMinPixels: ufLineMinPx,
        updateTriggers: { getLineColor: [visual.bordurasEstados] },
      }));
    }

    // Bordas de municípios: visíveis em MUNICIPAL, GEOLOCALIZACAO (não apenas ESTADUAL)
    if (visual.bordurasMunicipios && (nivelAtual === "MUNICIPAL" || nivelAtual === "GEOLOCALIZACAO")) {
      layers.push(new MVTLayer({
        id: "municipios-borders-overlay",
        beforeId: BEFORE_ID,
        data: `${import.meta.env.VITE_MARTIN_URL}/tiles_municipios/{z}/{x}/{y}`,
        pickable: false,
        getFillColor: [0, 0, 0, 0],
        getLineColor: munLineColor,
        getLineWidth: munLineWidth,
        lineWidthMinPixels: munLineMinPx,
        updateTriggers: { getLineColor: [visual.bordurasMunicipios] },
      }));
    }

    overlayRef.current.setProps({
      layers,
      getTooltip: makeTooltip(filtros.metrica, filtros.cid10_capitulo),
    });
  }, [nivelAtual, nivelForcado, viewState.zoom, tileUrlKey, estatisticas, filtros, normBounds, normSorted, visual, handleTileLoad, comparacao.ativo, featureSelecionada]);

  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }}>
      {DEMO && (
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, zIndex: 20,
                      background: "rgba(13,15,22,0.88)", color: "#cbd5e0", font: "11px/1.6 system-ui, sans-serif",
                      padding: "1px 12px", textAlign: "center", pointerEvents: "none",
                      whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          Static demo · states and municipalities, all 94 indicators and years, default filters ·
          census tracts, addresses and cause/sex/race/age filters need the full stack
        </div>
      )}
      {/* Mapa integrado: MapLibre + deck.gl (interleaved) */}
      <div ref={mapContainerRef} style={{ position: "absolute", inset: 0 }} />

      {/* Canvas de comparação (lado direito) */}
      {comparacao.ativo && (
        <canvas
          ref={compareCanvasRef}
          id="deck-compare-canvas"
          style={{
            position: "absolute", inset: 0, pointerEvents: "all",
            clipPath: "inset(0 0 0 50%)",
          }}
        />
      )}

      {/* Divisor vertical do split */}
      {comparacao.ativo && (
        <div style={{
          position: "absolute", top: 0, bottom: 0, left: "50%",
          width: 2, background: "#e2e8f0", zIndex: 20,
          pointerEvents: "none", boxShadow: "0 0 8px rgba(0,0,0,0.5)",
        }}>
          <div style={{
            position: "absolute", top: 12, left: "50%", transform: "translateX(-50%)",
            background: "rgba(13,15,22,0.9)", border: "1px solid #4a5568",
            borderRadius: 6, padding: "4px 10px", fontSize: 10, color: "#a0aec0",
            whiteSpace: "nowrap",
          }}>
            {METRICA_LABEL_CURTO[filtros.metrica] ?? filtros.metrica}
            {" vs "}
            {METRICA_LABEL_CURTO[comparacao.metrica] ?? comparacao.metrica}
          </div>
        </div>
      )}

      {/* Barra de ferramentas superior — busca + navegação */}
      <div style={{
        position: "absolute",
        top: 16,
        left: "50%",
        transform: "translateX(-50%)",
        display: "flex",
        alignItems: "center",
        gap: 8,
        zIndex: 10,
      }}>
        <BuscaMunicipio onFlyTo={setFlyTarget} />
        <button
          title="Centralizar o Brasil"
          onClick={() => setFlyTarget({ ...INITIAL_VIEW })}
          style={{
            background: "rgba(15,17,23,0.90)",
            border: "1px solid #2d3748",
            borderRadius: 8,
            color: "#a0aec0",
            cursor: "pointer",
            fontSize: 16,
            padding: "6px 10px",
            lineHeight: 1,
            transition: "border-color 0.15s, color 0.15s",
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = "#4299e1"; e.currentTarget.style.color = "#e2e8f0"; }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = "#2d3748"; e.currentTarget.style.color = "#a0aec0"; }}
        >🏠</button>
      </div>

      {/* Painel visual — controles de renderização */}
      <PainelVisual
        visual={visual}
        onUpdate={updateVisual}
        onFlyTo={(destino) => {
          if (destino === "brasil") {
            setFlyTarget({ ...INITIAL_VIEW, transitionDuration: 1200 });
          } else if (destino === "sul_america") {
            setFlyTarget({ latitude: -17, longitude: -57, zoom: 2.5, pitch: 0, bearing: 0, transitionDuration: 1500 });
          }
        }}
        comparacao={comparacao}
        onComparacaoUpdate={onComparacaoUpdate}
        onScreenshot={onScreenshot}
        onFullscreen={onFullscreen}
        anosDisponiveis={filtros.anosDisponiveis}
      />

      {/* Painel de exportacao dedicado */}
      <PainelExportar
        onReport={onReport}
        getCartaBaseOpts={getCartaBaseOpts}
        gerarPreview={gerarPreviewCarta}
      />

      {/* Painel de controles */}
      <PainelControles
        nivelAtual={nivelAtual}
        nivelForcado={nivelForcado}
        zoom={viewState.zoom}
        filtros={filtros}
        onMetricaChange={filtros.setMetrica}
        onUFChange={escolherUF}
        onFaixaEtariaChange={filtros.setFaixaEtaria}
        onCorRacaChange={filtros.setCorRaca}
        onSexoChange={filtros.setSexo}
        onEspecieChange={filtros.setEspecie}
        onNivelChange={setNivelForcado}
      />

      {/* Legenda de cores — usa P2/P98 adaptativos quando disponível */}
      {(() => {
        const displayRange = normBounds ?? estatisticas;
        return (
          <Legenda
            metrica={filtros.metrica}
            min={displayRange.min}
            max={displayRange.max}
            semDados={METRICAS_SEM_DADOS.includes(filtros.metrica)}
            invertida={METRICAS_INVERTIDAS.has(filtros.metrica)}
            adaptativo={normBounds !== null}
          />
        );
      })()}

      {/* Painel de detalhes */}
      {featureSelecionada && (
        <PainelDetalhes
          feature={featureSelecionada}
          nivel={nivelAtual}
          filtros={serverParams}
          onClose={() => setFeatureSelecionada(null)}
        />
      )}

      {/* Coordenadas do mouse */}
      {visual.mostrarCoordenadas && mouseCoords && (
        <div style={{
          position: "absolute", bottom: 56, right: 16, zIndex: 10,
          background: "rgba(13,15,22,0.88)", border: "1px solid #2d3748",
          borderRadius: 6, padding: "4px 10px", fontSize: 11,
          fontFamily: "monospace", color: "#a0aec0", pointerEvents: "none",
          backdropFilter: "blur(8px)",
        }}>
          {mouseCoords.lat.toFixed(5)}, {mouseCoords.lon.toFixed(5)}
        </div>
      )}

      {/* Indicador de nível semântico */}
      <div style={{
        position: "absolute", bottom: 24, left: "50%", transform: "translateX(-50%)",
        background: "rgba(15,17,23,0.85)", border: "1px solid #4a5568",
        borderRadius: 24, padding: "6px 16px", fontSize: 13,
        pointerEvents: "none", backdropFilter: "blur(8px)", color: "#e2e8f0",
      }}>
        {NIVEL_METADATA[nivelAtual].icone} {NIVEL_METADATA[nivelAtual].label}
        {/* no celular a descrição quebrava em 3 linhas por cima da legenda */}
        {window.innerWidth > 640 && <>{" — "}{NIVEL_METADATA[nivelAtual].descricao}</>}
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
