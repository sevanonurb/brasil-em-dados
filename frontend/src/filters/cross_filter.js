/**
 * cross_filter.js
 * Gerencia os filtros multidimensionais do painel.
 *
 * Todos os filtros — incluindo faixa etária e cor/raça — são enviados como
 * query params server-side para o Martin. O PostGIS agrega os registros
 * individuais de sim_mortalidade aplicando os filtros demográficos antes
 * de calcular a taxa por 100k. Isso garante que o mapa sempre mostre dados
 * corretos independentemente de como os filtros são combinados.
 */

import { create } from "zustand";

// Anos-padrão por métrica (fallback até o fetch da API completar).
// Mostra apenas o último ano com dados confirmados para evitar mapa em branco.
export const ANOS_POR_METRICA_DEFAULT = {
  taxa_mortalidade:            [2023],
  taxa_homicidio:              [2023],
  pib_per_capita:              [2022],
  receita_per_capita:          [2022],
  despesa_saude_per_capita:    [2022],
  despesa_educacao_per_capita: [2022],
  densidade_pop:               [2022],
  // Saneamento — Censo 2022 (estático)
  acesso_agua:                 [2022],
  acesso_esgoto:               [2022],
  coleta_lixo:                 [2022],
  // Saúde — SINASC e CNES
  taxa_natalidade:             [2023],
  leitos_sus_por_1k:           [2023],
  medicos_por_10k:             [2023],
  // Educação — IDEB (bienal)
  ideb_anos_iniciais:          [2023],
  ideb_anos_finais:            [2023],
  // Censo 2022 — Demográficos (estático)
  taxa_envelhecimento:         [2022],
  razao_sexo:                  [2022],
  taxa_alfabetizacao:          [2022],
  domicilios_internet:         [2022],
  media_moradores:             [2022],
  pop_favelas_pct:             [2022],
  // Censo 2022 Amostra — Renda e Trabalho (estático)
  renda_domiciliar_per_capita: [2022],
  renda_domiciliar_mediana_pc: [2022],
  renda_media_trabalho:        [2022],
  renda_mediana_trabalho:      [2022],
  // Mortalidade Infantil (Registro Civil — anual)
  mortalidade_infantil:        [2023],
  // Censo 2022 Amostra — Trabalho
  taxa_ocupacao:               [2022],
  // Censo 2022 Amostra — Educação
  media_anos_estudo:           [2022],
  pct_superior_completo:       [2022],
  taxa_deficiencia:            [2022],
  // Censo 2022 — Demográficos adicionais
  idade_mediana:               [2022],
  // PIB setorial — T5938 (anual, defasagem ~2 anos)
  pct_pib_agropecuaria:        [2021],
  pct_pib_industria:           [2021],
  pct_pib_servicos:            [2021],
  // PAM — Produção Agrícola Municipal
  vbp_agricola_per_capita:     [2023],
  // Pecuária Municipal (T74)
  vbp_pecuaria_per_capita:     [2023],
  // Fiscal — Siconfi RGF
  divida_rcl:                  [2022],
  despesa_pessoal_rcl:         [2022],
  // Censo 2022 — Raça/Etnia (estático)
  pct_indigena:                [2022],
  pct_quilombola:              [2022],
  // Censo Agropecuário 2017 (estático)
  pct_agrofamiliar:            [2017],
  pct_mecanizado:              [2017],
  pct_financiamento:           [2017],
  // CEMPRE — empresas por mil hab. (anual)
  empresas_por_1k:             [2023],
  // Censo 2022 — Migração e Escolarização (estático)
  taxa_migracao:               [2022],
  taxa_escolarizacao_1517:     [2022],
  // Censo 2022 — Mercado de Trabalho (estático)
  taxa_desemprego:             [2022],
  taxa_pendular:               [2022],
  taxa_informalidade:          [2022],
  // Censo 2022 — Renda e Pobreza (estático)
  pct_baixa_renda:             [2022],
  pct_renda_trabalho:          [2022],
  // Censo 2022 — Domicílios e Habitação (estático)
  pct_chefia_feminina:         [2022],
  domicilios_maquina_lavar:    [2022],
  superlotacao_domiciliar:     [2022],
  domicilios_alugados:         [2022],
  domicilios_monoparentais:    [2022],
  // Censo 2022 — Fecundidade (estático)
  media_filhos_mulher:         [2022],
  // Censo 2022 — Urbanização e Qualidade Habitacional (estático)
  pct_urbano:                  [2022],
  pct_alvenaria:               [2022],
  pct_banheiro_exclusivo:      [2022],
  // Registro Civil — Nupcialidade e Divorcialidade (anual)
  taxa_nupcialidade:           [2024, 2023, 2022, 2021, 2020, 2019, 2018],
  taxa_divorcialidade:         [2024, 2023, 2022, 2021, 2020, 2019, 2018],
};

// Re-exporta para compatibilidade com imports existentes
export const ANOS_POR_METRICA = ANOS_POR_METRICA_DEFAULT;

// Métricas que suportam filtros demográficos (sexo, cor/raça, faixa etária)
export const METRICAS_SAUDE = ["taxa_mortalidade", "taxa_homicidio"];

// Labels legíveis por capítulo/grupo CID-10 (inclui 'suicidio' como sub-capítulo especial)
export const CID10_LABELS = {
  I:        "Cardiovascular",
  C:        "Neoplasias / Câncer",
  J:        "Respiratório",
  E:        "Diabetes / Endócrinas",
  K:        "Digestivo / Cirrose",
  N:        "Renal / Urológico",
  G:        "Neurológico",
  B:        "Infecciosas — HIV, Hepatite",
  A:        "Infecciosas — TB, Cólera",
  suicidio: "Suicídio",
  V:        "Acidentes de transporte",
  W:        "Quedas / Acidentes",
  X:        "Causas externas diversas",
  Y:        "Causas ext. indeterminadas",
  O:        "Mortalidade materna",
  P:        "Perinatais / Neonatais",
  F:        "Transtornos mentais",
  Q:        "Malformações congênitas",
};

// ─────────────────────────────────────────────────────────────────────────────
// Store Zustand: estado global dos filtros
// ─────────────────────────────────────────────────────────────────────────────
export const useFiltrosStore = create((set, get) => ({
  // Filtros server-side (mudar recarrega tiles)
  ano: 2023,
  cod_uf: null,
  cid10_capitulo: null,
  metrica: "taxa_mortalidade",

  // Filtros demográficos (também server-side — passados ao PostGIS via Martin)
  faixa_etaria_min: 0,
  faixa_etaria_max: 17,
  cor_raca: null,  // null = todos; 1=Branca, 2=Preta, 4=Parda, 5=Indígena
  sexo: null,      // null = todos; 'M' = Masculino, 'F' = Feminino
  especie: null,   // null = todos; 1=Residencial, 2=Coletivo (apenas CNEFE)

  // Anos disponíveis por métrica — preenchido pelo fetch da API em main.jsx
  anosDisponiveis: ANOS_POR_METRICA_DEFAULT,

  // Ações
  setAno: (ano) => set({ ano }),
  setUF: (cod_uf) => set({ cod_uf }),
  setCID10: (cid10_capitulo) => set({ cid10_capitulo }),
  setMetrica: (metrica) => {
    const anos = get().anosDisponiveis[metrica] ?? [2023];
    const currentAno = get().ano;
    set({ metrica, ano: anos.includes(currentAno) ? currentAno : anos[0] });
  },
  setFaixaEtaria: ([min, max]) => set({ faixa_etaria_min: min, faixa_etaria_max: max }),
  setCorRaca: (cor_raca) => set({ cor_raca }),
  setSexo: (sexo) => set({ sexo }),
  setEspecie: (especie) => set({ especie }),
  setAnosDisponiveis: (anosDisponiveis) => {
    // Quando os anos chegam, corrige o ano selecionado se não estiver disponível
    const { metrica, ano } = get();
    const anos = anosDisponiveis[metrica] ?? [2023];
    set({ anosDisponiveis, ano: anos.includes(ano) ? ano : anos[0] });
  },

  resetFiltros: () => set({
    ano: get().anosDisponiveis["taxa_mortalidade"]?.[0] ?? 2023,
    cod_uf: null,
    cid10_capitulo: null,
    metrica: "taxa_mortalidade",
    faixa_etaria_min: 0,
    faixa_etaria_max: 17,
    cor_raca: null,
    sexo: null,
    especie: null,
  }),

  // Serializa os filtros como query params para o Martin.
  // Filtros demográficos só são incluídos quando não estão no valor padrão
  // (evita fragmentar o cache para métricas que não os usam).
  getServerParams: () => {
    const { ano, cod_uf, cid10_capitulo, metrica,
            faixa_etaria_min, faixa_etaria_max, cor_raca, sexo, especie } = get();
    const params = { ano, cod_uf, cid10_capitulo, metrica };

    // Filtros demográficos afetam apenas métricas de saúde
    if (METRICAS_SAUDE.includes(metrica)) {
      if (faixa_etaria_min !== 0 || faixa_etaria_max !== 17) {
        params.faixa_etaria_min = faixa_etaria_min;
        params.faixa_etaria_max = faixa_etaria_max;
      }
      if (cor_raca !== null) params.cor_raca = cor_raca;
      if (sexo !== null)     params.sexo = sexo;
    }
    // especie aplica-se apenas ao nível GEOLOCALIZACAO (tiles_cnefe)
    if (especie !== null) params.especie = especie;
    return params;
  },
}));
