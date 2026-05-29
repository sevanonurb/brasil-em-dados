/**
 * PainelVisual.jsx
 * Painel de controles visuais: estilo do mapa, rótulos, bordas,
 * comparação lado-a-lado, ferramentas e navegação.
 */

import React, { useState } from "react";
import { GRUPOS_METRICAS } from "./PainelControles.jsx";

// ── Componentes internos ──────────────────────────────────────────────────────

function Toggle({ checked, onChange }) {
  return (
    <div
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      style={{
        width: 36, height: 20, borderRadius: 10, cursor: "pointer",
        background: checked ? "#4299e1" : "#2d3748",
        position: "relative", transition: "background 0.2s", flexShrink: 0,
        border: "1px solid " + (checked ? "#4299e1" : "#4a5568"),
      }}
    >
      <div style={{
        position: "absolute",
        top: 2, left: checked ? 17 : 2,
        width: 14, height: 14, borderRadius: 7,
        background: checked ? "#fff" : "#a0aec0",
        transition: "left 0.18s",
        boxShadow: "0 1px 3px rgba(0,0,0,0.4)",
      }} />
    </div>
  );
}

function SliderRow({ label, value, min, max, step, onChange, badge, onBadgeClick }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
        <span style={{ fontSize: 11, color: "#718096", letterSpacing: "0.02em" }}>{label}</span>
        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
          {badge && (
            <button
              onClick={onBadgeClick}
              style={{
                fontSize: 9, padding: "1px 5px", borderRadius: 3, cursor: "pointer",
                background: "#1a202c", border: "1px solid #4a5568", color: "#718096",
                letterSpacing: "0.04em",
              }}
            >
              {badge}
            </button>
          )}
          <span style={{ fontSize: 11, color: "#e2e8f0", fontVariantNumeric: "tabular-nums", minWidth: 32, textAlign: "right" }}>
            {Math.round(value * 100)}%
          </span>
        </div>
      </div>
      <input
        type="range" min={min} max={max} step={step}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        style={{ width: "100%", height: 4, accentColor: "#4299e1", cursor: "pointer" }}
      />
    </div>
  );
}

function ToggleRow({ label, subLabel, checked, onChange }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 12, color: "#a0aec0" }}>{label}</div>
        {subLabel && <div style={{ fontSize: 10, color: "#4a5568", marginTop: 1 }}>{subLabel}</div>}
      </div>
      <Toggle checked={checked} onChange={onChange} />
    </div>
  );
}

function Secao({ titulo }) {
  return (
    <div style={{
      fontSize: 9, color: "#4a5568", letterSpacing: "0.10em", textTransform: "uppercase",
      marginTop: 12, marginBottom: 8, paddingTop: 10, borderTop: "1px solid #2d3748",
    }}>
      {titulo}
    </div>
  );
}

function BotaoNav({ label, onClick }) {
  const [hover, setHover] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        flex: 1, padding: "7px 4px", borderRadius: 6, cursor: "pointer", fontSize: 11,
        background: hover ? "#1e2a3a" : "#1a202c",
        border: "1px solid " + (hover ? "#4299e1" : "#2d3748"),
        color: hover ? "#e2e8f0" : "#a0aec0",
        transition: "all 0.15s", lineHeight: 1.3, textAlign: "center",
      }}
    >
      {label}
    </button>
  );
}

function BotaoIcone({ title, icon, onClick }) {
  const [hover, setHover] = useState(false);
  return (
    <button
      title={title}
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        flex: 1, padding: "6px 4px", borderRadius: 6, cursor: "pointer", fontSize: 13,
        background: hover ? "#1e2a3a" : "#1a202c",
        border: "1px solid " + (hover ? "#4299e1" : "#2d3748"),
        color: hover ? "#e2e8f0" : "#a0aec0",
        transition: "all 0.15s", textAlign: "center", lineHeight: 1,
      }}
    >
      <div>{icon}</div>
      <div style={{ fontSize: 9, marginTop: 2 }}>{title}</div>
    </button>
  );
}

const selectStyleMini = {
  width: "100%",
  background: "#2d3748",
  border: "1px solid #4a5568",
  borderRadius: 5,
  color: "#e2e8f0",
  padding: "4px 6px",
  fontSize: 11,
};

// ── Componente principal ──────────────────────────────────────────────────────

export function PainelVisual({
  visual, onUpdate, onFlyTo,
  comparacao, onComparacaoUpdate,
  onScreenshot, onReport, onFullscreen,
  anosDisponiveis,
}) {
  const [aberto, setAberto] = useState(false);
  const [btnHover, setBtnHover] = useState(false);

  const isBasemapManual = visual.opacidadeBasemap !== null;
  const basemapValue = isBasemapManual ? visual.opacidadeBasemap : 0.3;

  return (
    <div style={{ position: "absolute", left: 16, bottom: 60, zIndex: 10, userSelect: "none" }}>

      {aberto && (
        <div style={{
          background: "rgba(13,15,22,0.93)",
          border: "1px solid #2d3748",
          borderRadius: 10,
          padding: "14px 14px 12px",
          backdropFilter: "blur(14px)",
          width: 240,
          marginBottom: 8,
          boxShadow: "0 8px 32px rgba(0,0,0,0.6)",
          maxHeight: "calc(100vh - 140px)",
          overflowY: "auto",
        }}>

          <div style={{ fontSize: 10, color: "#4a5568", letterSpacing: "0.10em", textTransform: "uppercase", marginBottom: 14 }}>
            Controles Visuais
          </div>

          {/* ── Opacidade ── */}
          <SliderRow
            label="Opacidade — dados"
            value={visual.opacidadeOverlay}
            min={0} max={1} step={0.01}
            onChange={v => onUpdate("opacidadeOverlay", v)}
          />
          <SliderRow
            label="Opacidade — mapa base"
            value={basemapValue}
            min={0} max={1} step={0.01}
            onChange={v => onUpdate("opacidadeBasemap", v)}
            badge={isBasemapManual ? "manual" : "auto"}
            onBadgeClick={() => onUpdate("opacidadeBasemap", isBasemapManual ? null : 0.35)}
          />

          {/* ── Camadas do mapa ── */}
          <Secao titulo="Camadas" />
          <ToggleRow
            label="Ruas e estradas"
            subLabel="Vias sobrepostas ao indicador"
            checked={visual.mostrarRuas}
            onChange={v => onUpdate("mostrarRuas", v)}
          />
          {visual.mostrarRuas && (
            <SliderRow
              label="Opacidade — ruas"
              value={visual.opacidadeRuas ?? 0.5}
              min={0} max={1} step={0.01}
              onChange={v => onUpdate("opacidadeRuas", v)}
            />
          )}
          <ToggleRow
            label="Imagem de satélite"
            subLabel="Foto aérea por baixo dos dados"
            checked={visual.mostrarSatelite}
            onChange={v => onUpdate("mostrarSatelite", v)}
          />
          {visual.mostrarSatelite && (
            <SliderRow
              label="Opacidade — satélite"
              value={visual.opacidadeSatelite ?? 0.4}
              min={0} max={1} step={0.01}
              onChange={v => onUpdate("opacidadeSatelite", v)}
            />
          )}
          <ToggleRow
            label="Nomes das cidades"
            subLabel="Rótulos de municípios e localidades"
            checked={visual.mostrarNomes}
            onChange={v => onUpdate("mostrarNomes", v)}
          />

          {/* ── Bordas ── */}
          <Secao titulo="Bordas" />
          <ToggleRow
            label="Municípios"
            checked={visual.bordurasMunicipios}
            onChange={v => onUpdate("bordurasMunicipios", v)}
          />
          <ToggleRow
            label="Estados"
            checked={visual.bordurasEstados}
            onChange={v => onUpdate("bordurasEstados", v)}
          />

          {/* ── Comparação ── */}
          <Secao titulo="Comparação" />
          <ToggleRow
            label="Dividir mapa"
            subLabel="Compare dois indicadores lado a lado"
            checked={comparacao.ativo}
            onChange={v => onComparacaoUpdate("ativo", v)}
          />
          {comparacao.ativo && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 2 }}>
              <div>
                <label style={{ fontSize: 10, color: "#718096", display: "block", marginBottom: 2 }}>
                  Indicador (lado direito)
                </label>
                <select
                  value={comparacao.metrica}
                  onChange={e => onComparacaoUpdate("metrica", e.target.value)}
                  style={selectStyleMini}
                >
                  {GRUPOS_METRICAS.map(g => (
                    <optgroup key={g.label} label={g.label}>
                      {g.opcoes.map(m => (
                        <option key={m.value} value={m.value}>{m.label}</option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ fontSize: 10, color: "#718096", display: "block", marginBottom: 2 }}>
                  Ano (lado direito)
                </label>
                <select
                  value={comparacao.ano}
                  onChange={e => onComparacaoUpdate("ano", Number(e.target.value))}
                  style={selectStyleMini}
                >
                  {(anosDisponiveis?.[comparacao.metrica] ?? [2023, 2022]).map(a => (
                    <option key={a} value={a}>{a}</option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {/* ── Contexto ── */}
          <Secao titulo="Contexto" />
          <ToggleRow
            label="Continente sul-americano"
            subLabel="Mapa base em todos os zooms"
            checked={visual.mostrarSulAmerica}
            onChange={v => onUpdate("mostrarSulAmerica", v)}
          />

          {/* ── Ferramentas ── */}
          <Secao titulo="Ferramentas" />
          <ToggleRow
            label="Coordenadas"
            subLabel="Lat/lon ao mover o mouse"
            checked={visual.mostrarCoordenadas}
            onChange={v => onUpdate("mostrarCoordenadas", v)}
          />
          <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
            <BotaoIcone title="Captura" icon="📷" onClick={onScreenshot} />
            <BotaoIcone title="Tela cheia" icon="⛶" onClick={onFullscreen} />
          </div>

          {/* ── Exportar Report ── */}
          <Secao titulo="Exportar Carta" />
          <div style={{ fontSize: 10, color: "#4a5568", marginBottom: 6, lineHeight: 1.4 }}>
            Carta tematica ABNT com legenda, escala e metadados
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <BotaoIcone title="PNG" icon="🖼️" onClick={() => onReport?.("png")} />
            <BotaoIcone title="PDF" icon="📄" onClick={() => onReport?.("pdf")} />
            <BotaoIcone title="Instagram 4:5" icon="📱" onClick={() => onReport?.("instagram")} />
          </div>

          {/* ── Navegação ── */}
          <div style={{ display: "flex", gap: 6, marginTop: 14 }}>
            <BotaoNav label="Brasil" onClick={() => onFlyTo("brasil")} />
            <BotaoNav label="Sul América" onClick={() => onFlyTo("sul_america")} />
          </div>

        </div>
      )}

      <button
        onClick={() => setAberto(v => !v)}
        onMouseEnter={() => setBtnHover(true)}
        onMouseLeave={() => setBtnHover(false)}
        title={aberto ? "Fechar controles visuais" : "Controles visuais"}
        style={{
          background: aberto
            ? "rgba(66,153,225,0.15)"
            : btnHover ? "rgba(66,153,225,0.08)" : "rgba(13,15,22,0.92)",
          border: "1px solid " + (aberto ? "#4299e1" : btnHover ? "#4a6fa5" : "#2d3748"),
          borderRadius: 8,
          color: aberto ? "#63b3ed" : btnHover ? "#a0aec0" : "#718096",
          cursor: "pointer",
          fontSize: 15,
          padding: "6px 10px",
          lineHeight: 1,
          transition: "all 0.15s",
          backdropFilter: "blur(8px)",
          boxShadow: aberto ? "0 0 0 1px rgba(66,153,225,0.2)" : "none",
        }}
      >
        🎨
      </button>
    </div>
  );
}
