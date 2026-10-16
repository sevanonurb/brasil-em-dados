/**
 * BuscaMunicipio.jsx
 * Barra de busca por município com autocomplete e flyTo.
 */

import React, { useEffect, useRef, useState } from "react";

function normalizarTexto(s) {
  return s
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

export function BuscaMunicipio({ onFlyTo }) {
  const [query, setQuery] = useState("");
  const [municipios, setMunicipios] = useState([]);
  const [resultados, setResultados] = useState([]);
  const [focado, setFocado] = useState(false);
  const [idxAtivo, setIdxAtivo] = useState(-1);
  const inputRef = useRef(null);
  const listaRef = useRef(null);

  // Carrega lista de municípios uma vez
  useEffect(() => {
    const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:80";
    fetch(`${apiUrl}/api/municipios`)
      .then(r => r.ok ? r.json() : [])
      .then(data => setMunicipios(data))
      .catch(() => {});
  }, []);

  // Filtra conforme digitação
  useEffect(() => {
    if (!query || query.length < 2) {
      setResultados([]);
      setIdxAtivo(-1);
      return;
    }
    const q = normalizarTexto(query);
    const filtrados = municipios
      .filter(m => normalizarTexto(m.nome).includes(q) || normalizarTexto(m.uf).includes(q))
      .slice(0, 8);
    setResultados(filtrados);
    setIdxAtivo(-1);
  }, [query, municipios]);

  function selecionar(m) {
    setQuery("");
    setResultados([]);
    setFocado(false);
    onFlyTo({ longitude: m.lon, latitude: m.lat, zoom: 10 });
  }

  function handleKeyDown(e) {
    if (!resultados.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setIdxAtivo(i => Math.min(i + 1, resultados.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setIdxAtivo(i => Math.max(i - 1, -1));
    } else if (e.key === "Enter" && idxAtivo >= 0) {
      e.preventDefault();
      selecionar(resultados[idxAtivo]);
    } else if (e.key === "Escape") {
      setQuery("");
      setResultados([]);
      inputRef.current?.blur();
    }
  }

  const mostrarLista = focado && resultados.length > 0;

  return (
    <div style={{ position: "relative", width: 220 }}>
      <div style={{
        display: "flex",
        alignItems: "center",
        background: "rgba(15,17,23,0.90)",
        border: `1px solid ${focado ? "#4299e1" : "#2d3748"}`,
        borderRadius: mostrarLista ? "8px 8px 0 0" : 8,
        padding: "6px 10px",
        gap: 6,
        transition: "border-color 0.15s",
      }}>
        <span style={{ color: "#718096", fontSize: 13, userSelect: "none" }}>🔍</span>
        <input
          ref={inputRef}
          value={query}
          onChange={e => setQuery(e.target.value)}
          onFocus={() => setFocado(true)}
          onBlur={() => setTimeout(() => setFocado(false), 150)}
          onKeyDown={handleKeyDown}
          placeholder="Buscar município…"
          style={{
            flex: 1,
            background: "transparent",
            border: "none",
            outline: "none",
            color: "#e2e8f0",
            fontSize: 13,
            fontFamily: "inherit",
          }}
        />
        {query && (
          <button
            onClick={() => { setQuery(""); setResultados([]); inputRef.current?.focus(); }}
            style={{
              background: "none", border: "none", color: "#4a5568",
              cursor: "pointer", fontSize: 15, lineHeight: 1, padding: 0,
            }}
          >×</button>
        )}
      </div>

      {mostrarLista && (
        <div
          ref={listaRef}
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            background: "rgba(15,17,23,0.97)",
            border: "1px solid #2d3748",
            borderTop: "none",
            borderRadius: "0 0 8px 8px",
            overflow: "hidden",
            zIndex: 1000,
            boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
          }}
        >
          {resultados.map((m, i) => (
            <div
              key={m.cod}
              onMouseDown={() => selecionar(m)}
              style={{
                padding: "8px 12px",
                cursor: "pointer",
                background: i === idxAtivo ? "rgba(66,153,225,0.15)" : "transparent",
                borderBottom: i < resultados.length - 1 ? "1px solid #1a202c" : "none",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
              onMouseEnter={() => setIdxAtivo(i)}
            >
              <span style={{ color: "#e2e8f0", fontSize: 13 }}>{m.nome}</span>
              <span style={{
                fontSize: 11,
                color: "#4a5568",
                background: "#1a202c",
                borderRadius: 4,
                padding: "1px 5px",
                fontFamily: "monospace",
              }}>{m.uf}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
