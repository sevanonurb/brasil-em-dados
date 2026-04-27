/**
 * Legenda.jsx
 * Barra de cor coroplética com escala min/max para o painel principal.
 */

import React from "react";

const METRICAS_LABELS = {
  taxa_mortalidade:   "Mortalidade geral (por 100k hab.)",
  taxa_homicidio:     "Homicídios (por 100k hab.)",
  pib_per_capita:     "PIB per capita",
  receita_per_capita: "Receita municipal per capita",
  densidade_pop:      "Densidade demográfica (hab/km²)",
};

function formatarValor(v, metrica) {
  if (v == null) return "—";
  const n = Number(v);
  if (metrica.includes("pib") || metrica.includes("receita")) {
    return "R$\u00a0" + n.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
  }
  return n.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
}

export function Legenda({ metrica, min, max, semDados = false }) {
  const label = METRICAS_LABELS[metrica] ?? metrica;

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
            <span style={{ color: "#4a5568" }}>↑ maior risco</span>
            <span>{formatarValor(max, metrica)}</span>
          </div>
        </>
      )}
    </div>
  );
}
