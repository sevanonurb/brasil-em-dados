/**
 * Legenda.jsx
 * Barra de cor coroplética com escala min/max para o painel principal.
 */

import React from "react";

const METRICAS_LABELS = {
  taxa_mortalidade:            "Mortalidade geral (por 100k hab.)",
  taxa_homicidio:              "Homicídios (por 100k hab.)",
  mortalidade_cardiovascular:  "Mortalidade cardiovascular (por 100k hab.)",
  mortalidade_cancer:          "Mortalidade por câncer (por 100k hab.)",
  mortalidade_respiratoria:    "Mortalidade respiratória (por 100k hab.)",
  pib_per_capita:              "PIB per capita",
  receita_per_capita:          "Receita municipal per capita",
  despesa_saude_per_capita:    "Gasto em saúde per capita",
  despesa_educacao_per_capita: "Gasto em educação per capita",
  densidade_pop:               "Densidade demográfica (hab/km²)",
};

const METRICAS_REAIS = new Set([
  "pib_per_capita", "receita_per_capita",
  "despesa_saude_per_capita", "despesa_educacao_per_capita",
]);

function formatarValor(v, metrica) {
  if (v == null) return "—";
  const n = Number(v);
  if (METRICAS_REAIS.has(metrica)) {
    return "R$\u00a0" + n.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
  }
  return n.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
}

const METRICAS_SAUDE_SET = new Set([
  "taxa_mortalidade", "taxa_homicidio",
  "mortalidade_cardiovascular", "mortalidade_cancer", "mortalidade_respiratoria",
]);

export function Legenda({ metrica, min, max, semDados = false }) {
  const label = METRICAS_LABELS[metrica] ?? metrica;
  const legendaMeio = METRICAS_SAUDE_SET.has(metrica) ? "↑ maior risco"
    : metrica === "densidade_pop" ? "↑ mais denso"
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
