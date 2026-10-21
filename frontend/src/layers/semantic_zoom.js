import { DEMO } from "../demo.js";
/**
 * semantic_zoom.js
 * Define os limites de zoom e a lógica de transição semântica entre os
 * 4 níveis do painel. Cada nível usa fontes de dados e tipos de camada
 * completamente diferentes — não é apenas zoom geométrico.
 */

export const ZOOM_LEVELS = {
  NACIONAL:    { min: 0,  max: 4  },  // 27 UFs, coroplético
  ESTADUAL:    { min: 5,  max: 8  },  // 5.570 municípios
  MUNICIPAL:   { min: 9,  max: 12 },  // setores censitários
  GEOLOCALIZACAO: { min: 13, max: 22 }, // pontos CNEFE
};

/**
 * Retorna o nível semântico atual com base no zoom do mapa.
 * @param {number} zoom - zoom atual do MapLibre
 * @returns {'NACIONAL'|'ESTADUAL'|'MUNICIPAL'|'GEOLOCALIZACAO'}
 */
export function getNivelSemantico(zoom) {
  if (zoom <= ZOOM_LEVELS.NACIONAL.max)       return "NACIONAL";
  if (zoom <= ZOOM_LEVELS.ESTADUAL.max || DEMO) return "ESTADUAL";   // a demo estática não tem setores nem CNEFE
  if (zoom <= ZOOM_LEVELS.MUNICIPAL.max)      return "MUNICIPAL";
  return "GEOLOCALIZACAO";
}

/**
 * Fator de opacidade para transição suave entre níveis.
 * Evita cortes bruscos ao cruzar limites de zoom.
 * @param {number} zoom
 * @param {number} zoomIn  - zoom em que a camada começa a aparecer
 * @param {number} zoomOut - zoom em que a camada começa a desaparecer
 * @returns {number} opacidade entre 0 e 1
 */
export function calcularOpacidade(zoom, zoomIn, zoomOut, fadeRange = 0.5) {
  if (zoom < zoomIn - fadeRange)  return 0;
  if (zoom > zoomOut + fadeRange) return 0;
  if (zoom < zoomIn) return (zoom - (zoomIn - fadeRange)) / fadeRange;
  if (zoom > zoomOut) return 1 - (zoom - zoomOut) / fadeRange;
  return 1;
}

/**
 * Gera a URL do Martin para a camada correta baseada no nível semântico.
 * Os filtros ativos são serializados como query params tipados.
 *
 * @param {string} nivel
 * @param {object} filtros - {ano, cid10_capitulo, cor_raca, faixa_etaria_min, faixa_etaria_max, metrica}
 * @returns {string} URL template para o Martin (com {z}/{x}/{y})
 */
export function getTileUrl(nivel, filtros = {}) {
  const base = import.meta.env.VITE_MARTIN_URL;
  const params = new URLSearchParams();

  // Apenas adiciona parâmetros não-nulos (evita poluir a chave do cache Redis)
  Object.entries(filtros).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      params.set(key, String(value));
    }
  });

  const qs = params.toString() ? `?${params.toString()}` : "";

  const funcaoMap = {
    NACIONAL:       "tiles_ufs",
    ESTADUAL:       "tiles_municipios",
    MUNICIPAL:      "tiles_setores",
    GEOLOCALIZACAO: "tiles_cnefe",
  };

  return `${base}/${funcaoMap[nivel]}/{z}/{x}/{y}${qs}`;
}

/**
 * Metadados de cada nível para a UI (label, descrição, ícone de escala).
 */
export const NIVEL_METADATA = {
  NACIONAL: {
    label: "Estadual",
    descricao: "Comparativo entre as 27 UFs",
    geometria: "Unidades da Federação",
    icone: "🗺️",
    temDados: true,
  },
  ESTADUAL: {
    label: "Municipal",
    descricao: "5.570 municípios brasileiros",
    geometria: "5.570 municípios",
    icone: "🏙️",
    temDados: true,
  },
  MUNICIPAL: {
    label: "Setores",
    descricao: "Setores censitários IBGE 2022",
    geometria: "~468k setores",
    icone: "🏘️",
    temDados: true,
  },
  GEOLOCALIZACAO: {
    label: "Endereços",
    descricao: "Faces de logradouros IBGE 2022",
    geometria: "~13.8M pontos",
    icone: "📍",
    temDados: true,
  },
};
