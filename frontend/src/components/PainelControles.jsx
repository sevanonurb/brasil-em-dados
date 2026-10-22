/**
 * PainelControles.jsx
 * Painel lateral com controles de filtro multidimensional.
 * Filtros grossos (ano, UF, CID10) → disparam nova requisição de tiles.
 * Filtros finos (sliders) → atualizam apenas o filterRange da GPU.
 */

import React, { useState } from "react";
import { NIVEL_METADATA } from "../layers/semantic_zoom.js";
import { METRICAS_SAUDE, CID10_LABELS } from "../filters/cross_filter.js";
import { DEMO } from "../demo.js";
import "./RangeSlider.css";

// 27 UFs em ordem alfabética de sigla
export const UFS_BRASIL = [
  { cod: 12, sigla: "AC", nome: "Acre" },
  { cod: 27, sigla: "AL", nome: "Alagoas" },
  { cod: 16, sigla: "AP", nome: "Amapá" },
  { cod: 13, sigla: "AM", nome: "Amazonas" },
  { cod: 29, sigla: "BA", nome: "Bahia" },
  { cod: 23, sigla: "CE", nome: "Ceará" },
  { cod: 53, sigla: "DF", nome: "Distrito Federal" },
  { cod: 32, sigla: "ES", nome: "Espírito Santo" },
  { cod: 52, sigla: "GO", nome: "Goiás" },
  { cod: 21, sigla: "MA", nome: "Maranhão" },
  { cod: 51, sigla: "MT", nome: "Mato Grosso" },
  { cod: 50, sigla: "MS", nome: "Mato Grosso do Sul" },
  { cod: 31, sigla: "MG", nome: "Minas Gerais" },
  { cod: 15, sigla: "PA", nome: "Pará" },
  { cod: 25, sigla: "PB", nome: "Paraíba" },
  { cod: 41, sigla: "PR", nome: "Paraná" },
  { cod: 26, sigla: "PE", nome: "Pernambuco" },
  { cod: 22, sigla: "PI", nome: "Piauí" },
  { cod: 33, sigla: "RJ", nome: "Rio de Janeiro" },
  { cod: 24, sigla: "RN", nome: "Rio Grande do Norte" },
  { cod: 43, sigla: "RS", nome: "Rio Grande do Sul" },
  { cod: 11, sigla: "RO", nome: "Rondônia" },
  { cod: 14, sigla: "RR", nome: "Roraima" },
  { cod: 42, sigla: "SC", nome: "Santa Catarina" },
  { cod: 35, sigla: "SP", nome: "São Paulo" },
  { cod: 28, sigla: "SE", nome: "Sergipe" },
  { cod: 17, sigla: "TO", nome: "Tocantins" },
];

// Grupos de métricas para o <select> com <optgroup>
export const GRUPOS_METRICAS = [
  {
    label: "Saúde",
    opcoes: [
      { value: "taxa_mortalidade",            label: "Mortalidade geral" },
      { value: "taxa_homicidio",              label: "Homicídios" },
      { value: "mortalidade_infantil",        label: "Mortalidade infantil (por 1k nasc. vivos)" },
      { value: "taxa_natalidade",             label: "Natalidade (nasc./1k hab.)" },
      { value: "leitos_sus_por_1k",           label: "Leitos SUS (por 1k hab.)" },
      { value: "medicos_por_10k",             label: "Médicos (por 10k hab.)" },
    ],
  },
  {
    label: "Economia",
    opcoes: [
      { value: "pib_per_capita",              label: "PIB per capita" },
      { value: "receita_per_capita",          label: "Receita municipal per capita" },
      { value: "despesa_saude_per_capita",    label: "Gasto em saúde per capita" },
      { value: "despesa_educacao_per_capita", label: "Gasto em educação per capita" },
      { value: "vbp_agricola_per_capita",     label: "VBP agrícola per capita" },
      { value: "vbp_pecuaria_per_capita",     label: "VBP pecuário per capita" },
      { value: "empresas_por_1k",             label: "Empresas e organizações (por 1k hab.)" },
    ],
  },
  {
    label: "Estrutura do PIB (% setor)",
    opcoes: [
      { value: "pct_pib_agropecuaria",        label: "Agropecuária — % do PIB" },
      { value: "pct_pib_industria",           label: "Indústria — % do PIB" },
      { value: "pct_pib_servicos",            label: "Serviços — % do PIB" },
    ],
  },
  {
    label: "Finanças Públicas (RGF)",
    opcoes: [
      { value: "divida_rcl",                  label: "Dívida consolidada / RCL (%)" },
      { value: "despesa_pessoal_rcl",         label: "Despesa pessoal / RCL (%)" },
    ],
  },
  {
    label: "Saneamento (Censo 2022)",
    opcoes: [
      { value: "acesso_agua",                 label: "Acesso à água encanada (%)" },
      { value: "acesso_esgoto",               label: "Acesso à rede de esgoto (%)" },
      { value: "coleta_lixo",                 label: "Coleta de lixo (%)" },
    ],
  },
  {
    label: "Educação",
    opcoes: [
      { value: "ideb_anos_iniciais",          label: "IDEB — anos iniciais" },
      { value: "ideb_anos_finais",            label: "IDEB — anos finais" },
      { value: "taxa_alfabetizacao",          label: "Taxa de alfabetização 15+ (%)" },
      { value: "taxa_escolarizacao_1517",     label: "Escolarização 15-17 anos (%)" },
    ],
  },
  {
    label: "Renda e Trabalho (Censo 2022 Amostra)",
    opcoes: [
      { value: "taxa_ocupacao",               label: "Nível de ocupação 10+ (%)" },
      { value: "renda_domiciliar_per_capita",  label: "Renda domiciliar per capita — média (R$)" },
      { value: "renda_domiciliar_mediana_pc",  label: "Renda domiciliar per capita — mediana (R$)" },
      { value: "renda_media_trabalho",         label: "Renda média do trabalho (R$)" },
      { value: "renda_mediana_trabalho",       label: "Renda mediana do trabalho (R$)" },
    ],
  },
  {
    label: "Pobreza e Distribuição de Renda (Censo 2022)",
    opcoes: [
      { value: "pct_baixa_renda",              label: "Pop. com renda ≤ 1/2 SM per capita (%)" },
      { value: "pct_renda_trabalho",           label: "Renda domiciliar do trabalho (%)" },
    ],
  },
  {
    label: "Educação — Censo 2022 Amostra",
    opcoes: [
      { value: "media_anos_estudo",            label: "Média de anos de estudo (11+)" },
      { value: "pct_superior_completo",        label: "Superior completo — 25+ (%)" },
      { value: "taxa_deficiencia",             label: "Taxa de deficiência (%)" },
    ],
  },
  {
    label: "Domicílios e Habitação (Censo 2022)",
    opcoes: [
      { value: "domicilios_internet",         label: "Domicílios com internet (%)" },
      { value: "domicilios_maquina_lavar",    label: "Domicílios com máquina de lavar (%)" },
      { value: "domicilios_alugados",         label: "Domicílios alugados (%)" },
      { value: "domicilios_monoparentais",    label: "Domicílios monoparentais — sem cônjuge com filhos (%)" },
      { value: "superlotacao_domiciliar",     label: "Superlotação — >3 moradores/quarto (%)" },
      { value: "pct_chefia_feminina",         label: "Domicílios com responsável mulher (%)" },
      { value: "pop_favelas_pct",             label: "Pop. em aglomerados subnormais (%)" },
      { value: "pct_urbano",                  label: "Pop. urbana (%)" },
      { value: "pct_alvenaria",               label: "Domicílios com paredes de alvenaria (%)" },
      { value: "pct_banheiro_exclusivo",      label: "Moradores com banheiro exclusivo (%)" },
    ],
  },
  {
    label: "Território — Setor Censitário (Censo 2022)",
    opcoes: [
      { value: "densidade_domiciliar",        label: "Densidade domiciliar (domic./km²)" },
      { value: "media_moradores",             label: "Média de moradores por domicílio" },
      { value: "populacao_absoluta",          label: "População residente (absoluta)" },
      { value: "domicilios_absoluto",         label: "Domicílios particulares (absoluto)" },
      { value: "area_territorial",            label: "Área territorial (km²)" },
    ],
  },
  {
    label: "Registro Civil (anual)",
    opcoes: [
      { value: "taxa_nupcialidade",           label: "Taxa de nupcialidade (casamentos / 1000 hab.)" },
      { value: "taxa_divorcialidade",         label: "Taxa de divorcialidade (divórcios / 1000 hab.)" },
    ],
  },
  {
    label: "Saúde — Epidemiologia (SINAN)",
    opcoes: [
      { value: "incidencia_dengue",           label: "Dengue — incidência (/100k hab.)" },
      { value: "incidencia_tuberculose",      label: "Tuberculose — incidência (/100k hab.)" },
      { value: "incidencia_hanseniase",       label: "Hanseníase — incidência (/100k hab.)" },
      { value: "incidencia_leishmaniose",     label: "Leishmaniose visceral — incidência (/100k hab.)" },
    ],
  },
  {
    label: "Saúde — Internações SUS (SIH)",
    opcoes: [
      { value: "taxa_internacao_sus",             label: "Internações SUS (/1k hab.)" },
      { value: "taxa_internacao_cardiovascular",  label: "Internações cardiovasculares (/100k hab.)" },
      { value: "taxa_internacao_respiratoria",    label: "Internações respiratórias (/100k hab.)" },
      { value: "taxa_internacao_mental",          label: "Internações saúde mental (/100k hab.)" },
      { value: "media_permanencia_sus",           label: "Média de permanência hospitalar (dias)" },
    ],
  },
  {
    label: "Educação — Rendimento Escolar (INEP)",
    opcoes: [
      { value: "taxa_aprovacao_ef",           label: "Aprovação — Ens. Fundamental (%)" },
      { value: "taxa_reprovacao_ef",          label: "Reprovação — Ens. Fundamental (%)" },
      { value: "taxa_abandono_ef",            label: "Abandono — Ens. Fundamental (%)" },
      { value: "taxa_aprovacao_em",           label: "Aprovação — Ens. Médio (%)" },
      { value: "taxa_abandono_em",            label: "Abandono — Ens. Médio (%)" },
      { value: "distorcao_idade_serie_ef",    label: "Distorção idade-série — Ens. Fundamental (%)" },
      { value: "distorcao_idade_serie_em",    label: "Distorção idade-série — Ens. Médio (%)" },
    ],
  },
  {
    label: "Transporte — Frota Veicular (SENATRAN)",
    opcoes: [
      { value: "frota_automovel_por_1k",      label: "Automóveis (por 1k hab.)" },
      { value: "frota_moto_por_1k",           label: "Motocicletas (por 1k hab.)" },
      { value: "frota_caminhao_por_1k",       label: "Caminhões (por 1k hab.)" },
      { value: "frota_onibus_por_1k",         label: "Ônibus (por 1k hab.)" },
      { value: "frota_total_por_1k",          label: "Frota total (por 1k hab.)" },
    ],
  },
  {
    label: "Pecuária — Rebanhos (PPM anual)",
    opcoes: [
      { value: "rebanho_bovino_por_km2",      label: "Rebanho bovino (cabeças/km²)" },
      { value: "rebanho_bovino_por_hab",      label: "Rebanho bovino (cabeças/hab.)" },
      { value: "rebanho_suino_por_hab",       label: "Rebanho suíno (cabeças/hab.)" },
      { value: "rebanho_ovino_por_hab",       label: "Rebanho ovino (cabeças/hab.)" },
      { value: "rebanho_caprino_por_hab",     label: "Rebanho caprino (cabeças/hab.)" },
      { value: "rebanho_galinaceos_por_hab",  label: "Galináceos (cabeças/hab.)" },
      { value: "rebanho_equino_por_hab",      label: "Equinos (cabeças/hab.)" },
    ],
  },
  // Pecuária — Produção: dados ainda não carregados (T74 SIDRA intermitente)
  // {
  //   label: "Pecuária — Produção (PPM anual)",
  //   opcoes: producao_leite_por_vaca, producao_leite_per_capita, producao_mel_*, producao_ovos_*
  // },
  // Equipamentos Domésticos: dados ainda não carregados (load_censo_equipamentos.py pendente)
  // {
  //   label: "Equipamentos Domésticos (Censo 2022)",
  //   opcoes: pct_geladeira, pct_ar_condicionado, pct_freezer, pct_tv, etc.
  // },
  {
    label: "Demográfico (Censo 2022)",
    opcoes: [
      { value: "densidade_pop",               label: "Densidade demográfica (hab/km²)" },
      { value: "taxa_envelhecimento",         label: "Índice de envelhecimento" },
      { value: "razao_sexo",                  label: "Razão de sexo (h/100 mulheres)" },
      { value: "idade_mediana",               label: "Idade mediana (anos)" },
      { value: "taxa_migracao",               label: "Imigração inter-municipal (%)" },
      { value: "media_filhos_mulher",         label: "Média de filhos por mulher 12+ (fecundidade acumulada)" },
    ],
  },
  {
    label: "Mercado de Trabalho (Censo 2022)",
    opcoes: [
      { value: "taxa_desemprego",              label: "Taxa de desemprego — 14+ (%)" },
      { value: "taxa_informalidade",           label: "Informalidade no trabalho (%)" },
      { value: "taxa_pendular",                label: "Pendularidade laboral — trabalha em outro município (%)" },
    ],
  },
  {
    label: "Raça e Etnia (Censo 2022)",
    opcoes: [
      { value: "pct_indigena",                label: "Pop. indígena (autodeclarada) (%)" },
      { value: "pct_quilombola",              label: "Pop. quilombola (%)" },
    ],
  },
  {
    label: "Agropecuário (Censo 2017)",
    opcoes: [
      { value: "pct_agrofamiliar",            label: "Agricultura familiar — % estabelecimentos" },
      { value: "pct_mecanizado",              label: "Estabelecimentos com tratores (%)" },
      { value: "pct_financiamento",           label: "Estabelecimentos com financiamento (%)" },
    ],
  },
];

const CID10_CAPITULOS = [
  { value: "",         label: "Todas as causas" },
  // Doenças crônicas não transmissíveis
  { value: "I",        label: "Cardiovascular (I)" },
  { value: "C",        label: "Neoplasias / Câncer (C)" },
  { value: "J",        label: "Respiratório (J)" },
  { value: "E",        label: "Diabetes / Endócrinas (E)" },
  { value: "K",        label: "Digestivo / Cirrose (K)" },
  { value: "N",        label: "Renal / Urológico (N)" },
  { value: "G",        label: "Neurológico — Alzheimer, Parkinson (G)" },
  // Doenças infecciosas e parasitárias
  { value: "B",        label: "Infecciosas — HIV, Hepatite, Dengue (B)" },
  { value: "A",        label: "Infecciosas — Tuberculose, Cólera (A)" },
  // Causas externas e violência
  { value: "suicidio", label: "Suicídio (X60–X84)" },
  { value: "V",        label: "Acidentes de transporte (V)" },
  { value: "W",        label: "Quedas / Afogamentos / Acidentes (W)" },
  { value: "X",        label: "Causas externas diversas (X)" },
  { value: "Y",        label: "Causas ext. indeterminadas (Y)" },
  // Populações específicas
  { value: "O",        label: "Mortalidade materna (O)" },
  { value: "P",        label: "Perinatais / Neonatais (P)" },
  { value: "F",        label: "Transtornos mentais (F)" },
  { value: "Q",        label: "Malformações congênitas (Q)" },
];

const COR_RACA_OPCOES = [
  { value: null,  label: "Todas" },
  { value: 1,     label: "Branca" },
  { value: 2,     label: "Preta" },
  { value: 4,     label: "Parda" },
  { value: 5,     label: "Indígena" },
];

const SEXO_OPCOES = [
  { value: null, label: "Todos" },
  { value: "M",  label: "Masculino" },
  { value: "F",  label: "Feminino" },
];

// a demo estática só tem estados e municípios: os outros níveis dariam mapa vazio
const NIVEIS = DEMO ? ["NACIONAL", "ESTADUAL"] : ["NACIONAL", "ESTADUAL", "MUNICIPAL", "GEOLOCALIZACAO"];
const NIVEL_LABELS = {
  NACIONAL:       "Estadual",
  ESTADUAL:       "Municipal",
  MUNICIPAL:      "Setores",
  GEOLOCALIZACAO: "Endereços",
};

// Slider duplo com dois thumbs na mesma linha
function DualRangeSlider({ minVal, maxVal, onChange }) {
  const pMin = (minVal / 17) * 100;
  const pMax = (maxVal / 17) * 100;
  return (
    <div className="dual-range">
      <div className="dual-range__track" />
      <div className="dual-range__active" style={{ left: `${pMin}%`, width: `${pMax - pMin}%` }} />
      <input
        type="range" min={0} max={17} step={1}
        aria-label="Faixa etária mínima"
        value={minVal}
        data-on-top={minVal >= maxVal ? "true" : undefined}
        onChange={e => onChange([Math.min(Number(e.target.value), maxVal), maxVal])}
      />
      <input
        type="range" min={0} max={17} step={1}
        aria-label="Faixa etária máxima"
        value={maxVal}
        data-on-top={minVal < maxVal ? "true" : undefined}
        onChange={e => onChange([minVal, Math.max(Number(e.target.value), minVal)])}
      />
    </div>
  );
}

export function PainelControles({
  nivelAtual,
  nivelForcado,
  zoom,
  filtros,
  onMetricaChange,
  onUFChange,
  onFaixaEtariaChange,
  onCorRacaChange,
  onSexoChange,
  onEspecieChange,
  onNivelChange,
}) {
  // no celular começa fechado: aberto, cobre a maior parte do mapa
  const [aberto, setAberto] = useState(() => window.innerWidth > 640);

  const meta = NIVEL_METADATA[nivelAtual];

  return (
    <div style={{
      position: "absolute",
      top: window.innerWidth > 640 ? 16 : 64,
      right: 16,
      width: "min(280px, calc(100vw - 32px))",
      background: "rgba(15,17,23,0.92)",
      border: "1px solid #2d3748",
      borderRadius: 12,
      overflow: "hidden",
      backdropFilter: "blur(12px)",
      boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
    }}>
      {/* Cabeçalho */}
      <div
        style={{
          padding: "12px 16px",
          borderBottom: "1px solid #2d3748",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          cursor: "pointer",
        }}
        onClick={() => setAberto(!aberto)}
        role="button"
        tabIndex={0}
        aria-expanded={aberto}
        onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setAberto(!aberto); } }}
      >
        <span style={{ fontWeight: 600, fontSize: 14 }}>
          {meta.icone} {meta.label}
        </span>
        <span style={{ fontSize: 12, color: "#718096" }}>
          zoom {zoom.toFixed(1)} {aberto ? "▲" : "▼"}
        </span>
      </div>

      {aberto && (
        <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 16 }}>

          {/* Seletor de nível / visão */}
          <div>
            <label style={{ fontSize: 11, color: "#a0aec0", display: "block", marginBottom: 6 }}>
              NÍVEL DE VISÃO
            </label>
            <div style={{ display: "flex", gap: 3 }}>
              {/* Botão Auto: restaura detecção por zoom */}
              <button
                onClick={() => onNivelChange(null)}
                title="Segue o zoom automaticamente"
                style={{
                  flex: "0 0 auto",
                  background: nivelForcado === null ? "#553c9a" : "#2d3748",
                  border: nivelForcado === null ? "1px solid #9f7aea" : "1px solid #4a5568",
                  borderRadius: 5,
                  color: nivelForcado === null ? "#e9d8fd" : "#718096",
                  fontSize: 9,
                  padding: "5px 8px",
                  cursor: "pointer",
                  fontWeight: nivelForcado === null ? 700 : 400,
                  textAlign: "center",
                  lineHeight: 1.3,
                }}
              >
                <div style={{ fontSize: 11 }}>⟳</div>
                <div>Auto</div>
              </button>

              {NIVEIS.map(nivel => {
                const ativo = nivelForcado === nivel;
                const semDados = !NIVEL_METADATA[nivel].temDados;
                return (
                  <button
                    key={nivel}
                    onClick={() => onNivelChange(nivel)}
                    aria-pressed={ativo}
                    title={semDados
                      ? `${NIVEL_METADATA[nivel].descricao} — dados não carregados`
                      : NIVEL_METADATA[nivel].descricao}
                    style={{
                      flex: 1,
                      background: ativo ? "#4299e1" : "#2d3748",
                      border: ativo ? "1px solid #63b3ed" : "1px solid #4a5568",
                      borderRadius: 5,
                      color: ativo ? "#fff" : semDados ? "#4a5568" : "#a0aec0",
                      fontSize: 9,
                      padding: "5px 2px",
                      cursor: "pointer",
                      fontWeight: ativo ? 700 : 400,
                      textAlign: "center",
                      lineHeight: 1.3,
                      opacity: semDados && !ativo ? 0.55 : 1,
                    }}
                  >
                    <div style={{ fontSize: 13 }}>{NIVEL_METADATA[nivel].icone}</div>
                    <div>{NIVEL_LABELS[nivel]}</div>
                  </button>
                );
              })}
            </div>

            {/* Aviso quando nível ativo não tem dados carregados */}
            {!NIVEL_METADATA[nivelAtual].temDados && (
              <div style={{
                marginTop: 6,
                padding: "5px 8px",
                background: "rgba(237,137,54,0.12)",
                border: "1px solid rgba(237,137,54,0.3)",
                borderRadius: 5,
                fontSize: 10,
                color: "#ed8936",
              }}>
                ⚠ Dados de {NIVEL_METADATA[nivelAtual].label.toLowerCase()} não carregados
              </div>
            )}
          </div>

          {/* Seletor de métrica */}
          <div>
            <label style={{ fontSize: 11, color: "#a0aec0", display: "block", marginBottom: 4 }}>
              INDICADOR
            </label>
            <select
              aria-label="Indicador"
              value={filtros.metrica}
              onChange={e => onMetricaChange(e.target.value)}
              style={selectStyle}
            >
              {GRUPOS_METRICAS.map(grupo => (
                <optgroup key={grupo.label} label={grupo.label}>
                  {grupo.opcoes.map(m => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>

          {/* Ano */}
          <div>
            <label style={{ fontSize: 11, color: "#a0aec0", display: "block", marginBottom: 4 }}>
              ANO
            </label>
            <select
              aria-label="Ano"
              value={filtros.ano}
              onChange={e => filtros.setAno(Number(e.target.value))}
              style={selectStyle}
            >
              {(filtros.anosDisponiveis[filtros.metrica] ?? [2023]).map(a => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </div>

          {/* Filtro por UF */}
          <div>
            <label style={{ fontSize: 11, color: "#a0aec0", display: "block", marginBottom: 4 }}>
              ESTADO (UF)
            </label>
            <select
              aria-label="Estado (UF)"
              value={filtros.cod_uf ?? ""}
              onChange={e => onUFChange(e.target.value ? Number(e.target.value) : null)}
              style={selectStyle}
            >
              <option value="">Todos os estados</option>
              {UFS_BRASIL.map(uf => (
                <option key={uf.cod} value={uf.cod}>{uf.sigla} — {uf.nome}</option>
              ))}
            </select>
          </div>

          {/* Causa de morte (apenas quando métrica de saúde) */}
          {/* a demo foi extraída com os filtros padrão: causa, sexo, raça e idade não existem nela.
              Mostrá-los trocava a escala sem trocar o valor, e o mapa saía errado com cara de certo. */}
          {DEMO && METRICAS_SAUDE.includes(filtros.metrica) && (
            <div style={{ fontSize: 11, color: "#a0aec0", lineHeight: 1.4 }}>
              Filtros por causa, sexo, cor/raça e idade só existem no painel completo.
            </div>
          )}

          {!DEMO && ["taxa_mortalidade"].includes(filtros.metrica) && (
            <div>
              <label style={{ fontSize: 11, color: "#a0aec0", display: "block", marginBottom: 4 }}>
                CAUSA (CID-10)
              </label>
              <select
                aria-label="Causa (CID-10)"
                value={filtros.cid10_capitulo ?? ""}
                onChange={e => filtros.setCID10(e.target.value || null)}
                style={selectStyle}
              >
                {CID10_CAPITULOS.map(c => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </select>
            </div>
          )}

          {/* Filtros demográficos — para todas as métricas de saúde com microdados */}
          {!DEMO && METRICAS_SAUDE.includes(filtros.metrica) && (<>

            {/* Sexo */}
            <div>
              <label style={{ fontSize: 11, color: "#a0aec0", display: "block", marginBottom: 4 }}>
                SEXO
              </label>
              <div style={{ display: "flex", gap: 6 }}>
                {SEXO_OPCOES.map(op => (
                  <button
                    key={String(op.value)}
                    onClick={() => onSexoChange(op.value)}
                    style={{
                      ...chipStyle,
                      background: filtros.sexo === op.value ? "#4299e1" : "#2d3748",
                      color: filtros.sexo === op.value ? "#fff" : "#a0aec0",
                    }}
                  >
                    {op.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Cor/Raça */}
            <div>
              <label style={{ fontSize: 11, color: "#a0aec0", display: "block", marginBottom: 4 }}>
                COR / RAÇA
              </label>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {COR_RACA_OPCOES.map(op => (
                  <button
                    key={String(op.value)}
                    onClick={() => onCorRacaChange(op.value)}
                    style={{
                      ...chipStyle,
                      background: filtros.cor_raca === op.value ? "#4299e1" : "#2d3748",
                      color: filtros.cor_raca === op.value ? "#fff" : "#a0aec0",
                    }}
                  >
                    {op.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Faixa etária */}
            <div>
              <label style={{ fontSize: 11, color: "#a0aec0", display: "block", marginBottom: 4 }}>
                FAIXA ETÁRIA — {faixaLabel(filtros.faixa_etaria_min)} a {faixaLabel(filtros.faixa_etaria_max)}
              </label>
              <DualRangeSlider
                minVal={filtros.faixa_etaria_min}
                maxVal={filtros.faixa_etaria_max}
                onChange={onFaixaEtariaChange}
              />
            </div>

          </>)}

          {/* Tipo de endereço — apenas no nível GEOLOCALIZACAO */}
          {nivelAtual === "GEOLOCALIZACAO" && (
            <div>
              <label style={{ fontSize: 11, color: "#a0aec0", display: "block", marginBottom: 4 }}>
                TIPO DE ENDEREÇO
              </label>
              <div style={{ display: "flex", gap: 6 }}>
                {[{ v: null, l: "Todos" }, { v: 1, l: "Residencial" }, { v: 2, l: "Coletivo" }].map(op => (
                  <button
                    key={String(op.v)}
                    onClick={() => onEspecieChange(op.v)}
                    style={{
                      ...chipStyle,
                      background: filtros.especie === op.v ? "#4299e1" : "#2d3748",
                      color: filtros.especie === op.v ? "#fff" : "#a0aec0",
                    }}
                  >
                    {op.l}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Reset */}
          <button
            onClick={filtros.resetFiltros}
            style={{
              background: "transparent",
              border: "1px solid #4a5568",
              borderRadius: 6,
              color: "#718096",
              fontSize: 12,
              padding: "6px 12px",
              cursor: "pointer",
            }}
          >
            Limpar filtros
          </button>

        </div>
      )}
    </div>
  );
}

// Converte índice de faixa (0-17) para label legível
function faixaLabel(idx) {
  const faixas = [
    "<1a","1-4","5-9","10-14","15-19","20-24","25-29","30-34",
    "35-39","40-44","45-49","50-54","55-59","60-64","65-69","70-74","75-79","80+"
  ];
  return faixas[idx] ?? idx;
}

const selectStyle = {
  width: "100%",
  background: "#2d3748",
  border: "1px solid #4a5568",
  borderRadius: 6,
  color: "#e2e8f0",
  padding: "6px 8px",
  fontSize: 13,
};

const chipStyle = {
  border: "none",
  borderRadius: 4,
  padding: "4px 8px",
  fontSize: 11,
  cursor: "pointer",
  transition: "background 0.15s",
};
