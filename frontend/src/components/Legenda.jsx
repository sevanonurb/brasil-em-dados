/**
 * Legenda.jsx
 * Barra de cor coroplética com escala min/max para o painel principal.
 */

import React from "react";

const METRICAS_LABELS = {
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
  vbp_pecuaria_per_capita:     "VBP pecuário per capita (R$)",
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
  "taxa_desemprego", "taxa_pendular", "taxa_informalidade",
  "pct_baixa_renda", "pct_renda_trabalho",
  "pct_chefia_feminina", "domicilios_maquina_lavar", "superlotacao_domiciliar",
  "domicilios_alugados", "domicilios_monoparentais",
  "pct_urbano", "pct_alvenaria", "pct_banheiro_exclusivo",
]);

function formatarValor(v, metrica) {
  if (v == null) return "—";
  const n = Number(v);
  if (METRICAS_REAIS.has(metrica)) {
    return "R$\u00a0" + n.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
  }
  if (METRICAS_PERCENT.has(metrica)) {
    return n.toLocaleString("pt-BR", { maximumFractionDigits: 0 }) + "%";
  }
  if (metrica === "ideb_anos_iniciais" || metrica === "ideb_anos_finais") {
    return n.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  }
  if (metrica === "leitos_sus_por_1k") {
    return n.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
  }
  if (metrica === "media_moradores" || metrica === "media_anos_estudo" || metrica === "idade_mediana") {
    return n.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  }
  return n.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
}

const METRICAS_SAUDE_SET = new Set(["taxa_mortalidade", "taxa_homicidio", "mortalidade_infantil"]);
const METRICAS_MELHOR_ALTO = new Set([
  "acesso_agua", "acesso_esgoto", "coleta_lixo",
  "taxa_natalidade", "leitos_sus_por_1k", "medicos_por_10k",
  "ideb_anos_iniciais", "ideb_anos_finais",
  "taxa_alfabetizacao", "domicilios_internet",
  "vbp_agricola_per_capita", "vbp_pecuaria_per_capita",
  "media_anos_estudo", "pct_superior_completo",
  "renda_domiciliar_per_capita", "renda_domiciliar_mediana_pc",
  "renda_media_trabalho", "renda_mediana_trabalho",
  "taxa_ocupacao",
  "pct_agrofamiliar", "pct_mecanizado", "pct_financiamento",
  "empresas_por_1k", "taxa_escolarizacao_1517",
  "pct_renda_trabalho",
  "pct_chefia_feminina", "domicilios_maquina_lavar",
  "domicilios_alugados", "domicilios_monoparentais",
  "pct_alvenaria", "pct_banheiro_exclusivo",
]);

export function Legenda({ metrica, min, max, semDados = false }) {
  const label = METRICAS_LABELS[metrica] ?? metrica;
  const legendaMeio = METRICAS_SAUDE_SET.has(metrica) ? "↑ maior risco"
    : metrica === "densidade_pop" ? "↑ mais denso"
    : METRICAS_MELHOR_ALTO.has(metrica) ? "↑ melhor"
    : "↑ maior valor";

  return (
    <div style={{
      position: "absolute",
      bottom: 60,
      right: 16,
      background: "rgba(15,17,23,0.88)",
      border: "1px solid #2d3748",
      borderRadius: 8,
      padding: "10px 14px",
      backdropFilter: "blur(8px)",
      pointerEvents: "none",
      minWidth: 190,
    }}>
      <div style={{
        fontSize: 10,
        color: "#718096",
        marginBottom: 6,
        letterSpacing: "0.06em",
        textTransform: "uppercase",
        lineHeight: 1.3,
      }}>
        {label}
      </div>

      {semDados ? (
        <div style={{ fontSize: 11, color: "#4a5568", fontStyle: "italic" }}>
          Sem dados disponíveis
        </div>
      ) : (
        <>
          {/* Gradiente cyan→amarelo→vermelho (espelha getCorCoroplética) */}
          <div style={{
            height: 10,
            borderRadius: 4,
            background: "linear-gradient(to right, rgb(0,255,255), rgb(255,255,0), rgb(255,0,0))",
            marginBottom: 4,
          }} />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#a0aec0" }}>
            <span>{formatarValor(min, metrica)}</span>
            <span style={{ color: "#4a5568" }}>{legendaMeio}</span>
            <span>{formatarValor(max, metrica)}</span>
          </div>
        </>
      )}
    </div>
  );
}
