/**
 * main.jsx — Painel Geoespacial do Brasil
 *
 * Deck.gl v9 + MapLibre GL JS — arquitetura dual:
 * - MapLibre: basemap contextual
 * - Deck.gl: camadas temáticas analíticas sobre o basemap
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import maplibregl from "maplibre-gl";
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
import { PainelControles } from "./components/PainelControles.jsx";
import { PainelDetalhes } from "./components/PainelDetalhes.jsx";
import { Legenda } from "./components/Legenda.jsx";

// Registra protocolo PMTiles no MapLibre
const pmtilesProtocol = new Protocol();
maplibregl.addProtocol("pmtiles", pmtilesProtocol.tile);

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

// Busca os anos disponíveis no banco via API e atualiza o store
function useAnosDisponiveis() {
  const setAnosDisponiveis = useFiltrosStore(s => s.setAnosDisponiveis);
  useEffect(() => {
    const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8001";
    fetch(`${apiUrl}/api/anos`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setAnosDisponiveis(data); })
      .catch(() => {}); // mantém o fallback em caso de erro
  }, [setAnosDisponiveis]);
}

// Retorna uma função getTooltip que mostra o indicador atualmente selecionado.
// Recebe metrica e cid10 como closure para exibir label correto.
function makeTooltip(metrica, cid10) {
  const LABEL = {
    taxa_mortalidade:            cid10 ? (CID10_LABELS[cid10] ?? `Mortalidade CID-${cid10}`) : "Mortalidade",
    taxa_homicidio:              "Homicídio",
    mortalidade_infantil:        "Mort. infantil",
    pib_per_capita:              "PIB per capita",
    receita_per_capita:          "Receita per capita",
    despesa_saude_per_capita:    "Gasto em saúde",
    despesa_educacao_per_capita: "Gasto em educação",
    densidade_pop:               "Densidade demográfica",
    acesso_agua:                 "Acesso à água",
    acesso_esgoto:               "Acesso ao esgoto",
    coleta_lixo:                 "Coleta de lixo",
    taxa_natalidade:             "Taxa de natalidade",
    leitos_sus_por_1k:           "Leitos SUS",
    medicos_por_10k:             "Médicos",
    ideb_anos_iniciais:          "IDEB anos iniciais",
    ideb_anos_finais:            "IDEB anos finais",
    taxa_alfabetizacao:          "Taxa de alfabetização",
    taxa_envelhecimento:         "Índice de envelhecimento",
    razao_sexo:                  "Razão de sexo",
    media_moradores:             "Média de moradores",
    domicilios_internet:         "Domicílios c/ internet",
    pop_favelas_pct:             "Pop. em favelas",
    renda_domiciliar_per_capita: "Renda dom. per capita",
    renda_domiciliar_mediana_pc: "Renda dom. mediana pc",
    renda_media_trabalho:        "Renda média trabalho",
    renda_mediana_trabalho:      "Renda mediana trabalho",
    media_anos_estudo:           "Média anos de estudo",
    pct_superior_completo:       "Superior completo",
    taxa_deficiencia:            "Taxa de deficiência",
    taxa_ocupacao:               "Nível de ocupação",
    idade_mediana:               "Idade mediana",
    pct_pib_agropecuaria:        "Agropecuária / PIB",
    pct_pib_industria:           "Indústria / PIB",
    pct_pib_servicos:            "Serviços / PIB",
    vbp_agricola_per_capita:     "VBP agrícola per capita",
    vbp_pecuaria_per_capita:     "VBP pecuário per capita",
    divida_rcl:                  "Dívida / RCL",
    despesa_pessoal_rcl:         "Pessoal / RCL",
    pct_indigena:                "Pop. indígena",
    pct_quilombola:              "Pop. quilombola",
    pct_agrofamiliar:            "Agric. familiar",
    pct_mecanizado:              "Com tratores",
    pct_financiamento:           "Com financiamento",
    empresas_por_1k:             "Empresas / 1k hab.",
    taxa_migracao:               "Imigração inter-mun.",
    taxa_escolarizacao_1517:     "Escolarização 15-17",
  };

  const METRICAS_REAIS = new Set([
    "pib_per_capita", "receita_per_capita",
    "despesa_saude_per_capita", "despesa_educacao_per_capita",
    "vbp_agricola_per_capita", "vbp_pecuaria_per_capita",
    "renda_media_trabalho", "renda_mediana_trabalho",
    "renda_domiciliar_per_capita", "renda_domiciliar_mediana_pc",
  ]);

  const METRICAS_PERCENT = new Set([
    "acesso_agua", "acesso_esgoto", "coleta_lixo",
    "taxa_alfabetizacao", "domicilios_internet", "pop_favelas_pct",
    "divida_rcl", "despesa_pessoal_rcl",
    "pct_superior_completo", "taxa_deficiencia",
    "taxa_ocupacao",
    "pct_pib_agropecuaria", "pct_pib_industria", "pct_pib_servicos",
    "pct_indigena", "pct_quilombola", "pct_agrofamiliar",
    "pct_mecanizado", "pct_financiamento",
    "taxa_migracao", "taxa_escolarizacao_1517",
  ]);

  return ({ object }) => {
    if (!object?.properties) return null;
    const p = object.properties;
    const nome = p.nome_municipio || p.nome || p.sigla || `Setor ${p.cod_setor}`;
    const label = LABEL[metrica] || metrica;
    const valor = p.valor_metrica;

    let formatado;
    if (valor == null || valor === "") {
      formatado = "<i style='color:#718096'>sem dados</i>";
    } else {
      const n = Number(valor);
      if (!isFinite(n)) {
        formatado = "<i style='color:#718096'>sem dados</i>";
      } else if (METRICAS_REAIS.has(metrica)) {
        formatado = `<b>R$\u00a0${n.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}</b>`;
      } else if (metrica === "densidade_pop") {
        formatado = `<b>${n.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}</b> hab/km²`;
      } else if (METRICAS_PERCENT.has(metrica)) {
        formatado = `<b>${n.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}</b>%`;
      } else if (metrica === "ideb_anos_iniciais" || metrica === "ideb_anos_finais") {
        formatado = `<b>${n.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</b>`;
      } else if (metrica === "leitos_sus_por_1k") {
        formatado = `<b>${n.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}</b>/1k hab.`;
      } else if (metrica === "medicos_por_10k") {
        formatado = `<b>${n.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}</b>/10k hab.`;
      } else if (metrica === "mortalidade_infantil") {
        formatado = `<b>${n.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}</b>/1k nasc.`;
      } else if (metrica === "taxa_natalidade") {
        formatado = `<b>${n.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}</b>/1k hab.`;
      } else if (metrica === "razao_sexo") {
        formatado = `<b>${n.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}</b> h/100 mul.`;
      } else if (metrica === "media_moradores") {
        formatado = `<b>${n.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 2 })}</b> mor./dom.`;
      } else if (metrica === "taxa_envelhecimento") {
        formatado = `<b>${n.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}</b>`;
      } else if (metrica === "media_anos_estudo") {
        formatado = `<b>${n.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</b> anos`;
      } else if (metrica === "idade_mediana") {
        formatado = `<b>${n.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}</b> anos`;
      } else {
        formatado = `<b>${n.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}</b>/100k`;
      }
    }

    const pop = p.populacao_2022 ?? p.populacao_total;
    const popLine = pop != null
      ? `<br/>Pop.: <b>${Number(pop).toLocaleString("pt-BR")}</b>`
      : "";

    return {
      html: `<strong>${nome}</strong><br/>${label}: ${formatado}${popLine}`,
      style: {
        backgroundColor: "#1a202c",
        color: "#e2e8f0",
        border: "1px solid #4a5568",
        borderRadius: "6px",
        padding: "8px 12px",
        fontSize: "12px",
        maxWidth: "240px",
      },
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

function getCorCoroplética(valorNormalizado, opacity = 220) {
  const t = Math.max(0, Math.min(1, valorNormalizado));
  const r = Math.round(t < 0.5 ? t * 2 * 255 : 255);
  const g = Math.round(t < 0.5 ? 255 : (1 - t) * 2 * 255);
  const b = Math.round(t < 0.5 ? 255 - t * 2 * 255 : 0);
  return [r, g, b, opacity];
}

function normalizarValor(v, min, max) {
  if (max === min) return 0.5;
  const n = typeof v === "number" ? v : Number(v);
  if (!isFinite(n)) return 0;
  return Math.max(0, Math.min(1, (n - min) / (max - min)));
}

// ─────────────────────────────────────────────────────────────────────────────
export default function App() {
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);
  const deckRef = useRef(null);

  const [viewState, setViewState] = useState(INITIAL_VIEW);
  const [featureSelecionada, setFeatureSelecionada] = useState(null);
  const [estatisticas, setEstatisticas] = useState({ min: 0, max: 100 });

  const filtros = useFiltrosStore();
  useAnosDisponiveis(); // busca anos disponíveis do banco na inicialização

  // null = automático (segue o zoom); string = nível forçado pelo painel
  const [nivelForcado, setNivelForcado] = useState(null);
  const nivelAtual = nivelForcado ?? getNivelSemantico(viewState.zoom);

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

  // Inicia MapLibre + Deck.gl uma única vez
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: {
        version: 8,
        sources: {},
        layers: [
          {
            id: "background",
            type: "background",
            paint: { "background-color": "#1a1f2e" },
          },
        ],
      },
      center: [INITIAL_VIEW.longitude, INITIAL_VIEW.latitude],
      zoom: INITIAL_VIEW.zoom,
      interactive: false, // Deck.gl controla a interação
    });

    // Adiciona basemap OSM quando zoom >= 9 (nível municipal)
    map.on("load", () => {
      map.addSource("osm", {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        attribution: "© OpenStreetMap",
      });
      map.addLayer({
        id: "osm-tiles",
        type: "raster",
        source: "osm",
        paint: {
          "raster-opacity": [
            "interpolate", ["linear"], ["zoom"],
            8, 0, 10, 0.35, 14, 0.6,
          ],
        },
      });
    });

    mapRef.current = map;

    const deck = new Deck({
      canvas: "deck-canvas",
      width: "100%",
      height: "100%",
      initialViewState: INITIAL_VIEW,
      controller: true,

      onViewStateChange: ({ viewState: vs }) => {
        setViewState(vs);
        map.jumpTo({
          center: [vs.longitude, vs.latitude],
          zoom: vs.zoom,
          bearing: vs.bearing,
          pitch: vs.pitch,
        });
      },
      // getTooltip é atualizado via setProps no efeito de camadas
      // para sempre refletir o indicador e filtros atuais.
    });

    deckRef.current = deck;

    return () => {
      deck.finalize();
      map.remove();
      mapRef.current = null;
      deckRef.current = null;
    };
  }, []);

  // Atualiza camadas quando estado muda
  useEffect(() => {
    if (!deckRef.current) return;

    const layers = [];

    // Quando o nível é forçado manualmente, usa opacidade total (ignora fade por zoom)
    const op = (zIn, zOut) => nivelForcado ? 1 : calcularOpacidade(viewState.zoom, zIn, zOut);

    // Cor coroplética compartilhada por todas as camadas de fundo
    const getChoroplethColor = (f) => {
      const raw = f.properties?.valor_metrica;
      if (raw == null || raw === "") return [55, 60, 75, 160];
      const val = Number(raw);
      if (!isFinite(val)) return [55, 60, 75, 160];
      return getCorCoroplética(normalizarValor(val, estatisticas.min, estatisticas.max));
    };


    if (nivelAtual === "NACIONAL") {
      layers.push(new MVTLayer({
        id: "ufs-layer",
        data: getTileUrl("NACIONAL", serverParams),
        opacity: op(0, 6),
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 80],
        getFillColor: (f) => {
          const raw = f.properties?.valor_metrica;
          if (raw == null || raw === "") return [55, 60, 75, 160]; // cinza = sem dados
          const val = Number(raw);
          if (!isFinite(val)) return [55, 60, 75, 160];
          return getCorCoroplética(normalizarValor(val, estatisticas.min, estatisticas.max));
        },
        getLineColor: [60, 60, 80, 200],
        getLineWidth: 1,
        lineWidthMinPixels: 0.8,
        onClick: ({ object }) => object && setFeatureSelecionada(object),
        updateTriggers: { getFillColor: [estatisticas, tileUrlKey] },
      }));
    }

    if (nivelAtual === "ESTADUAL") {
      // When a UF is selected, show all UFs dimmed as geographic reference
      if (filtros.cod_uf) {
        layers.push(new MVTLayer({
          id: "ufs-dim-bg",
          data: `${import.meta.env.VITE_MARTIN_URL}/tiles_ufs/{z}/{x}/{y}`,
          opacity: 1,
          pickable: false,
          getFillColor: [60, 70, 95, 160],
          getLineColor: [100, 115, 145, 180],
          getLineWidth: 1,
          lineWidthMinPixels: 0.8,
        }));
      }

      layers.push(new MVTLayer({
        id: "municipios-layer",
        data: getTileUrl("ESTADUAL", serverParams),
        opacity: op(5, 12),
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 60],
        getFillColor: (f) => {
          const raw = f.properties?.valor_metrica;
          if (raw == null || raw === "") return [55, 60, 75, 160]; // cinza = sem dados
          const val = Number(raw);
          if (!isFinite(val)) return [55, 60, 75, 160];
          return getCorCoroplética(normalizarValor(val, estatisticas.min, estatisticas.max));
        },
        getLineColor: [20, 20, 20, 150],
        getLineWidth: 0.5,
        lineWidthMinPixels: 0.3,
        onClick: ({ object }) => object && setFeatureSelecionada(object),
        updateTriggers: { getFillColor: [estatisticas, tileUrlKey] },
      }));
    }

    if (nivelAtual === "MUNICIPAL") {
      layers.push(new MVTLayer({
        id: "setores-layer",
        data: getTileUrl("MUNICIPAL", serverParams),
        minZoom: 0,
        opacity: op(0, 15),
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 60],
        getFillColor: getChoroplethColor,
        getLineColor: [20, 20, 20, 120],
        getLineWidth: 0.3,
        lineWidthMinPixels: 0.2,
        pointRadiusMinPixels: 2,
        onClick: ({ object }) => object && setFeatureSelecionada(object),
        updateTriggers: { getFillColor: [estatisticas, tileUrlKey] },
      }));
    }

    if (nivelAtual === "GEOLOCALIZACAO") {
      layers.push(new MVTLayer({
        id: "cnefe-layer",
        data: getTileUrl("GEOLOCALIZACAO", serverParams),
        minZoom: 0,
        opacity: op(0, 22),
        pickable: false,
        getPointRadius: 3,
        pointRadiusMinPixels: 2,
        getFillColor: [255, 200, 50, 180],
      }));
    }

    deckRef.current.setProps({
      layers,
      getTooltip: makeTooltip(filtros.metrica, filtros.cid10_capitulo),
    });
  }, [nivelAtual, nivelForcado, viewState.zoom, tileUrlKey, estatisticas, filtros]);

  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }}>
      {/* Mapa base MapLibre */}
      <div ref={mapContainerRef} style={{ position: "absolute", inset: 0 }} />

      {/* Canvas Deck.gl sobreposto */}
      <canvas
        id="deck-canvas"
        style={{ position: "absolute", inset: 0, pointerEvents: "all" }}
      />

      {/* Painel de controles */}
      <PainelControles
        nivelAtual={nivelAtual}
        nivelForcado={nivelForcado}
        zoom={viewState.zoom}
        filtros={filtros}
        onMetricaChange={filtros.setMetrica}
        onUFChange={filtros.setUF}
        onFaixaEtariaChange={filtros.setFaixaEtaria}
        onCorRacaChange={filtros.setCorRaca}
        onSexoChange={filtros.setSexo}
        onEspecieChange={filtros.setEspecie}
        onNivelChange={setNivelForcado}
      />

      {/* Legenda de cores */}
      <Legenda
        metrica={filtros.metrica}
        min={estatisticas.min}
        max={estatisticas.max}
        semDados={METRICAS_SEM_DADOS.includes(filtros.metrica)}
      />

      {/* Painel de detalhes */}
      {featureSelecionada && (
        <PainelDetalhes
          feature={featureSelecionada}
          nivel={nivelAtual}
          filtros={serverParams}
          onClose={() => setFeatureSelecionada(null)}
        />
      )}

      {/* Indicador de nível semântico */}
      <div style={{
        position: "absolute", bottom: 24, left: "50%", transform: "translateX(-50%)",
        background: "rgba(15,17,23,0.85)", border: "1px solid #4a5568",
        borderRadius: 24, padding: "6px 16px", fontSize: 13,
        pointerEvents: "none", backdropFilter: "blur(8px)", color: "#e2e8f0",
      }}>
        {NIVEL_METADATA[nivelAtual].icone} {NIVEL_METADATA[nivelAtual].label}
        {" — "}{NIVEL_METADATA[nivelAtual].descricao}
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
