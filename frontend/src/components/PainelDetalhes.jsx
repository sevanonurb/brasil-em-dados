/**
 * PainelDetalhes.jsx
 * Painel lateral de drill-down: exibido ao clicar em uma feature do mapa.
 */

import { CID10_LABELS } from "../filters/cross_filter.js";

/**
 *
 * Campos disponíveis nos tiles (source-of-truth):
 *   UF (NACIONAL):    cod_uf, sigla, nome, regiao, populacao_total,
 *                     pib_estadual, receita_estadual_total, transferencias_sus_total, valor_metrica
 *   Município (ESTADUAL): cod_ibge_7, cod_uf, nome_municipio, populacao_2022,
 *                     transferencias_sus, valor_metrica
 */


const METRICA_LABEL = {
  taxa_mortalidade:                  "Taxa de mortalidade",
  taxa_homicidio:                    "Taxa de homicídio",
  mortalidade_infantil:              "Mortalidade infantil",
  pib_per_capita:                    "PIB per capita",
  receita_per_capita:                "Receita municipal per capita",
  despesa_saude_per_capita:          "Gasto em saúde per capita",
  despesa_educacao_per_capita:       "Gasto em educação per capita",
  densidade_pop:                     "Densidade demográfica",
  acesso_agua:                       "Água encanada",
  acesso_esgoto:                     "Esgoto (rede)",
  coleta_lixo:                       "Coleta de lixo",
  taxa_natalidade:                   "Taxa de natalidade",
  leitos_sus_por_1k:                 "Leitos SUS",
  medicos_por_10k:                   "Médicos",
  ideb_anos_iniciais:                "IDEB anos iniciais",
  ideb_anos_finais:                  "IDEB anos finais",
  taxa_nupcialidade:                 "Taxa de nupcialidade",
  taxa_divorcialidade:               "Taxa de divorcialidade",
  taxa_separacao:                    "Taxa de separação judicial",
  taxa_obito_fetal:                  "Taxa de óbito fetal",
  incidencia_dengue:                 "Incidência de dengue",
  incidencia_tuberculose:            "Incidência de tuberculose",
  incidencia_hanseniase:             "Incidência de hanseníase",
  incidencia_leishmaniose:           "Incidência de leishmaniose",
  taxa_internacao_sus:               "Internações SUS",
  taxa_internacao_cardiovascular:    "Internações cardiovasculares",
  taxa_internacao_respiratoria:      "Internações respiratórias",
  taxa_internacao_mental:            "Internações saúde mental",
  media_permanencia_sus:             "Média de permanência hospitalar",
  taxa_aprovacao_ef:                 "Aprovação — Ens. Fundamental",
  taxa_reprovacao_ef:                "Reprovação — Ens. Fundamental",
  taxa_abandono_ef:                  "Abandono — Ens. Fundamental",
  taxa_aprovacao_em:                 "Aprovação — Ens. Médio",
  taxa_abandono_em:                  "Abandono — Ens. Médio",
  distorcao_idade_serie_ef:          "Distorção idade-série — EF",
  distorcao_idade_serie_em:          "Distorção idade-série — EM",
  frota_automovel_por_1k:            "Automóveis",
  frota_moto_por_1k:                 "Motocicletas",
  frota_caminhao_por_1k:             "Caminhões",
  frota_onibus_por_1k:               "Ônibus",
  frota_total_por_1k:                "Frota total",
  rebanho_bovino_por_km2:            "Rebanho bovino (por km²)",
  rebanho_bovino_por_hab:            "Rebanho bovino (por hab.)",
  rebanho_suino_por_hab:             "Rebanho suíno (por hab.)",
  rebanho_ovino_por_hab:             "Rebanho ovino (por hab.)",
  rebanho_caprino_por_hab:           "Rebanho caprino (por hab.)",
  rebanho_galinaceos_por_hab:        "Galináceos (por hab.)",
  rebanho_equino_por_hab:            "Equinos (por hab.)",
  producao_leite_por_vaca:           "Produção de leite por vaca",
  producao_leite_per_capita:         "Produção de leite per capita",
  producao_mel_por_colmeia:          "Produção de mel por colmeia",
  producao_mel_kg:                   "Produção de mel (total)",
  producao_ovos_total:               "Produção de ovos (total)",
  producao_ovos_per_capita:          "Produção de ovos per capita",
  pct_geladeira:                     "Domicílios com geladeira",
  pct_ar_condicionado:               "Domicílios com ar-condicionado",
  pct_freezer:                       "Domicílios com freezer",
  pct_tv:                            "Domicílios com televisão",
  pct_automovel_domicilio:           "Domicílios com automóvel",
  pct_motocicleta_domicilio:         "Domicílios com motocicleta",
  pct_microondas:                    "Domicílios com microondas",
  pct_computador:                    "Domicílios com computador",
};

const METRICAS_REAIS = new Set([
  "pib_per_capita", "receita_per_capita",
  "despesa_saude_per_capita", "despesa_educacao_per_capita",
  "vbp_agricola_per_capita", "vbp_pecuaria_per_capita",
  "renda_domiciliar_per_capita", "renda_domiciliar_mediana_pc",
  "renda_media_trabalho", "renda_mediana_trabalho",
]);

const METRICAS_PERCENT = new Set([
  "acesso_agua", "acesso_esgoto", "coleta_lixo",
  "taxa_aprovacao_ef", "taxa_reprovacao_ef", "taxa_abandono_ef",
  "taxa_aprovacao_em", "taxa_abandono_em",
  "distorcao_idade_serie_ef", "distorcao_idade_serie_em",
  "pct_geladeira", "pct_ar_condicionado", "pct_freezer", "pct_tv",
  "pct_automovel_domicilio", "pct_motocicleta_domicilio",
  "pct_microondas", "pct_computador",
]);

const METRICAS_POR_1K = new Set([
  "taxa_natalidade", "taxa_nupcialidade", "taxa_divorcialidade", "taxa_separacao",
  "leitos_sus_por_1k", "taxa_internacao_sus",
  "frota_automovel_por_1k", "frota_moto_por_1k", "frota_caminhao_por_1k",
  "frota_onibus_por_1k", "frota_total_por_1k",
]);

const METRICAS_POR_100K = new Set([
  "incidencia_dengue", "incidencia_tuberculose",
  "incidencia_hanseniase", "incidencia_leishmaniose",
  "taxa_internacao_cardiovascular", "taxa_internacao_respiratoria",
  "taxa_internacao_mental",
]);

function formatarMetrica(valor, metrica) {
  if (valor == null || valor === "") return null;
  const n = typeof valor === "number" ? valor : Number(valor);
  if (!isFinite(n)) return null;

  if (METRICAS_REAIS.has(metrica)) {
    return { texto: "R$ " + n.toLocaleString("pt-BR", { maximumFractionDigits: 0 }), unidade: "" };
  }
  if (metrica === "densidade_pop") {
    return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 1 }), unidade: " hab/km²" };
  }
  if (METRICAS_PERCENT.has(metrica)) {
    return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 1 }), unidade: "%" };
  }
  if (metrica === "ideb_anos_iniciais" || metrica === "ideb_anos_finais") {
    return { texto: n.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }), unidade: " / 10" };
  }
  if (metrica === "medicos_por_10k") {
    return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 1 }), unidade: " /10k hab." };
  }
  if (METRICAS_POR_1K.has(metrica)) {
    return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 2 }), unidade: " /1k hab." };
  }
  if (METRICAS_POR_100K.has(metrica)) {
    return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 1 }), unidade: " /100k hab." };
  }
  if (metrica === "mortalidade_infantil" || metrica === "taxa_obito_fetal") {
    return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 1 }), unidade: " /1k nasc. vivos" };
  }
  if (metrica === "media_permanencia_sus") {
    return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 1 }), unidade: " dias" };
  }
  if (metrica === "producao_leite_por_vaca") {
    return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 0 }), unidade: " L/vaca" };
  }
  if (metrica === "producao_leite_per_capita") {
    return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 0 }), unidade: " L/hab." };
  }
  if (metrica === "producao_mel_por_colmeia") {
    return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 1 }), unidade: " kg/colmeia" };
  }
  if (metrica === "producao_mel_kg") {
    return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 0 }), unidade: " kg" };
  }
  if (metrica === "producao_ovos_total") {
    return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 0 }), unidade: " mil dúzias" };
  }
  if (metrica === "producao_ovos_per_capita") {
    return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 2 }), unidade: " dúzias/hab." };
  }
  if (metrica.startsWith("rebanho_") && metrica.endsWith("_por_km2")) {
    return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 2 }), unidade: " cab/km²" };
  }
  if (metrica.startsWith("rebanho_") && metrica.endsWith("_por_hab")) {
    return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 3 }), unidade: " cab/hab." };
  }
  return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 1 }), unidade: " /100k hab." };
}

export function PainelDetalhes({ feature, nivel, filtros, onClose }) {
  if (!feature) return null;
  const p = feature?.properties ?? {};

  const metrica = filtros?.metrica ?? "taxa_mortalidade";
  const ano = filtros?.ano ?? 2023;
  const cid10 = filtros?.cid10_capitulo;

  // Detecta se é tile de UF ou município
  const isUF = p.sigla != null || p.regiao != null;
  const nome = p.nome_municipio || p.nome || p.sigla || `Setor ${p.cod_setor}`;
  const subtitulo = isUF ? `${p.regiao ?? ""}` : null;

  const valorFormatado = formatarMetrica(p.valor_metrica, metrica);
  const metricaLabel = cid10
    ? `${METRICA_LABEL[metrica] ?? metrica} — ${CID10_LABELS[cid10] ?? `CID ${cid10}`}`
    : (METRICA_LABEL[metrica] ?? metrica);

  return (
    <div style={{
      position: "absolute",
      top: 16,
      left: 16,
      width: 300,
      maxHeight: "calc(100vh - 32px)",
      overflowY: "auto",
      background: "rgba(15,17,23,0.95)",
      border: "1px solid #2d3748",
      borderRadius: 12,
      backdropFilter: "blur(12px)",
      boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
    }}>
      {/* Cabeçalho */}
      <div style={{
        padding: "12px 16px",
        borderBottom: "1px solid #2d3748",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-start",
      }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 15 }}>{nome}</div>
          {subtitulo && (
            <div style={{ fontSize: 12, color: "#718096" }}>{subtitulo}</div>
          )}
        </div>
        <button
          onClick={onClose}
          style={{
            background: "none", border: "none", color: "#718096",
            cursor: "pointer", fontSize: 18, lineHeight: 1,
          }}
        >×</button>
      </div>

      <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 12 }}>

        {/* Indicador principal */}
        <div style={{
          background: "rgba(66,153,225,0.1)",
          border: "1px solid rgba(66,153,225,0.3)",
          borderRadius: 8,
          padding: "10px 12px",
        }}>
          <div style={{ fontSize: 10, color: "#63b3ed", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>
            {metricaLabel} — {ano}
          </div>
          {valorFormatado ? (
            <div style={{ fontSize: 20, fontWeight: 700, color: "#e2e8f0" }}>
              {valorFormatado.texto}
              <span style={{ fontSize: 12, fontWeight: 400, color: "#a0aec0" }}>{valorFormatado.unidade}</span>
            </div>
          ) : (
            <div style={{ fontSize: 13, color: "#4a5568", fontStyle: "italic" }}>sem dados</div>
          )}
        </div>

        {/* Economia — dados disponíveis dependem do nível */}
        <Secao titulo="Economia">
          {isUF ? (
            <>
              <Metrica label="PIB (soma UF)" valor={p.pib_estadual} prefixo={"R$ "} decimais={0} />
              <Metrica label="Receita (soma UF)" valor={p.receita_estadual_total} prefixo={"R$ "} decimais={0} />
              <Metrica label="Transf. SUS" valor={p.transferencias_sus_total} prefixo={"R$ "} decimais={0} />
            </>
          ) : (
            <>
              <Metrica label="Transf. SUS" valor={p.transferencias_sus} prefixo={"R$ "} decimais={0} />
              <Metrica label="Gasto em saúde" valor={p.despesa_saude} prefixo={"R$ "} decimais={0} />
              <Metrica label="Gasto em educação" valor={p.despesa_educacao} prefixo={"R$ "} decimais={0} />
            </>
          )}
        </Secao>

        {/* Demografia */}
        <Secao titulo="Demografia">
          <Metrica
            label="População (Censo 2022)"
            valor={p.populacao_2022 ?? p.populacao_total}
            decimais={0}
          />
        </Secao>

        {/* Geocódigo */}
        <div style={{
          background: "#1a202c",
          borderRadius: 6,
          padding: "6px 10px",
          fontSize: 11,
          color: "#4a5568",
          fontFamily: "monospace",
        }}>
          {p.cod_ibge_7
            ? `IBGE: ${p.cod_ibge_7}`
            : p.sigla
            ? `UF: ${p.sigla} (cod ${p.cod_uf})`
            : p.cod_setor
            ? `Setor: ${p.cod_setor}`
            : ""}
        </div>
      </div>
    </div>
  );
}

function Secao({ titulo, children }) {
  return (
    <div>
      <div style={{
        fontSize: 10,
        fontWeight: 700,
        color: "#4a5568",
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        marginBottom: 6,
      }}>
        {titulo}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {children}
      </div>
    </div>
  );
}

function Metrica({ label, valor, unidade = "", prefixo = "", decimais = 1 }) {
  if (valor == null) return null;
  const num = typeof valor === "number" ? valor : Number(valor);
  if (!isFinite(num)) return null;
  const formatado = num.toLocaleString("pt-BR", { maximumFractionDigits: decimais });
  return (
    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
      <span style={{ color: "#a0aec0" }}>{label}</span>
      <span style={{ fontWeight: 600 }}>
        {prefixo}{formatado}{unidade}
      </span>
    </div>
  );
}
