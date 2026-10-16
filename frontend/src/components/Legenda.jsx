/**
 * Legenda.jsx
 * Barra de cor coroplética com escala min/max para o painel principal.
 */

import React from "react";
import { METRICA_LABEL_LONGO, METRICAS_SAUDE_SET, formatarParaLegenda } from "../utils/metricas.js";

export function Legenda({ metrica, min, max, semDados = false, invertida = false, adaptativo = false }) {
  const label = METRICA_LABEL_LONGO[metrica] ?? metrica;

  // Rótulo central da legenda
  const legendaMeio = invertida
    ? "↑ melhor"
    : METRICAS_SAUDE_SET.has(metrica)
      ? "↑ maior risco"
      : (metrica === "densidade_pop" || metrica === "densidade_domiciliar")
        ? "↑ mais denso"
        : "↑ maior valor";

  // Gradiente CSS espelha RAMPA_COR de main.jsx (6 paradas)
  // Azul → Teal → Verde → Amarelo → Laranja → Violeta
  const rampaNormal = "linear-gradient(to right, rgb(40,130,255), rgb(0,210,190), rgb(100,230,50), rgb(255,220,0), rgb(255,65,15), rgb(175,20,220))";
  const gradiente = invertida
    ? "linear-gradient(to right, rgb(175,20,220), rgb(255,65,15), rgb(255,220,0), rgb(100,230,50), rgb(0,210,190), rgb(40,130,255))"
    : rampaNormal;

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
            <span>{formatarParaLegenda(min, metrica)}</span>
            <span style={{ color: "#4a5568" }}>{legendaMeio}</span>
            <span>{formatarParaLegenda(max, metrica)}</span>
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
