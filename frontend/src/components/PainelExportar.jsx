/**
 * PainelExportar.jsx
 * Painel completo de exportacao de cartas tematicas com preview ao vivo.
 * Estilo do mapa (claro/escuro/satelite), proporcao, elementos, texto.
 */

import React, { useState, useRef, useEffect, useCallback } from "react";

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

function ToggleRow({ label, subLabel, checked, onChange }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
      <div style={{ flex: 1, minWidth: 0 }}>
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
      marginTop: 14, marginBottom: 8, paddingTop: 10, borderTop: "1px solid #2d3748",
    }}>
      {titulo}
    </div>
  );
}

const FORMATOS = [
  { id: "carta", label: "Carta",     icon: "\ud83d\uddfa\ufe0f" },
  { id: "png",   label: "PNG",       icon: "\ud83d\uddbc\ufe0f" },
  { id: "pdf",   label: "PDF",       icon: "\ud83d\udcc4" },
  { id: "instagram", label: "Insta", icon: "\ud83d\udcf1" },
];

const ESTILOS_MAPA = [
  { id: "claro",    label: "Claro",     icon: "\u2600\ufe0f",
    preview: "linear-gradient(135deg, #e8e6df 0%, #d6dbc8 40%, #b8d4e8 100%)" },
  { id: "escuro",   label: "Escuro",    icon: "\ud83c\udf19",
    preview: "linear-gradient(135deg, #0d0f16 0%, #181c28 40%, #14171f 100%)" },
  { id: "satelite", label: "Satelite",  icon: "\ud83d\udef0\ufe0f",
    preview: "linear-gradient(135deg, #1a3a20 0%, #2a4a35 40%, #1a2a40 100%)" },
];

const PROPORCOES = [
  { id: "auto", label: "Auto" },
  { id: "4:3",  label: "4:3" },
  { id: "1:1",  label: "1:1" },
  { id: "3:4",  label: "3:4" },
  { id: "16:9", label: "16:9" },
];

const inputStyle = {
  width: "100%",
  background: "#1a202c",
  border: "1px solid #2d3748",
  borderRadius: 5,
  color: "#e2e8f0",
  padding: "6px 8px",
  fontSize: 12,
  outline: "none",
  resize: "vertical",
  fontFamily: "inherit",
};

// ── Componente principal ──────────────────────────────────────────────────────

export function PainelExportar({ onReport, getCartaBaseOpts, gerarPreview }) {
  const [aberto, setAberto] = useState(false);
  const [btnHover, setBtnHover] = useState(false);
  const [exportando, setExportando] = useState(false);

  // Config
  const [formatoSel, setFormatoSel] = useState("carta");
  const [estiloMapa, setEstiloMapa] = useState("escuro");
  const [proporcao, setProporcao] = useState("auto");
  const [tituloCustom, setTituloCustom] = useState("");
  const [textoExplicativo, setTextoExplicativo] = useState("");

  // Elementos
  const [mostrarDestaque, setMostrarDestaque] = useState(true);
  const [mostrarLocalizador, setMostrarLocalizador] = useState(true);
  const [mostrarLegenda, setMostrarLegenda] = useState(true);
  const [mostrarNorte, setMostrarNorte] = useState(true);
  const [mostrarCoordenadas, setMostrarCoordenadas] = useState(true);
  const [mostrarDescricao, setMostrarDescricao] = useState(true);

  // Preview
  const previewRef = useRef(null);
  const debounceRef = useRef(null);
  const [previewVer, setPreviewVer] = useState(0);
  const [previewPronto, setPreviewPronto] = useState(false);

  const isCarta = formatoSel === "carta";

  const opcoes = {
    estiloMapa,
    proporcao,
    tituloCustom: tituloCustom.trim() || undefined,
    textoExplicativo: textoExplicativo.trim() || undefined,
    mostrarDestaque,
    mostrarLocalizador,
    mostrarLegenda,
    mostrarNorte,
    mostrarCoordenadas,
    mostrarDescricao,
  };

  // ── Preview ao vivo ──
  const atualizarPreview = useCallback(() => {
    if (!aberto || !isCarta || !gerarPreview || !getCartaBaseOpts) return;
    const baseOpts = getCartaBaseOpts();
    if (!baseOpts) return;

    const tema = estiloMapa === "claro" ? "claro" : "escuro";
    const canvas = gerarPreview({
      ...baseOpts,
      ...opcoes,
      tema,
      formato: "carta",
    }, 252);

    const container = previewRef.current;
    if (!container) return;
    if (!canvas) return;

    // Substituir canvas existente
    const prev = container.querySelector("canvas");
    if (prev) container.removeChild(prev);

    canvas.style.width = "100%";
    canvas.style.height = "auto";
    canvas.style.borderRadius = "6px";
    canvas.style.display = "block";
    container.appendChild(canvas);
    setPreviewPronto(true);
  }, [aberto, isCarta, gerarPreview, getCartaBaseOpts,
      estiloMapa, proporcao, tituloCustom, textoExplicativo,
      mostrarDestaque, mostrarLocalizador, mostrarLegenda,
      mostrarNorte, mostrarCoordenadas, mostrarDescricao]);

  // Debounce preview updates
  useEffect(() => {
    if (!aberto || !isCarta) return;
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(atualizarPreview, 200);
    return () => clearTimeout(debounceRef.current);
  }, [atualizarPreview, aberto, isCarta, previewVer]);

  // Atualizar preview quando o painel abre / resetar ao fechar
  useEffect(() => {
    if (aberto && isCarta) {
      setPreviewPronto(false);
      setPreviewVer(v => v + 1);
    }
  }, [aberto]);

  const executarExport = async () => {
    setExportando(true);
    try {
      await onReport(formatoSel, opcoes);
    } finally {
      setExportando(false);
      // Atualizar preview apos export (mapa pode ter mudado)
      setTimeout(() => setPreviewVer(v => v + 1), 500);
    }
  };

  return (
    <div style={{ position: "absolute", left: 60, bottom: 60, zIndex: 10, userSelect: "none" }}>

      {aberto && (
        <div style={{
          background: "rgba(13,15,22,0.95)",
          border: "1px solid #2d3748",
          borderRadius: 10,
          padding: "14px 14px 12px",
          backdropFilter: "blur(14px)",
          width: 280,
          marginBottom: 8,
          boxShadow: "0 8px 32px rgba(0,0,0,0.6)",
          maxHeight: "calc(100vh - 140px)",
          overflowY: "auto",
        }}>

          {/* ── Header ── */}
          <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            marginBottom: 14,
          }}>
            <div style={{ fontSize: 10, color: "#4a5568", letterSpacing: "0.10em", textTransform: "uppercase" }}>
              Exportar
            </div>
            {exportando && (
              <div style={{ fontSize: 10, color: "#4299e1", letterSpacing: "0.04em" }}>
                Preparando mapa...
              </div>
            )}
          </div>

          {/* ── Preview ao vivo ── */}
          {isCarta && (
            <>
              <div
                ref={previewRef}
                onClick={() => setPreviewVer(v => v + 1)}
                title="Clique para atualizar o preview"
                style={{
                  width: "100%",
                  minHeight: previewPronto ? undefined : 100,
                  background: "#0a0c14",
                  borderRadius: 6,
                  border: "1px solid #2d3748",
                  marginBottom: 6,
                  cursor: "pointer",
                  overflow: "hidden",
                  display: previewPronto ? "block" : "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                {!previewPronto && (
                  <div style={{ fontSize: 10, color: "#4a5568", padding: 12, textAlign: "center" }}>
                    Carregando preview...
                  </div>
                )}
              </div>
              <div style={{ fontSize: 9, color: "#4a5568", marginBottom: 10, textAlign: "center" }}>
                Clique no preview para atualizar
              </div>
            </>
          )}

          {/* ── Formato (compacto, linha unica) ── */}
          <div style={{ display: "flex", gap: 4 }}>
            {FORMATOS.map(f => {
              const ativo = formatoSel === f.id;
              return (
                <button
                  key={f.id}
                  onClick={() => setFormatoSel(f.id)}
                  style={{
                    flex: 1, padding: "6px 2px", borderRadius: 6, cursor: "pointer",
                    background: ativo ? "rgba(66,153,225,0.12)" : "transparent",
                    border: "1px solid " + (ativo ? "#4299e1" : "#2d3748"),
                    transition: "all 0.15s", textAlign: "center",
                  }}
                >
                  <div style={{ fontSize: 14 }}>{f.icon}</div>
                  <div style={{ fontSize: 9, color: ativo ? "#63b3ed" : "#718096", marginTop: 2, fontWeight: ativo ? 600 : 400 }}>
                    {f.label}
                  </div>
                </button>
              );
            })}
          </div>

          {/* ── Estilo do mapa (afeta basemap + frame) ── */}
          <Secao titulo="Estilo do mapa" />
          <div style={{ display: "flex", gap: 6 }}>
            {ESTILOS_MAPA.map(e => {
              const ativo = estiloMapa === e.id;
              return (
                <button
                  key={e.id}
                  onClick={() => setEstiloMapa(e.id)}
                  style={{
                    flex: 1, padding: 0, borderRadius: 8, cursor: "pointer",
                    border: "2px solid " + (ativo ? "#4299e1" : "#2d3748"),
                    transition: "all 0.15s", overflow: "hidden",
                    background: "transparent",
                    boxShadow: ativo ? "0 0 0 1px rgba(66,153,225,0.3)" : "none",
                  }}
                >
                  {/* Mini preview do basemap */}
                  <div style={{
                    height: 36, background: e.preview,
                    display: "flex", alignItems: "center", justifyContent: "center",
                  }}>
                    <span style={{ fontSize: 16 }}>{e.icon}</span>
                  </div>
                  <div style={{
                    fontSize: 10, padding: "4px 0",
                    color: ativo ? "#e2e8f0" : "#718096",
                    fontWeight: ativo ? 600 : 400,
                    background: "rgba(13,15,22,0.8)",
                  }}>
                    {e.label}
                  </div>
                </button>
              );
            })}
          </div>
          <div style={{ fontSize: 10, color: "#4a5568", marginTop: 5, lineHeight: 1.4 }}>
            {estiloMapa === "claro" && "Basemap claro com moldura clara. Ideal para impressao."}
            {estiloMapa === "escuro" && "Basemap escuro com moldura escura. Visual do painel."}
            {estiloMapa === "satelite" && "Imagem de satelite Esri. Moldura escura."}
          </div>

          {/* ── Opcoes da carta ── */}
          {isCarta && (
            <>
              {/* Proporcao do mapa */}
              <Secao titulo="Proporcao do mapa" />
              <div style={{ display: "flex", gap: 4 }}>
                {PROPORCOES.map(p => {
                  const ativo = proporcao === p.id;
                  return (
                    <button
                      key={p.id}
                      onClick={() => setProporcao(p.id)}
                      style={{
                        flex: 1, padding: "5px 2px", borderRadius: 5, cursor: "pointer",
                        background: ativo ? "rgba(66,153,225,0.12)" : "transparent",
                        border: "1px solid " + (ativo ? "#4299e1" : "#2d3748"),
                        color: ativo ? "#63b3ed" : "#718096",
                        fontSize: 11, fontWeight: ativo ? 600 : 400,
                        transition: "all 0.15s",
                      }}
                    >
                      {p.label}
                    </button>
                  );
                })}
              </div>
              <div style={{ fontSize: 10, color: "#4a5568", marginTop: 4 }}>
                {proporcao === "auto" && "Usa a proporcao atual da tela"}
                {proporcao === "4:3" && "Paisagem classica \u2014 elimina laterais"}
                {proporcao === "1:1" && "Quadrado \u2014 corte central"}
                {proporcao === "3:4" && "Retrato \u2014 corte lateral maximo"}
                {proporcao === "16:9" && "Panoramico \u2014 faixa horizontal"}
              </div>

              {/* Elementos visiveis */}
              <Secao titulo="Elementos" />
              <ToggleRow label="Destaque (callout)" subLabel="Valor do municipio selecionado" checked={mostrarDestaque} onChange={setMostrarDestaque} />
              <ToggleRow label="Mapa localizador" subLabel="Mini-mapa quando filtrado por UF" checked={mostrarLocalizador} onChange={setMostrarLocalizador} />
              <ToggleRow label="Legenda" subLabel="Classes de cores e valores" checked={mostrarLegenda} onChange={setMostrarLegenda} />
              <ToggleRow label="Norte e escala" subLabel="Rosa dos ventos e barra de escala" checked={mostrarNorte} onChange={setMostrarNorte} />
              <ToggleRow label="Coordenadas" subLabel="Lat/lon e datum no rodape" checked={mostrarCoordenadas} onChange={setMostrarCoordenadas} />
              <ToggleRow label="Descricao" subLabel="Texto explicativo abaixo da legenda" checked={mostrarDescricao} onChange={setMostrarDescricao} />

              {/* Texto customizado */}
              <Secao titulo="Texto" />
              <div style={{ marginBottom: 8 }}>
                <label style={{ fontSize: 10, color: "#718096", display: "block", marginBottom: 3 }}>
                  Titulo (vazio = automatico)
                </label>
                <input
                  type="text"
                  value={tituloCustom}
                  onChange={e => setTituloCustom(e.target.value)}
                  placeholder="Ex: Mortalidade por COVID-19 em SP"
                  style={inputStyle}
                />
              </div>
              <div>
                <label style={{ fontSize: 10, color: "#718096", display: "block", marginBottom: 3 }}>
                  Texto explicativo (opcional)
                </label>
                <textarea
                  value={textoExplicativo}
                  onChange={e => setTextoExplicativo(e.target.value)}
                  placeholder="Substitui a descricao automatica..."
                  rows={2}
                  style={{ ...inputStyle, minHeight: 42 }}
                />
              </div>
            </>
          )}

          {/* ── Dicas ── */}
          {estiloMapa !== "satelite" && (
            <div style={{ fontSize: 10, color: "#4a5568", marginTop: 12, lineHeight: 1.4 }}>
              Nomes de cidades aparecem automaticamente na exportacao.
            </div>
          )}
          {estiloMapa === "satelite" && (
            <div style={{ fontSize: 10, color: "#ed8936", marginTop: 12, lineHeight: 1.4 }}>
              Satelite pode falhar por CORS. Se o mapa sair preto, use Claro ou Escuro.
            </div>
          )}

          {/* ── Botao exportar ── */}
          <button
            onClick={executarExport}
            disabled={exportando}
            style={{
              width: "100%", marginTop: 12, padding: "10px 0",
              borderRadius: 6, cursor: exportando ? "wait" : "pointer",
              background: exportando ? "#2d3748" : "linear-gradient(135deg, #4299e1 0%, #3182ce 100%)",
              border: "none", color: "#fff", fontSize: 13, fontWeight: 600,
              letterSpacing: "0.02em", transition: "all 0.2s",
              boxShadow: exportando ? "none" : "0 2px 8px rgba(66,153,225,0.3)",
              opacity: exportando ? 0.7 : 1,
            }}
          >
            {exportando ? "Preparando mapa..." : "Exportar"}
          </button>
        </div>
      )}

      <button
        onClick={() => setAberto(v => !v)}
        onMouseEnter={() => setBtnHover(true)}
        onMouseLeave={() => setBtnHover(false)}
        title={aberto ? "Fechar exportacao" : "Exportar carta"}
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
        {"\ud83d\udce4"}
      </button>
    </div>
  );
}
