/**
 * PainelControles.jsx
 * Painel lateral com controles de filtro multidimensional.
 * Filtros grossos (ano, UF, CID10) → disparam nova requisição de tiles.
 * Filtros finos (sliders) → atualizam apenas o filterRange da GPU.
 */

import React, { useState } from "react";
import { NIVEL_METADATA } from "../layers/semantic_zoom.js";
import { METRICAS_SAUDE } from "../filters/cross_filter.js";
import "./RangeSlider.css";

// 27 UFs em ordem alfabética de sigla
const UFS_BRASIL = [
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

const METRICAS = [
  // Saúde
  { value: "taxa_mortalidade",            label: "Taxa de mortalidade" },
  { value: "taxa_homicidio",              label: "Taxa de homicídio" },
  // Economia
  { value: "pib_per_capita",              label: "PIB per capita" },
  { value: "receita_per_capita",          label: "Receita municipal per capita" },
  { value: "despesa_saude_per_capita",    label: "Gasto em saúde per capita" },
  { value: "despesa_educacao_per_capita", label: "Gasto em educação per capita" },
  // Demográfico
  { value: "densidade_pop",               label: "Densidade demográfica" },
];

const CID10_CAPITULOS = [
  { value: "",  label: "Todas as causas" },
  { value: "I", label: "Cardiovasculares (CID I)" },
  { value: "J", label: "Respiratórias (CID J)" },
  { value: "C", label: "Neoplasias (CID C)" },
  { value: "E", label: "Diabetes / Endócrinas (CID E)" },
  { value: "F", label: "Transtornos mentais (CID F)" },
  { value: "X", label: "Causas externas (CID X)" },
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

const NIVEIS = ["NACIONAL", "ESTADUAL", "MUNICIPAL", "GEOLOCALIZACAO"];
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
        value={minVal}
        data-on-top={minVal >= maxVal ? "true" : undefined}
        onChange={e => onChange([Math.min(Number(e.target.value), maxVal), maxVal])}
      />
      <input
        type="range" min={0} max={17} step={1}
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
  const [aberto, setAberto] = useState(true);

  const meta = NIVEL_METADATA[nivelAtual];

  return (
    <div style={{
      position: "absolute",
      top: 16,
      right: 16,
      width: 280,
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
              value={filtros.metrica}
              onChange={e => onMetricaChange(e.target.value)}
              style={selectStyle}
            >
              {METRICAS.map(m => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          </div>

          {/* Ano */}
          <div>
            <label style={{ fontSize: 11, color: "#a0aec0", display: "block", marginBottom: 4 }}>
              ANO
            </label>
            <select
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
          {["taxa_mortalidade"].includes(filtros.metrica) && (
            <div>
              <label style={{ fontSize: 11, color: "#a0aec0", display: "block", marginBottom: 4 }}>
                CAUSA (CID-10)
              </label>
              <select
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
          {METRICAS_SAUDE.includes(filtros.metrica) && (<>

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
