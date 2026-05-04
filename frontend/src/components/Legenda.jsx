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
  "taxa_aprovacao_ef", "taxa_aprovacao_em",
  "pct_geladeira", "pct_ar_condicionado", "pct_freezer", "pct_tv",
  "pct_automovel_domicilio", "pct_motocicleta_domicilio",
  "pct_microondas", "pct_computador",
  "taxa_reprovacao_ef", "taxa_abandono_ef", "taxa_abandono_em",
  "distorcao_idade_serie_ef", "distorcao_idade_serie_em",
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
  if (metrica === "leitos_sus_por_1k" || metrica === "media_permanencia_sus") {
    return n.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
  }
  if (metrica === "media_moradores" || metrica === "media_anos_estudo" || metrica === "idade_mediana") {
    return n.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  }
  if (metrica.startsWith("rebanho_")) {
    return n.toLocaleString("pt-BR", { maximumFractionDigits: 3 });
  }
  if (metrica.startsWith("producao_") || metrica === "producao_mel_kg") {
    return n.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
  }
  return n.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
}

const METRICAS_SAUDE_SET = new Set(["taxa_mortalidade", "taxa_homicidio", "mortalidade_infantil"]);

export function Legenda({ metrica, min, max, semDados = false, invertida = false, adaptativo = false }) {
  const label = METRICAS_LABELS[metrica] ?? metrica;

  // Rótulo central da legenda
  const legendaMeio = invertida
    ? "↑ melhor"
    : METRICAS_SAUDE_SET.has(metrica)
      ? "↑ maior risco"
      : metrica === "densidade_pop"
        ? "↑ mais denso"
        : "↑ maior valor";

  // Gradiente CSS espelha getCorCoroplética
  const gradiente = invertida
    ? "linear-gradient(to right, rgb(255,0,0), rgb(255,255,0), rgb(0,220,50))"   // vermelho→amarelo→verde
    : "linear-gradient(to right, rgb(0,255,255), rgb(255,255,0), rgb(255,0,0))"; // ciano→amarelo→vermelho

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
          <div style={{
            height: 10,
            borderRadius: 4,
            background: gradiente,
            marginBottom: 4,
          }} />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#a0aec0" }}>
            <span>{formatarValor(min, metrica)}</span>
            <span style={{ color: "#4a5568" }}>{legendaMeio}</span>
            <span>{formatarValor(max, metrica)}</span>
          </div>
          {adaptativo && (
            <div style={{ fontSize: 9, color: "#4a5568", marginTop: 3, textAlign: "right", letterSpacing: "0.04em" }}>
              P2–P98 dos dados carregados
            </div>
          )}
        </>
      )}
    </div>
  );
}
