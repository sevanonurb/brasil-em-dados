/**
 * PainelDetalhes.jsx
 * Painel lateral de drill-down: exibido ao clicar em uma feature do mapa.
 *
 * Campos disponíveis nos tiles (source-of-truth):
 *   UF (NACIONAL):    cod_uf, sigla, nome, regiao, populacao_total,
 *                     pib_estadual, receita_estadual_total, transferencias_sus_total, valor_metrica
 *   Município (ESTADUAL): cod_ibge_7, cod_uf, nome_municipio, populacao_2022,
 *                     transferencias_sus, valor_metrica
 */


const METRICA_LABEL = {
  taxa_mortalidade:            "Taxa de mortalidade",
  taxa_homicidio:              "Taxa de homicídio",
  mortalidade_cardiovascular:  "Mortalidade cardiovascular",
  mortalidade_cancer:          "Mortalidade por câncer",
  mortalidade_respiratoria:    "Mortalidade respiratória",
  pib_per_capita:              "PIB per capita",
  receita_per_capita:          "Receita municipal per capita",
  despesa_saude_per_capita:    "Gasto em saúde per capita",
  despesa_educacao_per_capita: "Gasto em educação per capita",
  densidade_pop:               "Densidade demográfica",
};

const METRICAS_REAIS = new Set([
  "pib_per_capita", "receita_per_capita",
  "despesa_saude_per_capita", "despesa_educacao_per_capita",
]);

function formatarMetrica(valor, metrica) {
  if (valor == null || valor === "") return null;
  const n = typeof valor === "number" ? valor : Number(valor);
  if (!isFinite(n)) return null;
  if (METRICAS_REAIS.has(metrica)) {
    return { texto: "R$\u00a0" + n.toLocaleString("pt-BR", { maximumFractionDigits: 0 }), unidade: "" };
  }
  if (metrica === "densidade_pop") {
    return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 1 }), unidade: "\u00a0hab/km²" };
  }
  return { texto: n.toLocaleString("pt-BR", { maximumFractionDigits: 1 }), unidade: "\u00a0/100k hab." };
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
    ? `${METRICA_LABEL[metrica] ?? metrica} — CID ${cid10}`
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
              <Metrica label="PIB (soma UF)" valor={p.pib_estadual} prefixo="R$\u00a0" decimais={0} />
              <Metrica label="Receita (soma UF)" valor={p.receita_estadual_total} prefixo="R$\u00a0" decimais={0} />
              <Metrica label="Transf. SUS" valor={p.transferencias_sus_total} prefixo="R$\u00a0" decimais={0} />
            </>
          ) : (
            <>
              <Metrica label="Transf. SUS" valor={p.transferencias_sus} prefixo="R$\u00a0" decimais={0} />
              <Metrica label="Gasto em saúde" valor={p.despesa_saude} prefixo="R$\u00a0" decimais={0} />
              <Metrica label="Gasto em educação" valor={p.despesa_educacao} prefixo="R$\u00a0" decimais={0} />
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
