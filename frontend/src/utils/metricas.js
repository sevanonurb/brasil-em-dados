/**
 * metricas.js — Metadados centralizados de todas as métricas do painel.
 *
 * Fonte unica de verdade para: labels, unidades, categorias de formatacao.
 * Elimina duplicacao entre main.jsx, Legenda.jsx e PainelDetalhes.jsx.
 */

// ── Categorias de formatacao ──────────────────────────────────────────────────

/** Metricas monetarias (R$) */
export const METRICAS_REAIS = new Set([
  "pib_per_capita", "receita_per_capita",
  "despesa_saude_per_capita", "despesa_educacao_per_capita",
  "vbp_agricola_per_capita", "vbp_pecuaria_per_capita",
  "renda_media_trabalho", "renda_mediana_trabalho",
  "renda_domiciliar_per_capita", "renda_domiciliar_mediana_pc",
]);

/** Metricas percentuais (%) */
export const METRICAS_PERCENT = new Set([
  "acesso_agua", "acesso_esgoto", "coleta_lixo",
  "taxa_alfabetizacao", "domicilios_internet", "pop_favelas_pct",
  "divida_rcl", "despesa_pessoal_rcl",
  "pct_superior_completo", "taxa_deficiencia",
  "taxa_ocupacao",
  "pct_pib_agropecuaria", "pct_pib_industria", "pct_pib_servicos",
  "pct_indigena", "pct_quilombola", "pct_agrofamiliar",
  "pct_mecanizado", "pct_financiamento",
  "taxa_migracao", "taxa_escolarizacao_1517",
  "taxa_desemprego", "taxa_pendular", "taxa_informalidade",
  "pct_baixa_renda", "pct_renda_trabalho",
  "pct_chefia_feminina", "domicilios_maquina_lavar", "superlotacao_domiciliar",
  "domicilios_alugados", "domicilios_monoparentais",
  "pct_urbano", "pct_alvenaria", "pct_banheiro_exclusivo",
  "taxa_aprovacao_ef", "taxa_reprovacao_ef", "taxa_abandono_ef",
  "taxa_aprovacao_em", "taxa_abandono_em",
  "distorcao_idade_serie_ef", "distorcao_idade_serie_em",
  "pct_geladeira", "pct_ar_condicionado", "pct_freezer", "pct_tv",
  "pct_automovel_domicilio", "pct_motocicleta_domicilio",
  "pct_microondas", "pct_computador",
]);

/** Metricas por 1k hab. */
export const METRICAS_POR_1K = new Set([
  "taxa_natalidade", "taxa_nupcialidade", "taxa_divorcialidade", "taxa_separacao",
  "leitos_sus_por_1k", "taxa_internacao_sus",
  "frota_automovel_por_1k", "frota_moto_por_1k", "frota_caminhao_por_1k",
  "frota_onibus_por_1k", "frota_total_por_1k",
]);

/** Metricas por 100k hab. */
export const METRICAS_POR_100K = new Set([
  "taxa_mortalidade", "taxa_homicidio",
  "incidencia_dengue", "incidencia_tuberculose",
  "incidencia_hanseniase", "incidencia_leishmaniose",
  "taxa_internacao_cardiovascular", "taxa_internacao_respiratoria",
  "taxa_internacao_mental",
]);

/** Metricas de saude (suportam filtros demograficos) */
export const METRICAS_SAUDE_SET = new Set([
  "taxa_mortalidade", "taxa_homicidio", "mortalidade_infantil",
]);

// ── Labels ────────────────────────────────────────────────────────────────────

/** Label curto para tooltips */
export const METRICA_LABEL_CURTO = {
  taxa_mortalidade:            "Mortalidade",
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
  taxa_desemprego:             "Desemprego",
  taxa_pendular:               "Pendularidade laboral",
  taxa_informalidade:          "Informalidade",
  pct_baixa_renda:             "Baixa renda (≤1/2 SM)",
  pct_renda_trabalho:          "% renda do trabalho",
  pct_chefia_feminina:         "Chefia feminina",
  domicilios_maquina_lavar:    "Máquina de lavar",
  superlotacao_domiciliar:     "Superlotação domiciliar",
  domicilios_alugados:         "Domicílios alugados",
  domicilios_monoparentais:    "Domicílios monoparentais",
  media_filhos_mulher:         "Média filhos/mulher",
  pct_urbano:                  "Pop. urbana",
  pct_alvenaria:               "Alvenaria",
  pct_banheiro_exclusivo:      "Banheiro exclusivo",
  taxa_nupcialidade:           "Nupcialidade",
  taxa_divorcialidade:         "Divorcialidade",
  taxa_separacao:              "Separação judicial",
  taxa_obito_fetal:            "Óbito fetal",
  incidencia_dengue:           "Dengue",
  incidencia_tuberculose:      "Tuberculose",
  incidencia_hanseniase:       "Hanseníase",
  incidencia_leishmaniose:     "Leishmaniose",
  taxa_internacao_sus:         "Internações SUS",
  taxa_internacao_cardiovascular: "Internações cardiovasc.",
  taxa_internacao_respiratoria:   "Internações respirat.",
  taxa_internacao_mental:         "Internações mental",
  media_permanencia_sus:       "Permanência hosp.",
  taxa_aprovacao_ef:           "Aprovação EF",
  taxa_reprovacao_ef:          "Reprovação EF",
  taxa_abandono_ef:            "Abandono EF",
  taxa_aprovacao_em:           "Aprovação EM",
  taxa_abandono_em:            "Abandono EM",
  distorcao_idade_serie_ef:    "Distorção EF",
  distorcao_idade_serie_em:    "Distorção EM",
  frota_automovel_por_1k:      "Automóveis",
  frota_moto_por_1k:           "Motocicletas",
  frota_caminhao_por_1k:       "Caminhões",
  frota_onibus_por_1k:         "Ônibus",
  frota_total_por_1k:          "Frota total",
  rebanho_bovino_por_km2:      "Bovino/km²",
  rebanho_bovino_por_hab:      "Bovino/hab.",
  rebanho_suino_por_hab:       "Suíno/hab.",
  rebanho_ovino_por_hab:       "Ovino/hab.",
  rebanho_caprino_por_hab:     "Caprino/hab.",
  rebanho_galinaceos_por_hab:  "Galináceos/hab.",
  rebanho_equino_por_hab:      "Equino/hab.",
  producao_leite_por_vaca:     "Leite/vaca",
  producao_leite_per_capita:   "Leite per capita",
  producao_mel_por_colmeia:    "Mel/colmeia",
  producao_mel_kg:             "Mel (kg)",
  producao_ovos_total:         "Ovos (mil dúzias)",
  producao_ovos_per_capita:    "Ovos/hab.",
  pct_geladeira:               "Geladeira",
  pct_ar_condicionado:         "Ar-condicionado",
  pct_freezer:                 "Freezer",
  pct_tv:                      "Televisão",
  pct_automovel_domicilio:     "Automóvel (domicílio)",
  pct_motocicleta_domicilio:   "Motocicleta (domicílio)",
  pct_microondas:              "Microondas",
  pct_computador:              "Computador",
};

/** Label longo para legendas e painéis */
export const METRICA_LABEL_LONGO = {
  taxa_mortalidade:            "Mortalidade geral (por 100k hab.)",
  taxa_homicidio:              "Homicídios (por 100k hab.)",
  mortalidade_infantil:        "Mortalidade infantil (por 1k nasc. vivos)",
  pib_per_capita:              "PIB per capita",
  receita_per_capita:          "Receita municipal per capita",
  despesa_saude_per_capita:    "Gasto em saúde per capita",
  despesa_educacao_per_capita: "Gasto em educação per capita",
  densidade_pop:               "Densidade demográfica (hab/km²)",
  acesso_agua:                 "Acesso à água encanada (%)",
  acesso_esgoto:               "Acesso à rede de esgoto (%)",
  coleta_lixo:                 "Coleta de lixo (%)",
  taxa_natalidade:             "Taxa de natalidade (nasc./1k hab.)",
  leitos_sus_por_1k:           "Leitos SUS (por 1k hab.)",
  medicos_por_10k:             "Médicos (por 10k hab.)",
  ideb_anos_iniciais:          "IDEB — anos iniciais (0–10)",
  ideb_anos_finais:            "IDEB — anos finais (0–10)",
  taxa_alfabetizacao:          "Taxa de alfabetização 15+ (%)",
  taxa_envelhecimento:         "Índice de envelhecimento",
  razao_sexo:                  "Razão de sexo (h/100 mulheres)",
  media_moradores:             "Média de moradores/domicílio",
  domicilios_internet:         "Domicílios com internet (%)",
  pop_favelas_pct:             "Pop. em aglomerados subnormais (%)",
  vbp_agricola_per_capita:     "VBP agrícola per capita (R$)",
  vbp_pecuaria_per_capita:     "VBP pecuário per capita (R$)",
  divida_rcl:                  "Dívida consolidada / RCL (%)",
  despesa_pessoal_rcl:         "Despesa pessoal / RCL (%)",
  pct_indigena:                "Pop. indígena (autodeclarada) (%)",
  pct_quilombola:              "Pop. quilombola (%)",
  pct_agrofamiliar:            "Agricultura familiar — % estabelecimentos",
  pct_mecanizado:              "Estabelecimentos com tratores (%)",
  pct_financiamento:           "Estabelecimentos com financiamento (%)",
  empresas_por_1k:             "Empresas e organizações (por 1k hab.)",
  taxa_migracao:               "Imigração inter-municipal (%)",
  media_filhos_mulher:         "Média de filhos nascidos vivos por mulher (12+)",
  pct_urbano:                  "População urbana (%)",
  pct_alvenaria:               "Domicílios com paredes de alvenaria (%)",
  pct_banheiro_exclusivo:      "Moradores em domicílios com banheiro exclusivo (%)",
  taxa_nupcialidade:           "Taxa de nupcialidade (casamentos / 1000 hab.)",
  taxa_divorcialidade:         "Taxa de divorcialidade (divórcios / 1000 hab.)",
  taxa_separacao:              "Taxa de separação judicial (/1k hab.)",
  taxa_obito_fetal:            "Taxa de óbito fetal (/1k nascidos vivos)",
  incidencia_dengue:           "Dengue — incidência (/100k hab.)",
  incidencia_tuberculose:      "Tuberculose — incidência (/100k hab.)",
  incidencia_hanseniase:       "Hanseníase — incidência (/100k hab.)",
  incidencia_leishmaniose:     "Leishmaniose visceral — incidência (/100k hab.)",
  taxa_internacao_sus:         "Internações SUS (/1k hab.)",
  taxa_internacao_cardiovascular: "Internações cardiovasculares (/100k hab.)",
  taxa_internacao_respiratoria:   "Internações respiratórias (/100k hab.)",
  taxa_internacao_mental:         "Internações saúde mental (/100k hab.)",
  media_permanencia_sus:       "Média de permanência hospitalar (dias)",
  taxa_aprovacao_ef:           "Aprovação — Ens. Fundamental (%)",
  taxa_reprovacao_ef:          "Reprovação — Ens. Fundamental (%)",
  taxa_abandono_ef:            "Abandono — Ens. Fundamental (%)",
  taxa_aprovacao_em:           "Aprovação — Ens. Médio (%)",
  taxa_abandono_em:            "Abandono — Ens. Médio (%)",
  distorcao_idade_serie_ef:    "Distorção idade-série — Ens. Fundamental (%)",
  distorcao_idade_serie_em:    "Distorção idade-série — Ens. Médio (%)",
  frota_automovel_por_1k:      "Automóveis (/1k hab.)",
  frota_moto_por_1k:           "Motocicletas (/1k hab.)",
  frota_caminhao_por_1k:       "Caminhões (/1k hab.)",
  frota_onibus_por_1k:         "Ônibus (/1k hab.)",
  frota_total_por_1k:          "Frota total (/1k hab.)",
  rebanho_bovino_por_km2:      "Rebanho bovino (cab./km²)",
  rebanho_bovino_por_hab:      "Rebanho bovino (cab./hab.)",
  rebanho_suino_por_hab:       "Rebanho suíno (cab./hab.)",
  rebanho_ovino_por_hab:       "Rebanho ovino (cab./hab.)",
  rebanho_caprino_por_hab:     "Rebanho caprino (cab./hab.)",
  rebanho_galinaceos_por_hab:  "Galináceos (cab./hab.)",
  rebanho_equino_por_hab:      "Equinos (cab./hab.)",
  producao_leite_por_vaca:     "Produção de leite por vaca (L/vaca)",
  producao_leite_per_capita:   "Produção de leite per capita (L/hab.)",
  producao_mel_por_colmeia:    "Produção de mel por colmeia (kg/colmeia)",
  producao_mel_kg:             "Produção de mel — total (kg)",
  producao_ovos_total:         "Produção de ovos — total (mil dúzias)",
  producao_ovos_per_capita:    "Produção de ovos per capita (dúzias/hab.)",
  pct_geladeira:               "Domicílios com geladeira (%)",
  pct_ar_condicionado:         "Domicílios com ar-condicionado (%)",
  pct_freezer:                 "Domicílios com freezer (%)",
  pct_tv:                      "Domicílios com televisão (%)",
  pct_automovel_domicilio:     "Domicílios com automóvel (%)",
  pct_motocicleta_domicilio:   "Domicílios com motocicleta (%)",
  pct_microondas:              "Domicílios com microondas (%)",
  pct_computador:              "Domicílios com computador (%)",
  domicilios_alugados:         "Domicílios alugados (%)",
  domicilios_monoparentais:    "Domicílios monoparentais — sem cônjuge com filhos (%)",
  pct_chefia_feminina:         "Domicílios com responsável mulher (%)",
  domicilios_maquina_lavar:    "Domicílios com máquina de lavar (%)",
  superlotacao_domiciliar:     "Superlotação domiciliar — >3 mor./quarto (%)",
  taxa_escolarizacao_1517:     "Taxa de escolarização 15-17 anos (%)",
  taxa_desemprego:             "Taxa de desemprego — 14+ (%)",
  taxa_pendular:               "Pendularidade laboral — trabalha em outro município (%)",
  taxa_informalidade:          "Taxa de informalidade no trabalho (%)",
  pct_baixa_renda:             "Pop. com renda domiciliar ≤ 1/2 SM per capita (%)",
  pct_renda_trabalho:          "Renda domiciliar proveniente de trabalho (%)",
  renda_domiciliar_per_capita: "Renda domiciliar per capita — média (R$)",
  renda_domiciliar_mediana_pc: "Renda domiciliar per capita — mediana (R$)",
  renda_media_trabalho:        "Renda média do trabalho (R$)",
  renda_mediana_trabalho:      "Renda mediana do trabalho (R$)",
  media_anos_estudo:           "Média de anos de estudo (11+)",
  pct_superior_completo:       "Superior completo — 25+ (%)",
  taxa_deficiencia:            "Taxa de deficiência (%)",
  taxa_ocupacao:               "Nível de ocupação 10+ (%)",
  idade_mediana:               "Idade mediana (anos)",
  pct_pib_agropecuaria:        "Agropecuária — % do PIB municipal",
  pct_pib_industria:           "Indústria — % do PIB municipal",
  pct_pib_servicos:            "Serviços — % do PIB municipal",
};

// ── Formatacao unificada ──────────────────────────────────────────────────────

/**
 * Regras especiais de formatacao por metrica.
 * Cada entrada: { decimais, unidade, prefixo? }
 * Metricas nao listadas aqui sao formatadas pela categoria (REAIS/PERCENT/etc).
 */
const FORMATO_ESPECIAL = {
  densidade_pop:           { decimais: 1, unidade: " hab/km²" },
  mortalidade_infantil:    { decimais: 1, unidade: "/1k nasc." },
  taxa_obito_fetal:        { decimais: 1, unidade: "/1k nasc. vivos" },
  medicos_por_10k:         { decimais: 1, unidade: "/10k hab." },
  media_permanencia_sus:   { decimais: 1, unidade: " dias" },
  razao_sexo:              { decimais: 1, unidade: " h/100 mul." },
  media_moradores:         { decimais: 2, unidade: " mor./dom.", minDecimals: 1 },
  media_anos_estudo:       { decimais: 1, unidade: " anos", minDecimals: 1 },
  idade_mediana:           { decimais: 0, unidade: " anos" },
  taxa_envelhecimento:     { decimais: 1, unidade: "" },
  producao_leite_por_vaca: { decimais: 0, unidade: " L/vaca" },
  producao_leite_per_capita: { decimais: 0, unidade: " L/hab." },
  producao_mel_por_colmeia:  { decimais: 1, unidade: " kg/colmeia" },
  producao_mel_kg:           { decimais: 0, unidade: " kg" },
  producao_ovos_total:       { decimais: 0, unidade: " mil duz." },
  producao_ovos_per_capita:  { decimais: 2, unidade: " duz./hab." },
  ideb_anos_iniciais:      { decimais: 1, unidade: "", minDecimals: 1 },
  ideb_anos_finais:        { decimais: 1, unidade: "", minDecimals: 1 },
  leitos_sus_por_1k:       { decimais: 2, unidade: "/1k hab." },
  media_filhos_mulher:     { decimais: 1, unidade: "", minDecimals: 1 },
};

/**
 * Formata um valor numerico para exibicao de acordo com a metrica.
 * Retorna { texto, unidade } para composicao flexivel,
 * ou null se o valor for invalido.
 *
 * @param {*} valor - valor bruto (numero ou string)
 * @param {string} metrica - identificador da metrica
 * @returns {{ texto: string, unidade: string } | null}
 */
export function formatarMetrica(valor, metrica) {
  if (valor == null || valor === "") return null;
  const n = typeof valor === "number" ? valor : Number(valor);
  if (!isFinite(n)) return null;

  // 1. Formato especial por metrica
  const esp = FORMATO_ESPECIAL[metrica];
  if (esp) {
    const opts = { maximumFractionDigits: esp.decimais };
    if (esp.minDecimals) opts.minimumFractionDigits = esp.minDecimals;
    return {
      texto: n.toLocaleString("pt-BR", opts),
      unidade: esp.unidade,
    };
  }

  // 2. Rebanho por km2 / por hab
  if (metrica.startsWith("rebanho_") && metrica.endsWith("_por_km2")) {
    return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 2 }), unidade: " cab/km²" };
  }
  if (metrica.startsWith("rebanho_") && metrica.endsWith("_por_hab")) {
    return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 3 }), unidade: " cab/hab." };
  }

  // 3. Categorias genericas
  if (METRICAS_REAIS.has(metrica)) {
    return { texto: "R$ " + n.toLocaleString("pt-BR", { maximumFractionDigits: 0 }), unidade: "" };
  }
  if (METRICAS_PERCENT.has(metrica)) {
    return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 1 }), unidade: "%" };
  }
  if (METRICAS_POR_1K.has(metrica)) {
    return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 2 }), unidade: "/1k hab." };
  }
  if (METRICAS_POR_100K.has(metrica)) {
    return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 1 }), unidade: "/100k hab." };
  }

  // 4. Fallback
  return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 1 }), unidade: "" };
}

/**
 * Formata um valor para tooltip HTML (com <b> e unidade inline).
 * @param {*} valor
 * @param {string} metrica
 * @returns {string} HTML formatado ou "<i>sem dados</i>"
 */
export function formatarParaTooltip(valor, metrica) {
  const f = formatarMetrica(valor, metrica);
  if (!f) return "<i style='color:#718096'>sem dados</i>";
  return `<b>${f.texto}</b>${f.unidade}`;
}

/**
 * Formata um valor para legenda (apenas texto, sem HTML).
 * @param {*} valor
 * @param {string} metrica
 * @returns {string}
 */
export function formatarParaLegenda(valor, metrica) {
  if (valor == null) return "\u2014";
  const f = formatarMetrica(valor, metrica);
  if (!f) return "\u2014";
  return f.texto + f.unidade;
}
