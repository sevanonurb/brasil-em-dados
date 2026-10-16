/**
 * report.js — Gerador de cartas temáticas (PNG/PDF) do painel Brasil em Dados.
 *
 * PNG: Canvas 2D API nativo (raster a 2×).
 * PDF: Objetos vetoriais nativos ISO 32000-1 — texto (Helvetica Type1),
 *      linhas, retângulos e rampa como vetores; apenas o mapa é raster (JPEG).
 *
 * Conformidade: ABNT NBR 15777:2009, IBGE, ICA, Res. IBGE R.PR-01/2015.
 */

import { METRICA_LABEL_LONGO, METRICA_LABEL_CURTO, METRICAS_SAUDE_SET, formatarMetrica, formatarParaLegenda } from "./metricas.js";

// ── Rampa de cores (espelha RAMPA_COR de main.jsx) ──────────────────────────
const RAMPA = [
  [40, 130, 255],
  [0,  210, 190],
  [100, 230, 50],
  [255, 220, 0],
  [255, 65,  15],
  [175, 20, 220],
];

// ── Dados compartilhados ────────────────────────────────────────────────────

const UF_NOMES = {
  11:"RO",12:"AC",13:"AM",14:"RR",15:"PA",16:"AP",17:"TO",
  21:"MA",22:"PI",23:"CE",24:"RN",25:"PB",26:"PE",27:"AL",28:"SE",29:"BA",
  31:"MG",32:"ES",33:"RJ",35:"SP",41:"PR",42:"SC",43:"RS",
  50:"MS",51:"MT",52:"GO",53:"DF",
};
const UF_NOMES_COMPLETOS = {
  11:"Rondonia",12:"Acre",13:"Amazonas",14:"Roraima",15:"Para",16:"Amapa",17:"Tocantins",
  21:"Maranhao",22:"Piaui",23:"Ceara",24:"Rio Grande do Norte",25:"Paraiba",
  26:"Pernambuco",27:"Alagoas",28:"Sergipe",29:"Bahia",
  31:"Minas Gerais",32:"Espirito Santo",33:"Rio de Janeiro",35:"Sao Paulo",
  41:"Parana",42:"Santa Catarina",43:"Rio Grande do Sul",
  50:"Mato Grosso do Sul",51:"Mato Grosso",52:"Goias",53:"Distrito Federal",
};
const UF_CENTROIDS = {
  11:[-63.6,-10.9],12:[-70.5,-9.2],13:[-64.7,-3.5],14:[-61.4,2.1],
  15:[-52.5,-3.5],16:[-51.1,1.0],17:[-48.3,-10.2],
  21:[-45.3,-5.1],22:[-43.0,-7.7],23:[-39.3,-5.2],24:[-36.6,-5.8],
  25:[-36.6,-7.1],26:[-37.3,-8.3],27:[-36.6,-9.5],28:[-37.4,-10.6],29:[-41.7,-12.6],
  31:[-44.7,-18.5],32:[-40.7,-19.6],33:[-43.2,-22.2],35:[-49.3,-22.3],
  41:[-51.5,-24.6],42:[-50.5,-27.2],43:[-53.2,-29.8],
  50:[-54.8,-20.5],51:[-55.5,-12.7],52:[-49.6,-15.9],53:[-47.8,-15.8],
};
const BRASIL_CONTORNO = [
  [-34.8,-7.2],[-34.9,-8.0],[-35.2,-9.1],[-35.8,-9.9],[-36.4,-10.5],
  [-36.9,-10.8],[-37.4,-11.0],[-38.2,-12.0],[-38.9,-13.5],[-39.0,-14.5],
  [-39.1,-15.4],[-39.4,-16.5],[-39.7,-17.8],[-39.8,-18.8],[-40.0,-20.0],
  [-40.5,-21.0],[-41.0,-22.3],[-41.3,-22.5],[-41.9,-22.9],[-43.2,-23.0],
  [-44.6,-23.1],[-45.5,-23.5],[-46.5,-24.0],[-47.5,-24.5],[-48.5,-25.5],
  [-48.5,-27.0],[-48.6,-28.5],[-49.5,-29.0],[-50.3,-29.0],[-51.5,-30.5],
  [-52.0,-32.0],[-53.4,-33.7],[-55.0,-33.0],[-56.0,-32.0],[-57.6,-30.2],
  [-57.8,-28.0],[-58.0,-26.0],[-58.0,-24.0],[-57.9,-22.0],[-57.8,-20.0],
  [-57.9,-18.0],[-58.1,-16.6],[-59.5,-15.5],[-60.2,-15.0],[-60.8,-14.0],
  [-61.5,-13.5],[-62.5,-13.0],[-63.3,-12.5],[-64.5,-11.5],[-65.4,-10.0],
  [-66.5,-8.0],[-67.5,-5.5],[-68.5,-3.5],[-69.6,-1.7],[-70.0,0.0],
  [-69.9,1.7],[-68.5,1.8],[-67.0,1.8],[-65.0,2.5],[-63.0,3.5],
  [-61.0,4.5],[-60.5,5.2],[-58.0,5.0],[-55.0,4.5],[-52.5,4.2],
  [-51.5,4.1],[-50.0,2.0],[-48.5,0.0],[-47.0,-1.0],[-46.0,-2.5],
  [-44.5,-2.6],[-42.1,-2.8],[-40.5,-2.7],[-38.6,-3.6],[-37.0,-4.0],
  [-35.5,-5.0],[-35.0,-6.0],[-34.8,-7.2],
];
const COR_RACA_NOMES = { 1: "Branca", 2: "Preta", 4: "Parda", 5: "Indigena" };
const SEXO_NOMES = { M: "Masculino", F: "Feminino" };
const FAIXAS_LABELS = [
  "<1a","1-4","5-9","10-14","15-19","20-24","25-29","30-34","35-39",
  "40-44","45-49","50-54","55-59","60-64","65-69","70-74","75-79","80+",
];

// ── Helpers compartilhados ──────────────────────────────────────────────────

function interpolaRGB(t, invertida) {
  const v = invertida ? 1 - t : t;
  const s = v * (RAMPA.length - 1);
  const i = Math.min(Math.floor(s), RAMPA.length - 2);
  const f = s - i;
  const c0 = RAMPA[i], c1 = RAMPA[i + 1];
  return [
    Math.round(c0[0]+f*(c1[0]-c0[0])),
    Math.round(c0[1]+f*(c1[1]-c0[1])),
    Math.round(c0[2]+f*(c1[2]-c0[2])),
  ];
}

function metrosPorPixel(lat, zoom) {
  return 40_075_016.686 * Math.cos(lat * Math.PI / 180) / Math.pow(2, zoom + 8);
}

function calcularEscala(mpp, maxPx) {
  const maxDist = mpp * maxPx;
  const redondos = [1,2,5,10,20,50,100,200,500,1e3,2e3,5e3,1e4,2e4,5e4,1e5,2e5,5e5,1e6,2e6,5e6];
  let dist = 1;
  for (const r of redondos) { if (r <= maxDist) dist = r; else break; }
  const label = dist >= 1000 ? `${(dist/1000).toLocaleString("pt-BR")} km` : `${dist} m`;
  return { px: dist / mpp, m: dist, label };
}

function fmtCoord(v, tipo) {
  const a = Math.abs(v), g = Math.floor(a);
  const m = Math.floor((a - g) * 60);
  const s = Math.round(((a - g) * 60 - m) * 60);
  const d = tipo === "lat" ? (v >= 0 ? "N" : "S") : (v >= 0 ? "E" : "W");
  return `${g}\xB0${String(m).padStart(2,"0")}'${String(s).padStart(2,"0")}"${d}`;
}

function obterFonte(metrica) {
  if (metrica.startsWith("taxa_mortalidade") || metrica.startsWith("taxa_homicidio"))
    return ["SIM/DATASUS", "Sistema de Informacoes sobre Mortalidade"];
  if (metrica.startsWith("mortalidade_infantil") || metrica.startsWith("taxa_natalidade") || metrica === "taxa_obito_fetal")
    return ["SINASC/DATASUS", "Nascidos Vivos - Min. da Saude"];
  if (metrica.startsWith("pib_") || metrica.startsWith("pct_pib_"))
    return ["IBGE", "PIB dos Municipios"];
  if (metrica.startsWith("receita_") || metrica.startsWith("despesa_") || metrica.startsWith("divida_") || metrica === "despesa_pessoal_rcl")
    return ["SICONFI/STN", "Tesouro Nacional"];
  if (metrica.startsWith("incidencia_"))
    return ["SINAN/DATASUS", "Agravos de Notificacao"];
  if (metrica.startsWith("taxa_internacao") || metrica === "media_permanencia_sus")
    return ["SIH/DATASUS", "Informacoes Hospitalares"];
  if (metrica.startsWith("ideb_"))
    return ["INEP/MEC", "IDEB"];
  if (metrica.startsWith("taxa_aprovacao") || metrica.startsWith("taxa_reprovacao") || metrica.startsWith("taxa_abandono") || metrica.startsWith("distorcao_"))
    return ["INEP/MEC", "Censo Escolar"];
  if (metrica.startsWith("frota_"))
    return ["SENATRAN", "Sec. Nacional de Transito"];
  if (metrica.startsWith("rebanho_") || metrica.startsWith("producao_") || metrica === "vbp_pecuaria_per_capita")
    return ["IBGE", "Pesquisa Pecuaria Municipal"];
  if (metrica === "vbp_agricola_per_capita")
    return ["IBGE", "Producao Agricola Municipal"];
  if (metrica.startsWith("leitos_") || metrica.startsWith("medicos_"))
    return ["CNES/DATASUS", "Estabelecimentos de Saude"];
  if (metrica === "empresas_por_1k")
    return ["IBGE", "CEMPRE"];
  if (metrica.startsWith("taxa_nupcialidade") || metrica.startsWith("taxa_divorcialidade") || metrica === "taxa_separacao")
    return ["IBGE", "Registro Civil"];
  return ["IBGE", "Censo Demografico 2022"];
}

function filtrosTexto(filtros, cid10Labels) {
  const t = [];
  if (filtros.cod_uf) t.push(`UF: ${UF_NOMES_COMPLETOS[filtros.cod_uf] ?? UF_NOMES[filtros.cod_uf] ?? filtros.cod_uf}`);
  if (filtros.cid10_capitulo) t.push(`CID-10: Cap. ${filtros.cid10_capitulo} - ${cid10Labels?.[filtros.cid10_capitulo] ?? ""}`);
  if (filtros.sexo) t.push(`Sexo: ${SEXO_NOMES[filtros.sexo] ?? filtros.sexo}`);
  if (filtros.cor_raca) t.push(`Cor/raca: ${COR_RACA_NOMES[filtros.cor_raca] ?? filtros.cor_raca}`);
  if (filtros.faixa_etaria_min != null && filtros.faixa_etaria_max != null &&
      (filtros.faixa_etaria_min !== 0 || filtros.faixa_etaria_max !== 17)) {
    t.push(`Faixa etaria: ${FAIXAS_LABELS[filtros.faixa_etaria_min] ?? filtros.faixa_etaria_min} a ${FAIXAS_LABELS[filtros.faixa_etaria_max] ?? filtros.faixa_etaria_max}`);
  }
  return t;
}

function temFiltrosAtivos(filtros) {
  return !!(filtros.cod_uf || filtros.cid10_capitulo || filtros.sexo || filtros.cor_raca ||
    (filtros.faixa_etaria_min != null && filtros.faixa_etaria_min !== 0) ||
    (filtros.faixa_etaria_max != null && filtros.faixa_etaria_max !== 17));
}

function quebrarTexto(ctx, texto, maxW, font) {
  ctx.font = font;
  const palavras = texto.split(" ");
  const linhas = [];
  let atual = "";
  for (const p of palavras) {
    const teste = atual ? atual + " " + p : p;
    if (ctx.measureText(teste).width > maxW && atual) {
      linhas.push(atual);
      atual = p;
    } else {
      atual = teste;
    }
  }
  if (atual) linhas.push(atual);
  return linhas;
}

function obterIndicadorDirecao(metrica, invertida) {
  if (invertida) return "\u2191 melhor";
  if (METRICAS_SAUDE_SET.has(metrica)) return "\u2191 maior risco";
  if (metrica === "densidade_pop") return "\u2191 mais denso";
  return "\u2191 maior valor";
}

// ── Painel de detalhes da feature selecionada (Canvas 2D) ──────────────────

function desenharPainelDetalhes(ctx, x, y, w, feature, metrica, ano, cid10Labels, S, FF, maxBottom) {
  const p = feature?.properties ?? {};
  const isUF = p.sigla != null || p.regiao != null;
  const nome = p.nome_municipio || p.nome || p.sigla || `Setor ${p.cod_setor ?? ""}`;

  const cor = { fundo:"rgba(15,17,23,0.95)", moldura:"#2d3748", tit:"#e2e8f0", sub:"#a0aec0",
                txt:"#a0aec0", sutil:"#718096", accent:"#4299e1", accentBg:"rgba(66,153,225,0.15)" };

  // Fundo + moldura
  const radius = 8 * S;
  // Calculamos primeiro a altura necessaria
  let cy = 0;

  // Header
  const headerH = 24 * S;
  cy += headerH;

  // Indicador principal
  const indicadorH = 40 * S;
  cy += indicadorH + 6 * S;

  // Linhas de dados extras
  const linhas = [];
  const pop = p.populacao_2022 ?? p.populacao_total;
  if (pop != null) linhas.push(["Populacao", Number(pop).toLocaleString("pt-BR", { maximumFractionDigits: 0 })]);
  if (isUF && p.pib_estadual != null) linhas.push(["PIB (UF)", "R$ " + Number(p.pib_estadual).toLocaleString("pt-BR", { maximumFractionDigits: 0 })]);
  if (!isUF && p.transferencias_sus != null) linhas.push(["Transf. SUS", "R$ " + Number(p.transferencias_sus).toLocaleString("pt-BR", { maximumFractionDigits: 0 })]);

  const geocod = p.cod_ibge_7 ? `IBGE: ${p.cod_ibge_7}` : p.sigla ? `UF: ${p.sigla} (${p.cod_uf})` : p.cod_setor ? `Setor: ${p.cod_setor}` : "";
  if (geocod) linhas.push(null); // separador para geocodigo

  cy += linhas.filter(l => l !== null).length * 16 * S;
  if (geocod) cy += 18 * S;
  cy += 12 * S; // padding inferior

  const totalH = cy;

  // Mantém o painel dentro da área do mapa: se a altura real ultrapassaria o
  // limite inferior (ex.: invadiria a legenda no formato retrato), ancora pelo
  // rodapé do mapa em vez de transbordar.
  if (maxBottom != null && y + totalH > maxBottom) {
    y = Math.max(maxBottom - totalH, 0);
  }

  // Desenhar fundo com cantos arredondados
  ctx.fillStyle = cor.fundo;
  ctx.beginPath(); ctx.roundRect(x, y, w, totalH, radius); ctx.fill();
  ctx.strokeStyle = cor.moldura; ctx.lineWidth = 1 * S;
  ctx.beginPath(); ctx.roundRect(x, y, w, totalH, radius); ctx.stroke();

  let dy = y + 10 * S;

  // Nome da feature
  ctx.fillStyle = cor.tit; ctx.font = `bold ${12*S}px ${FF}`;
  ctx.fillText(nome, x + 10*S, dy + 10*S);
  if (isUF && p.regiao) {
    ctx.fillStyle = cor.sutil; ctx.font = `${9*S}px ${FF}`;
    ctx.fillText(p.regiao, x + 10*S, dy + 22*S);
  }
  dy += headerH;

  // Indicador principal (box azul)
  const boxX = x + 8*S, boxW = w - 16*S, boxH = 36*S;
  ctx.fillStyle = cor.accentBg;
  ctx.beginPath(); ctx.roundRect(boxX, dy, boxW, boxH, 6*S); ctx.fill();
  ctx.strokeStyle = "rgba(66,153,225,0.3)"; ctx.lineWidth = 0.8*S;
  ctx.beginPath(); ctx.roundRect(boxX, dy, boxW, boxH, 6*S); ctx.stroke();

  const metricaLabel = METRICA_LABEL_CURTO[metrica] ?? metrica;
  ctx.fillStyle = cor.accent; ctx.font = `${8*S}px ${FF}`;
  ctx.fillText(`${metricaLabel} \u2014 ${ano}`, boxX + 8*S, dy + 12*S);

  const valorFormatado = formatarMetrica(p.valor_metrica, metrica);
  if (valorFormatado) {
    ctx.fillStyle = cor.tit; ctx.font = `bold ${16*S}px ${FF}`;
    ctx.fillText(valorFormatado.texto, boxX + 8*S, dy + 30*S);
    const valW = ctx.measureText(valorFormatado.texto).width;
    ctx.fillStyle = cor.sub; ctx.font = `${10*S}px ${FF}`;
    ctx.fillText(valorFormatado.unidade, boxX + 8*S + valW + 3*S, dy + 30*S);
  } else {
    ctx.fillStyle = cor.sutil; ctx.font = `italic ${11*S}px ${FF}`;
    ctx.fillText("sem dados", boxX + 8*S, dy + 28*S);
  }
  dy += indicadorH + 6*S;

  // Linhas extras
  ctx.font = `${10*S}px ${FF}`;
  for (const l of linhas) {
    if (l === null) continue;
    const [label, val] = l;
    ctx.fillStyle = cor.sub; ctx.fillText(label, x + 10*S, dy + 10*S);
    ctx.fillStyle = cor.tit; ctx.textAlign = "right";
    ctx.fillText(val, x + w - 10*S, dy + 10*S);
    ctx.textAlign = "left";
    dy += 16*S;
  }

  // Geocodigo
  if (geocod) {
    dy += 4*S;
    ctx.fillStyle = "#1a202c";
    ctx.beginPath(); ctx.roundRect(x + 8*S, dy, w - 16*S, 14*S, 4*S); ctx.fill();
    ctx.fillStyle = cor.sutil; ctx.font = `${8*S}px monospace, ${FF}`;
    ctx.fillText(geocod, x + 14*S, dy + 10*S);
  }

  return totalH;
}

// ═════════════════════════════════════════════════════════════════════════════
//  Entry point
// ═════════════════════════════════════════════════════════════════════════════

export function gerarReport(opts) {
  if (!opts.mapCanvas) { alert("Mapa nao disponivel para captura."); return; }
  if (opts.formato === "pdf") return gerarPDF(opts);
  if (opts.formato === "instagram") return gerarInstagram(opts);
  if (opts.formato === "carta") return gerarCarta(opts);
  return gerarPNG(opts);
}

/**
 * Gera um canvas de preview da carta (escala reduzida, sem download).
 * @param {object} opts - mesmas opts de gerarCarta
 * @param {number} [targetWidth=260] - largura alvo em px CSS
 * @returns {HTMLCanvasElement|null}
 */
export function gerarPreviewCarta(opts, targetWidth = 260) {
  if (!opts.mapCanvas) return null;
  const scale = targetWidth / 1080;
  try {
    return gerarCarta({ ...opts, formato: "carta" }, scale, true);
  } catch (_) {
    return null;
  }
}


// ═════════════════════════════════════════════════════════════════════════════
//  PNG — Canvas 2D (raster 2×)
// ═════════════════════════════════════════════════════════════════════════════

function gerarPNG(opts) {
  const { mapCanvas, viewState, bounds, metrica, ano, nivel, nivelMeta,
          invertida, range, filtros, cid10Labels, adaptativo } = opts;

  // Testar se o canvas do mapa pode ser exportado (CORS taint check)
  let mapExportavel = true;
  try { mapCanvas.toDataURL(); } catch (_) { mapExportavel = false; }

  const S = 2, PAD = 36*S;
  const FF = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif';
  const W = 1200 * S;
  const mapAR = mapCanvas.height / mapCanvas.width;
  const mapAreaW = W - 2*PAD;
  const mapH = Math.round(mapAreaW * mapAR);
  const mppScreen = metrosPorPixel(viewState.latitude, viewState.zoom);
  const mppReport = mppScreen * (mapCanvas.width / mapAreaW);
  const temF = temFiltrosAtivos(filtros);
  const direcao = obterIndicadorDirecao(metrica, invertida);
  const geometria = nivelMeta?.geometria ?? nivel;
  const headerH=100*S, legendaH=160*S, filtrosH=temF?30*S:0, metadataH=72*S, footerH=56*S, mg=22*S;
  const H = mg + headerH + 4*S + mapH + 8*S + legendaH + filtrosH + 6*S + metadataH + footerH + mg;
  const canvas = document.createElement("canvas");
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext("2d");
  const cor = { fundo:"#0d0f17", moldura:"#2d3748", tit:"#e2e8f0", sub:"#a0aec0",
                txt:"#a0aec0", sutil:"#718096", mini:"#4a5568", accent:"#4299e1" };

  ctx.fillStyle = cor.fundo; ctx.fillRect(0,0,W,H);
  // Moldura dupla
  ctx.strokeStyle = cor.sub; ctx.lineWidth = 2*S; ctx.strokeRect(mg/2,mg/2,W-mg,H-mg);
  ctx.strokeStyle = cor.moldura; ctx.lineWidth = .75*S; ctx.strokeRect(mg/2+4*S,mg/2+4*S,W-mg-8*S,H-mg-8*S);
  let y = mg;

  // ── Header ──────────────────────────────────────────────────────────────────
  const titulo = METRICA_LABEL_LONGO[metrica] ?? metrica;
  ctx.fillStyle=cor.tit; ctx.font=`bold ${22*S}px ${FF}`; ctx.fillText(titulo,PAD,y+26*S);
  let geo = "Brasil"; if (filtros.cod_uf) geo = UF_NOMES_COMPLETOS[filtros.cod_uf] ?? geo;
  ctx.fillStyle=cor.sub; ctx.font=`${14*S}px ${FF}`; ctx.fillText(`${geo} \u2014 ${nivelMeta?.label??nivel} \u2014 ${ano}`,PAD,y+48*S);
  ctx.fillStyle=cor.sutil; ctx.font=`italic ${11*S}px ${FF}`;
  ctx.fillText(`Carta tematica coropletica \u2014 ${geometria}`,PAD,y+68*S);
  ctx.textAlign="right"; ctx.fillStyle=cor.sutil; ctx.font=`${10*S}px ${FF}`;
  const d=new Date().toLocaleDateString("pt-BR",{day:"2-digit",month:"long",year:"numeric"});
  ctx.fillText(`Elaboracao: ${d}`,W-PAD,y+26*S);
  ctx.fillStyle=cor.sub; ctx.font=`bold ${11*S}px ${FF}`; ctx.fillText("Brasil em Dados",W-PAD,y+44*S);
  ctx.fillStyle=cor.sutil; ctx.font=`${9*S}px ${FF}`; ctx.fillText("Painel Geoespacial Interativo",W-PAD,y+58*S);
  ctx.textAlign="left"; y+=headerH;

  // Sep
  ctx.strokeStyle=cor.moldura; ctx.lineWidth=1; ctx.beginPath(); ctx.moveTo(PAD,y); ctx.lineTo(W-PAD,y); ctx.stroke(); y+=4*S;

  // ── Mapa ────────────────────────────────────────────────────────────────────
  const mapX=PAD, mapW=mapAreaW, mapY=y;
  ctx.strokeStyle=cor.tit; ctx.lineWidth=1.5*S; ctx.strokeRect(mapX-1,mapY-1,mapW+2,mapH+2);
  if (mapExportavel) {
    try { ctx.drawImage(mapCanvas,mapX,mapY,mapW,mapH); } catch(_) { mapExportavel = false; }
  }
  if (!mapExportavel) {
    ctx.fillStyle="#1a1d2e"; ctx.fillRect(mapX,mapY,mapW,mapH);
    ctx.fillStyle=cor.sutil; ctx.font=`${14*S}px ${FF}`; ctx.textAlign="center";
    ctx.fillText("Mapa indisponivel para exportacao (CORS)",mapX+mapW/2,mapY+mapH/2-10*S);
    ctx.font=`${10*S}px ${FF}`;
    ctx.fillText("Desative o satelite e recarregue a pagina para exportar o mapa",mapX+mapW/2,mapY+mapH/2+10*S);
    ctx.textAlign="left";
  }

  // Coordenadas geograficas NW / SE
  if (bounds) {
    ctx.font=`${8*S}px ${FF}`;
    const nw=`${fmtCoord(bounds.north,"lat")}  ${fmtCoord(bounds.west,"lon")}`;
    const nwW=ctx.measureText(nw).width+10*S;
    ctx.fillStyle="rgba(13,15,23,.78)"; ctx.fillRect(mapX+1,mapY+1,nwW,15*S);
    ctx.fillStyle=cor.txt; ctx.fillText(nw,mapX+5*S,mapY+11*S);
    const se=`${fmtCoord(bounds.south,"lat")}  ${fmtCoord(bounds.east,"lon")}`;
    const seW=ctx.measureText(se).width+10*S;
    ctx.fillStyle="rgba(13,15,23,.78)"; ctx.fillRect(mapX+mapW-seW-1,mapY+mapH-16*S,seW,15*S);
    ctx.fillStyle=cor.txt; ctx.textAlign="right"; ctx.fillText(se,mapX+mapW-5*S,mapY+mapH-5*S); ctx.textAlign="left";
  }

  // Seta norte / orientacao
  const ncx=mapX+mapW-32*S, ncy=mapY+32*S, nr=22*S;
  ctx.beginPath(); ctx.arc(ncx,ncy,nr,0,Math.PI*2); ctx.fillStyle="rgba(13,15,23,.8)"; ctx.fill();
  ctx.strokeStyle="rgba(255,255,255,.25)"; ctx.lineWidth=1.5; ctx.stroke();
  const na=nr*.62;
  ctx.beginPath(); ctx.moveTo(ncx,ncy-na); ctx.lineTo(ncx+na*.3,ncy+na*.15); ctx.lineTo(ncx,ncy-na*.05); ctx.closePath();
  ctx.fillStyle=cor.tit; ctx.fill();
  ctx.beginPath(); ctx.moveTo(ncx,ncy-na); ctx.lineTo(ncx-na*.3,ncy+na*.15); ctx.lineTo(ncx,ncy-na*.05); ctx.closePath();
  ctx.fillStyle=cor.moldura; ctx.fill(); ctx.strokeStyle=cor.tit; ctx.lineWidth=1; ctx.stroke();
  ctx.fillStyle=cor.tit; ctx.font=`bold ${10*S}px ${FF}`; ctx.textAlign="center"; ctx.fillText("N",ncx,ncy-nr+8*S); ctx.textAlign="left";

  // Mapa de enquadramento (inset) — quando UF selecionada
  if (filtros.cod_uf) {
    const iW=110*S,iH=100*S,ix=mapX+8*S,iy=mapY+mapH-iH-8*S;
    ctx.fillStyle="#111520"; ctx.fillRect(ix,iy,iW,iH); ctx.strokeStyle=cor.moldura; ctx.lineWidth=1.5; ctx.strokeRect(ix,iy,iW,iH);
    const proj=(lon,lat)=>[ix+6*S+((lon+75)/42)*(iW-12*S), iy+6*S+((6-lat)/40.5)*(iH-12*S)];
    ctx.beginPath(); BRASIL_CONTORNO.forEach(([lo,la],i)=>{const[px,py]=proj(lo,la);i===0?ctx.moveTo(px,py):ctx.lineTo(px,py);}); ctx.closePath();
    ctx.fillStyle="#1a2030"; ctx.fill(); ctx.strokeStyle="#4a5568"; ctx.lineWidth=1; ctx.stroke();
    if (UF_CENTROIDS[filtros.cod_uf]) {
      const[lo,la]=UF_CENTROIDS[filtros.cod_uf],[px,py]=proj(lo,la);
      ctx.beginPath(); ctx.arc(px,py,4*S,0,Math.PI*2); ctx.fillStyle=cor.accent; ctx.fill(); ctx.strokeStyle="#e2e8f0"; ctx.lineWidth=1.5; ctx.stroke();
    }
    ctx.fillStyle=cor.sutil; ctx.font=`${7*S}px ${FF}`; ctx.fillText("LOCALIZACAO",ix+4*S,iy+10*S);
  }

  // Painel de detalhes (sobre o mapa, se feature selecionada)
  if (opts.featureSelecionada) {
    const panelW = 220*S;
    const panelX = mapX + 8*S;
    const panelY = mapY + 8*S;
    desenharPainelDetalhes(ctx, panelX, panelY, panelW, opts.featureSelecionada, metrica, ano, cid10Labels, S, FF, mapY + mapH - 8*S);
  }

  y+=mapH+8*S;

  // ── Legenda ─────────────────────────────────────────────────────────────────
  ctx.fillStyle=cor.tit; ctx.font=`bold ${11*S}px ${FF}`; ctx.fillText("LEGENDA",PAD,y+14*S);

  // Rampa de cor continua
  const rX=PAD,rY=y+22*S,rW=mapAreaW*.55,rH=16*S;
  for(let i=0;i<256;i++){const[r,g,b]=interpolaRGB(i/255,invertida); ctx.fillStyle=`rgb(${r},${g},${b})`; ctx.fillRect(rX+i*rW/256,rY,rW/256+1,rH);}
  ctx.strokeStyle="rgba(255,255,255,.18)"; ctx.lineWidth=1; ctx.strokeRect(rX,rY,rW,rH);

  // Tick marks + rotulos de valor (6 pontos)
  ctx.textAlign="center";
  for(let p=0;p<=5;p++){
    const t=p/5,tx=rX+t*rW;
    ctx.strokeStyle="rgba(255,255,255,.5)"; ctx.beginPath(); ctx.moveTo(tx,rY+rH); ctx.lineTo(tx,rY+rH+5*S); ctx.stroke();
    ctx.fillStyle=cor.txt; ctx.font=`${10*S}px ${FF}`;
    ctx.fillText(formatarParaLegenda(range.min+t*(range.max-range.min),metrica),tx,rY+rH+17*S);
  }

  // Indicador de direcao (sentido da escala)
  ctx.fillStyle=cor.accent; ctx.font=`bold ${10*S}px ${FF}`;
  ctx.fillText(direcao,rX+rW/2,rY+rH+32*S);
  ctx.textAlign="left";

  // Sem dados (convencao cartografica)
  ctx.fillStyle=cor.mini; ctx.fillRect(rX,rY+rH+42*S,14*S,10*S);
  ctx.strokeStyle="rgba(255,255,255,.15)"; ctx.lineWidth=0.5; ctx.strokeRect(rX,rY+rH+42*S,14*S,10*S);
  ctx.fillStyle=cor.sutil; ctx.font=`${9*S}px ${FF}`; ctx.fillText("Sem dados / nao aplicavel",rX+18*S,rY+rH+51*S);

  // Unidades espaciais
  ctx.fillStyle=cor.sutil; ctx.font=`${9*S}px ${FF}`;
  ctx.fillText(`Unidades de analise: ${geometria}`,rX,rY+rH+66*S);

  // ── Coluna direita: metodo de classificacao ─────────────────────────────────
  const mX=rX+rW+28*S;
  ctx.fillStyle=cor.sutil; ctx.font=`bold ${9*S}px ${FF}`; ctx.fillText("METODO DE CLASSIFICACAO",mX,y+14*S);
  ctx.font=`${10*S}px ${FF}`; ctx.fillStyle=cor.txt;
  ctx.fillText("Normalizacao quantilica (percentil)",mX,y+28*S);
  ctx.fillStyle=cor.sutil;
  if (adaptativo) {
    ctx.fillText("Limites adaptativos: P2 / P98 dos dados carregados",mX,y+42*S);
  } else {
    ctx.fillText("Faixa pre-definida por metrica",mX,y+42*S);
  }
  ctx.fillText("Rampa continua 6 paradas:",mX,y+56*S);
  ctx.fillText("Azul > Teal > Verde > Amarelo > Laranja > Violeta",mX,y+70*S);

  // Mini-rampa ilustrativa ao lado da descricao
  const miniRW=80*S, miniRH=6*S, miniRX=mX, miniRY=y+76*S;
  for(let i=0;i<miniRW;i++){const[r,g,b]=interpolaRGB(i/(miniRW-1),false); ctx.fillStyle=`rgb(${r},${g},${b})`; ctx.fillRect(miniRX+i,miniRY,1.5,miniRH);}
  ctx.strokeStyle="rgba(255,255,255,.12)"; ctx.lineWidth=0.5; ctx.strokeRect(miniRX,miniRY,miniRW,miniRH);

  // Range numerico
  ctx.fillStyle=cor.txt; ctx.font=`${9*S}px ${FF}`;
  ctx.fillText(`Faixa: ${formatarParaLegenda(range.min,metrica)} a ${formatarParaLegenda(range.max,metrica)}`,mX,y+98*S);

  y+=legendaH;

  // ── Filtros aplicados ───────────────────────────────────────────────────────
  if (temF) {
    ctx.fillStyle=cor.sutil; ctx.font=`bold ${9*S}px ${FF}`; ctx.fillText("FILTROS APLICADOS",PAD,y+10*S);
    const ft=filtrosTexto(filtros,cid10Labels);
    ctx.font=`${10*S}px ${FF}`; ctx.fillStyle=cor.txt; ctx.fillText(ft.join("  |  "),PAD+120*S,y+10*S);
    y+=filtrosH;
  }

  // Sep
  ctx.strokeStyle=cor.moldura; ctx.lineWidth=.5; ctx.beginPath(); ctx.moveTo(PAD,y); ctx.lineTo(W-PAD,y); ctx.stroke(); y+=6*S;

  // ── Escala grafica (barra alternada) ────────────────────────────────────────
  const esc=calcularEscala(mppReport,200*S); const bW=esc.px,bH=7*S;
  for(let i=0;i<4;i++){ctx.fillStyle=i%2===0?"#e2e8f0":cor.moldura; ctx.fillRect(PAD+i*bW/4,y+6*S,bW/4,bH);}
  ctx.strokeStyle=cor.tit; ctx.lineWidth=1; ctx.strokeRect(PAD,y+6*S,bW,bH);
  ctx.fillStyle=cor.tit; ctx.font=`bold ${10*S}px ${FF}`; ctx.fillText("0",PAD,y+6*S+bH+14*S);
  ctx.textAlign="right"; ctx.fillText(esc.label,PAD+bW,y+6*S+bH+14*S); ctx.textAlign="left";

  // ── Referencia geodesica ────────────────────────────────────────────────────
  const gX=PAD+280*S;
  ctx.fillStyle=cor.sutil; ctx.font=`bold ${9*S}px ${FF}`; ctx.fillText("REFERENCIA GEODESICA",gX,y+10*S);
  ctx.font=`${10*S}px ${FF}`; ctx.fillStyle=cor.txt;
  ctx.fillText("Datum: SIRGAS 2000 (EPSG:4674)",gX,y+24*S);
  ctx.fillText("Projecao: Web Mercator (EPSG:3857)",gX,y+38*S);
  ctx.fillStyle=cor.sutil; ctx.font=`${9*S}px ${FF}`;
  ctx.fillText("Armazenamento: EPSG:4674 | Visualizacao: EPSG:3857",gX,y+52*S);

  // ── Fonte dos dados ─────────────────────────────────────────────────────────
  const fX=PAD+600*S; const[sig,desc]=obterFonte(metrica);
  ctx.fillStyle=cor.sutil; ctx.font=`bold ${9*S}px ${FF}`; ctx.fillText("FONTE DOS DADOS",fX,y+10*S);
  ctx.fillStyle=cor.txt; ctx.font=`${10*S}px ${FF}`; ctx.fillText(sig,fX,y+24*S);
  ctx.fillStyle=cor.sutil; ctx.font=`${9*S}px ${FF}`; ctx.fillText(desc,fX,y+38*S);
  ctx.fillText("Base cartografica: IBGE - Malha Municipal 2022",fX,y+52*S);
  y+=metadataH;

  // ── Rodape ──────────────────────────────────────────────────────────────────
  const fY=H-footerH-mg/2;
  ctx.fillStyle="#0a0c12"; ctx.fillRect(mg/2+4*S,fY,W-mg-8*S,footerH-4*S);
  ctx.fillStyle=cor.sub; ctx.font=`bold ${10*S}px ${FF}`; ctx.fillText("Brasil em Dados \u2014 Painel Geoespacial Interativo do Brasil",PAD,fY+16*S);
  ctx.fillStyle=cor.sutil; ctx.font=`${8*S}px ${FF}`;
  ctx.fillText("ABNT NBR 15777:2009 | Datum SIRGAS 2000 - Res. IBGE R.PR-01/2015 | brasilemdados.ia.br",PAD,fY+34*S);
  ctx.textAlign="right"; ctx.fillText(`Zoom: ${viewState.zoom.toFixed(1)} | Nivel: ${nivelMeta?.label??nivel}`,W-PAD,fY+34*S); ctx.textAlign="left";

  // ── Download ────────────────────────────────────────────────────────────────
  try {
    const link = document.createElement("a");
    link.download = `carta-tematica_${metrica}_${ano}_${nivel}.png`;
    link.href = canvas.toDataURL("image/png");
    link.click();
  } catch (e) {
    alert("Erro ao exportar PNG: o canvas foi contaminado por tiles de origem cruzada (CORS).\n\nDesative a camada de satelite e tente novamente.");
  }
}


// ═════════════════════════════════════════════════════════════════════════════
//  Instagram — 1080px largura, altura dinamica (feed aceita 1:1 a 4:5)
//  Raster 2× — mapa protagonista, sem espaco morto
// ═════════════════════════════════════════════════════════════════════════════

function gerarInstagram(opts) {
  const { mapCanvas, viewState, bounds, metrica, ano, nivel, nivelMeta,
          invertida, range, filtros, cid10Labels, adaptativo } = opts;

  let mapExportavel = true;
  try { mapCanvas.toDataURL(); } catch (_) { mapExportavel = false; }

  const S = 2;
  const W = 1080 * S;
  const PAD = 32 * S;
  const FF = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif';
  const cor = { fundo:"#0d0f17", moldura:"#2d3748", tit:"#e2e8f0", sub:"#a0aec0",
                txt:"#a0aec0", sutil:"#718096", mini:"#4a5568", accent:"#4299e1" };
  const direcao = obterIndicadorDirecao(metrica, invertida);
  const geometria = nivelMeta?.geometria ?? nivel;
  const titulo = METRICA_LABEL_LONGO[metrica] ?? metrica;
  let geo = "Brasil";
  if (filtros.cod_uf) geo = UF_NOMES_COMPLETOS[filtros.cod_uf] ?? geo;
  const temF = temFiltrosAtivos(filtros);
  const [fonteSigla, fonteDesc] = obterFonte(metrica);

  // ── Pre-calcular altura do mapa e do canvas ──
  const mapAreaW = W - 2 * PAD;
  const mapAR = mapCanvas.height / mapCanvas.width;
  // Mapa com crop central: se muito landscape, corta as laterais para ficar mais quadrado
  // Aspect ratio minimo do mapa no card: 0.55 (quase quadrado)
  const effectiveAR = Math.max(mapAR, 0.55);
  const mapH = Math.round(mapAreaW * effectiveAR);

  // Calcular altura total baseado no conteudo real
  const headerH = 90 * S;
  const legendaH = 80 * S;
  const filtrosH = temF ? 22 * S : 0;
  const metaH = 50 * S;
  const footerH = 36 * S;
  const gaps = 30 * S; // espacamento total entre secoes
  const H = PAD + headerH + mapH + legendaH + filtrosH + metaH + footerH + gaps + PAD;

  const canvas = document.createElement("canvas");
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext("2d");

  // ── Fundo ──
  ctx.fillStyle = cor.fundo; ctx.fillRect(0, 0, W, H);

  // Moldura
  ctx.strokeStyle = "rgba(160,174,192,.25)"; ctx.lineWidth = 1.5 * S;
  ctx.strokeRect(PAD * 0.4, PAD * 0.4, W - PAD * 0.8, H - PAD * 0.8);

  let y = PAD;

  // ── Header ──────────────────────────────────────────────────────────────────
  // Marca
  ctx.fillStyle = cor.accent; ctx.font = `bold ${12*S}px ${FF}`;
  ctx.fillText("BRASIL EM DADOS", PAD, y + 16*S);

  // Ano (badge direita)
  ctx.textAlign = "right";
  ctx.fillStyle = cor.accent; ctx.font = `bold ${14*S}px ${FF}`;
  ctx.fillText(String(ano), W - PAD, y + 18*S);
  ctx.textAlign = "left";

  // Titulo — fonte grande, quebra automatica
  ctx.fillStyle = cor.tit; ctx.font = `bold ${24*S}px ${FF}`;
  const maxTitleW = W - 2 * PAD;
  if (ctx.measureText(titulo).width > maxTitleW) {
    const words = titulo.split(" ");
    let line1 = "", line2 = "";
    for (const w of words) {
      const test = line1 ? line1 + " " + w : w;
      if (ctx.measureText(test).width <= maxTitleW) line1 = test;
      else line2 += (line2 ? " " : "") + w;
    }
    ctx.fillText(line1, PAD, y + 48*S);
    if (line2) { ctx.font = `bold ${22*S}px ${FF}`; ctx.fillText(line2, PAD, y + 72*S); }
  } else {
    ctx.fillText(titulo, PAD, y + 50*S);
  }

  // Subtitulo
  ctx.fillStyle = cor.sub; ctx.font = `${14*S}px ${FF}`;
  ctx.fillText(`${geo} \u2014 ${geometria}`, PAD, y + headerH - 6*S);

  y += headerH;

  // Sep
  ctx.strokeStyle = cor.moldura; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(PAD, y); ctx.lineTo(W - PAD, y); ctx.stroke();
  y += 4*S;

  // ── Mapa ────────────────────────────────────────────────────────────────────
  const mapX = PAD, mapY = y;

  // Moldura do mapa
  ctx.strokeStyle = "rgba(255,255,255,.12)"; ctx.lineWidth = 1*S;
  ctx.strokeRect(mapX - 1, mapY - 1, mapAreaW + 2, mapH + 2);

  if (mapExportavel) {
    try {
      if (mapAR >= 0.55) {
        // Mapa cabe sem crop
        ctx.drawImage(mapCanvas, mapX, mapY, mapAreaW, mapH);
      } else {
        // Mapa muito landscape: crop central vertical
        const srcH = mapCanvas.width * effectiveAR;
        const srcY = (mapCanvas.height - srcH) / 2;
        ctx.drawImage(mapCanvas, 0, Math.max(0, srcY), mapCanvas.width, srcH, mapX, mapY, mapAreaW, mapH);
      }
    } catch (_) { mapExportavel = false; }
  }
  if (!mapExportavel) {
    ctx.fillStyle = "#1a1d2e"; ctx.fillRect(mapX, mapY, mapAreaW, mapH);
    ctx.fillStyle = cor.sutil; ctx.font = `${14*S}px ${FF}`; ctx.textAlign = "center";
    ctx.fillText("Mapa indisponivel (CORS)", mapX + mapAreaW / 2, mapY + mapH / 2);
    ctx.textAlign = "left";
  }

  // Coordenadas sobre o mapa
  if (bounds) {
    ctx.font = `${8*S}px ${FF}`;
    const nw = `${fmtCoord(bounds.north, "lat")}  ${fmtCoord(bounds.west, "lon")}`;
    const nwW = ctx.measureText(nw).width + 10*S;
    ctx.fillStyle = "rgba(13,15,23,.82)"; ctx.fillRect(mapX + 2, mapY + 2, nwW, 14*S);
    ctx.fillStyle = cor.txt; ctx.fillText(nw, mapX + 5*S, mapY + 12*S);

    const se = `${fmtCoord(bounds.south, "lat")}  ${fmtCoord(bounds.east, "lon")}`;
    const seW = ctx.measureText(se).width + 10*S;
    ctx.fillStyle = "rgba(13,15,23,.82)"; ctx.fillRect(mapX + mapAreaW - seW - 2, mapY + mapH - 16*S, seW, 14*S);
    ctx.fillStyle = cor.txt; ctx.textAlign = "right";
    ctx.fillText(se, mapX + mapAreaW - 5*S, mapY + mapH - 5*S);
    ctx.textAlign = "left";
  }

  // Seta norte
  const ncx = mapX + mapAreaW - 28*S, ncy = mapY + 28*S, nr = 20*S;
  ctx.beginPath(); ctx.arc(ncx, ncy, nr, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(13,15,23,.85)"; ctx.fill();
  ctx.strokeStyle = "rgba(255,255,255,.2)"; ctx.lineWidth = 1.5; ctx.stroke();
  const nna = nr * 0.6;
  ctx.beginPath(); ctx.moveTo(ncx, ncy - nna); ctx.lineTo(ncx + nna * 0.3, ncy + nna * 0.12); ctx.lineTo(ncx, ncy - nna * 0.05); ctx.closePath();
  ctx.fillStyle = cor.tit; ctx.fill();
  ctx.beginPath(); ctx.moveTo(ncx, ncy - nna); ctx.lineTo(ncx - nna * 0.3, ncy + nna * 0.12); ctx.lineTo(ncx, ncy - nna * 0.05); ctx.closePath();
  ctx.fillStyle = cor.moldura; ctx.fill(); ctx.strokeStyle = cor.tit; ctx.lineWidth = 1; ctx.stroke();
  ctx.fillStyle = cor.tit; ctx.font = `bold ${9*S}px ${FF}`; ctx.textAlign = "center";
  ctx.fillText("N", ncx, ncy - nr + 8*S); ctx.textAlign = "left";

  // Inset
  if (filtros.cod_uf) {
    const iW = 80*S, iH = 72*S, ix = mapX + 8*S, iy = mapY + mapH - iH - 8*S;
    ctx.fillStyle = "rgba(17,21,32,.92)"; ctx.fillRect(ix, iy, iW, iH);
    ctx.strokeStyle = cor.moldura; ctx.lineWidth = 1; ctx.strokeRect(ix, iy, iW, iH);
    const proj = (lon, lat) => [ix + 5*S + ((lon + 75) / 42) * (iW - 10*S), iy + 5*S + ((6 - lat) / 40.5) * (iH - 10*S)];
    ctx.beginPath();
    BRASIL_CONTORNO.forEach(([lo, la], i) => { const [px, py] = proj(lo, la); i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py); });
    ctx.closePath(); ctx.fillStyle = "#1a2030"; ctx.fill(); ctx.strokeStyle = "#4a5568"; ctx.lineWidth = 1; ctx.stroke();
    if (UF_CENTROIDS[filtros.cod_uf]) {
      const [lo, la] = UF_CENTROIDS[filtros.cod_uf], [px, py] = proj(lo, la);
      ctx.beginPath(); ctx.arc(px, py, 4*S, 0, Math.PI * 2);
      ctx.fillStyle = cor.accent; ctx.fill(); ctx.strokeStyle = "#e2e8f0"; ctx.lineWidth = 1.5; ctx.stroke();
    }
  }

  // Escala grafica sobre o mapa (canto inferior direito, acima das coords)
  const mppScreen = metrosPorPixel(viewState.latitude, viewState.zoom);
  const mppReport = mppScreen * (mapCanvas.width / mapAreaW);
  const esc = calcularEscala(mppReport, 160*S);
  const bW = esc.px, bH = 5*S;
  const bX = mapX + mapAreaW - bW - 12*S, bY = mapY + mapH - 36*S;
  ctx.fillStyle = "rgba(13,15,23,.82)"; ctx.fillRect(bX - 6*S, bY - 4*S, bW + 12*S, bH + 22*S);
  for (let i = 0; i < 4; i++) {
    ctx.fillStyle = i % 2 === 0 ? "#e2e8f0" : cor.moldura;
    ctx.fillRect(bX + i * bW / 4, bY, bW / 4, bH);
  }
  ctx.strokeStyle = cor.tit; ctx.lineWidth = 0.8; ctx.strokeRect(bX, bY, bW, bH);
  ctx.fillStyle = cor.tit; ctx.font = `bold ${8*S}px ${FF}`;
  ctx.fillText("0", bX, bY + bH + 12*S);
  ctx.textAlign = "right"; ctx.fillText(esc.label, bX + bW, bY + bH + 12*S); ctx.textAlign = "left";

  // Painel de detalhes (sobre o mapa, se feature selecionada)
  if (opts.featureSelecionada) {
    const panelW = 190*S;
    const panelX = mapX + 8*S;
    // Se tem inset, coloca o painel acima dele
    const panelY = filtros.cod_uf ? mapY + 8*S : mapY + mapH - 120*S;
    desenharPainelDetalhes(ctx, panelX, panelY, panelW, opts.featureSelecionada, metrica, ano, cid10Labels, S, FF, mapY + mapH - 8*S);
  }

  y += mapH + 8*S;

  // ── Legenda ─────────────────────────────────────────────────────────────────
  // Rampa de cor — grossa e visivel
  const rX = PAD, rW = mapAreaW, rH = 18*S;
  for (let i = 0; i < 256; i++) {
    const [r, g, b] = interpolaRGB(i / 255, invertida);
    ctx.fillStyle = `rgb(${r},${g},${b})`;
    ctx.fillRect(rX + i * rW / 256, y, rW / 256 + 1, rH);
  }
  ctx.strokeStyle = "rgba(255,255,255,.15)"; ctx.lineWidth = 0.8; ctx.strokeRect(rX, y, rW, rH);

  // Tick marks + valores — 5 pontos, primeiro left-aligned, ultimo right-aligned
  y += rH;
  ctx.font = `bold ${10*S}px ${FF}`; ctx.fillStyle = cor.txt;
  for (let p = 0; p <= 4; p++) {
    const t = p / 4, tx = rX + t * rW;
    ctx.strokeStyle = "rgba(255,255,255,.5)"; ctx.beginPath();
    ctx.moveTo(tx, y); ctx.lineTo(tx, y + 5*S); ctx.stroke();
    const lbl = formatarParaLegenda(range.min + t * (range.max - range.min), metrica);
    if (p === 0) { ctx.textAlign = "left"; }
    else if (p === 4) { ctx.textAlign = "right"; }
    else { ctx.textAlign = "center"; }
    ctx.fillText(lbl, tx, y + 17*S);
  }
  ctx.textAlign = "left";

  // Direcao
  ctx.fillStyle = cor.accent; ctx.font = `bold ${11*S}px ${FF}`; ctx.textAlign = "center";
  ctx.fillText(direcao, rX + rW / 2, y + 32*S);
  ctx.textAlign = "left";

  // Linha: sem dados + geometria + metodo
  ctx.fillStyle = cor.mini; ctx.fillRect(rX, y + 40*S, 12*S, 10*S);
  ctx.strokeStyle = "rgba(255,255,255,.12)"; ctx.lineWidth = 0.5; ctx.strokeRect(rX, y + 40*S, 12*S, 10*S);
  ctx.fillStyle = cor.sutil; ctx.font = `${9*S}px ${FF}`;
  ctx.fillText("Sem dados", rX + 16*S, y + 49*S);

  const metodoTxt = adaptativo ? "P2/P98 adaptativo" : "Faixa fixa";
  ctx.textAlign = "right"; ctx.fillStyle = cor.sutil;
  ctx.fillText(`${geometria}  \u2022  ${metodoTxt}  \u2022  SIRGAS 2000`, W - PAD, y + 49*S);
  ctx.textAlign = "left";

  y += legendaH;

  // ── Filtros ─────────────────────────────────────────────────────────────────
  if (temF) {
    const ft = filtrosTexto(filtros, cid10Labels);
    ctx.fillStyle = cor.accent; ctx.font = `bold ${9*S}px ${FF}`;
    ctx.fillText("FILTROS", PAD, y + 8*S);
    ctx.fillStyle = cor.txt; ctx.font = `${10*S}px ${FF}`;
    ctx.fillText(ft.join("  \u2022  "), PAD + 60*S, y + 8*S);
    y += filtrosH;
  }

  // ── Rodape ──────────────────────────────────────────────────────────────────
  ctx.strokeStyle = cor.moldura; ctx.lineWidth = 0.5;
  ctx.beginPath(); ctx.moveTo(PAD, y); ctx.lineTo(W - PAD, y); ctx.stroke();
  y += 8*S;

  ctx.fillStyle = cor.sutil; ctx.font = `${9*S}px ${FF}`;
  ctx.fillText(`Fonte: ${fonteSigla} \u2014 ${fonteDesc}  |  Base: IBGE 2022`, PAD, y + 8*S);

  ctx.textAlign = "right";
  ctx.fillStyle = cor.accent; ctx.font = `bold ${11*S}px ${FF}`;
  ctx.fillText("brasilemdados.ia.br", W - PAD, y + 8*S);
  const d = new Date().toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
  ctx.fillStyle = cor.mini; ctx.font = `${8*S}px ${FF}`;
  ctx.fillText(d, W - PAD, y + 22*S);
  ctx.textAlign = "left";

  // ── Download ────────────────────────────────────────────────────────────────
  try {
    const link = document.createElement("a");
    link.download = `brasil-em-dados_${metrica}_${ano}_instagram.png`;
    link.href = canvas.toDataURL("image/png");
    link.click();
  } catch (e) {
    alert("Erro ao exportar: canvas contaminado por CORS.\nDesative o satelite e tente novamente.");
  }
}


// ═════════════════════════════════════════════════════════════════════════════
//  CARTA — Formato editorial claro, inspirado em cartografia profissional
//  Tema claro, tipografia grande, legenda discreta, export JPEG
// ═════════════════════════════════════════════════════════════════════════════

/**
 * Gera a carta tematica completa.
 * @param {object} opts
 * @param {number} [scaleOverride] - fator de escala (default 2 para export, ~0.25 para preview)
 * @param {boolean} [returnCanvas] - se true, retorna o canvas ao inves de baixar
 */
function gerarCarta(opts, scaleOverride, returnCanvas) {
  const { mapCanvas, viewState, bounds, metrica, ano, nivel, nivelMeta,
          invertida, range, filtros, cid10Labels, adaptativo } = opts;
  const tema = opts.tema ?? "claro";
  const proporcao = opts.proporcao ?? "auto";
  const mostrarDestaque = opts.mostrarDestaque !== false;
  const mostrarLocalizador = opts.mostrarLocalizador !== false;
  const mostrarLegenda = opts.mostrarLegenda !== false;
  const mostrarNorte = opts.mostrarNorte !== false;
  const mostrarCoordenadas = opts.mostrarCoordenadas !== false;
  const mostrarDescricao = opts.mostrarDescricao !== false;
  const tituloCustom = opts.tituloCustom;
  const textoExplicativo = opts.textoExplicativo;

  let mapExportavel = true;
  try { mapCanvas.toDataURL(); } catch (_) { mapExportavel = false; }

  const S = scaleOverride ?? 2;
  const W = 1080 * S;
  const PAD = 48 * S;
  const FF = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';
  const contentW = W - 2 * PAD;

  // ── Paletas ──
  const PALETAS = {
    claro: {
      fundo:     "#f2f1ec",
      titulo:    "#1a1a1a",
      subtitulo: "#3a3a3a",
      texto:     "#555555",
      sutil:     "#888888",
      marca:     "#b0b0a8",
      barra:     "#444444",
      semDados:  "#c8c8c0",
      fonte:     "#333333",
      separador: "#d0cfc8",
      moldura:   "rgba(255,255,255,0.85)",
      insetFundo: "rgba(242,241,236,0.94)",
      insetTerra: "#d5d4cc",
      insetBorda: "rgba(0,0,0,0.12)",
      calloutFundo: "rgba(242,241,236,0.95)",
      calloutBorda: "rgba(0,0,0,0.08)",
      mapFallback: "#e0dfd8",
      sombraBase: 0.03,
    },
    escuro: {
      fundo:     "#0d0f17",
      titulo:    "#e2e8f0",
      subtitulo: "#a0aec0",
      texto:     "#a0aec0",
      sutil:     "#718096",
      marca:     "#4a5568",
      barra:     "#4299e1",
      semDados:  "#2d3748",
      fonte:     "#a0aec0",
      separador: "#2d3748",
      moldura:   "rgba(45,55,72,0.8)",
      insetFundo: "rgba(13,15,23,0.94)",
      insetTerra: "#1a2030",
      insetBorda: "rgba(255,255,255,0.1)",
      calloutFundo: "rgba(13,15,23,0.95)",
      calloutBorda: "rgba(255,255,255,0.08)",
      mapFallback: "#1a1d2e",
      sombraBase: 0.08,
    },
  };
  const cor = PALETAS[tema] ?? PALETAS.claro;

  const titulo = tituloCustom || (METRICA_LABEL_LONGO[metrica] ?? metrica);
  let geo = "Brasil";
  if (filtros.cod_uf) geo = UF_NOMES_COMPLETOS[filtros.cod_uf] ?? geo;
  const [fonteSigla, fonteDesc] = obterFonte(metrica);
  const geometria = nivelMeta?.geometria ?? nivel;
  const temF = temFiltrosAtivos(filtros);
  const filtrosLines = temF ? filtrosTexto(filtros, cid10Labels) : [];

  // ── Pre-medir textos ──
  const tmpC = document.createElement("canvas"); tmpC.width = W; tmpC.height = 10;
  const tmpCtx = tmpC.getContext("2d");

  // Titulo: fonte display, ate 3 linhas (52pt — referencia @espacialidade)
  const tituloFont = `800 ${52*S}px ${FF}`;
  const tituloLinhas = quebrarTexto(tmpCtx, titulo, contentW, tituloFont);
  const tituloLineH = 62 * S;
  const tituloH = tituloLinhas.length * tituloLineH;

  // Descricao para overlay no mapa
  const descricaoAuto =
    `Distribuicao espacial de ${(METRICA_LABEL_LONGO[metrica] ?? metrica).charAt(0).toLowerCase() + (METRICA_LABEL_LONGO[metrica] ?? metrica).slice(1)} ` +
    `por ${geometria}. Dados processados a partir de ` +
    `${fonteDesc}. Base cartografica: IBGE, Malha Municipal 2022.`;
  const descricao = textoExplicativo || descricaoAuto;

  // ── Dimensoes do mapa (proporcao customizavel) ──
  const mapAR = mapCanvas.height / mapCanvas.width;
  const PROP_MAP = { "4:3": 3/4, "1:1": 1, "3:4": 4/3, "16:9": 9/16 };
  const targetAR = PROP_MAP[proporcao] ?? null;
  // Auto: minimo 0.85 evita cartas achatadas em monitores widescreen
  const effectiveAR = targetAR ?? Math.max(mapAR, 0.85);
  const mapH = Math.round(contentW * effectiveAR);

  // ── Layout vertical (mapa dominante, tipografia generosa) ──
  const brandH = 28*S, barH = 5*S, gapBrand = 14*S;
  const gapTitSub = 10*S, subH = 44*S, gapSubMap = 18*S;
  const gapMapLeg = 20*S;
  const legSwatchH = 45*S, legLabelH = 51*S, legUnitH = 42*S;
  const legH = mostrarLegenda ? legLabelH + legSwatchH + legUnitH + 10*S : 0;
  const sepH = 1;
  const filtrosH = filtrosLines.length > 0 ? 36*S : 0;
  // Descricao abaixo da legenda — só quando overlay está desligado mas há texto explicativo
  const descFont = `${27*S}px ${FF}`;
  const descMaxW = contentW * 0.88;
  const descAbaixo = !mostrarDescricao && textoExplicativo;
  const descLinhas = descAbaixo ? quebrarTexto(tmpCtx, descricao, descMaxW, descFont) : [];
  const descLineH = 36 * S;
  const descH = descLinhas.length > 0 ? descLinhas.length * descLineH + 10 * S : 0;
  const footerH = 120*S;
  const gapFoot = 14*S;

  const temBlocoExtra = descH > 0 || filtrosLines.length > 0;
  const blocoExtraH = temBlocoExtra ? 14*S + sepH + 14*S + descH + filtrosH : 0;
  const H = PAD + brandH + barH + gapBrand + tituloH + gapTitSub + subH + gapSubMap
          + mapH + gapMapLeg + legH + blocoExtraH
          + gapFoot + footerH + PAD;

  // ── Canvas ──
  const canvas = document.createElement("canvas");
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext("2d");

  ctx.fillStyle = cor.fundo; ctx.fillRect(0, 0, W, H);

  let y = PAD;

  // ═══ MARCA ═════════════════════════════════════════════════════════════════
  ctx.fillStyle = cor.marca; ctx.font = `italic ${14*S}px ${FF}`;
  ctx.fillText("@brasilemdadoslab", PAD, y + 16*S);
  y += brandH;

  // Barra de acento (mais larga, como referencia)
  ctx.fillStyle = cor.barra; ctx.fillRect(PAD, y, 64*S, barH);
  y += barH + gapBrand;

  // ═══ TITULO ════════════════════════════════════════════════════════════════
  ctx.fillStyle = cor.titulo; ctx.font = tituloFont;
  for (const linha of tituloLinhas) {
    ctx.fillText(linha, PAD, y + 48*S);
    y += tituloLineH;
  }
  y += gapTitSub;

  // ═══ SUBTITULO (geo | ano) ═════════════════════════════════════════════════
  ctx.fillStyle = cor.subtitulo; ctx.font = `300 ${36*S}px ${FF}`;
  ctx.fillText(`${geo}  \u2502  ${ano}`, PAD, y + 36*S);
  y += subH + gapSubMap;

  // ═══ MAPA (sem moldura — direto, limpo, como a referencia) ═════════════════
  const mapX = PAD, mapY = y;

  // Mapa (recorte central para proporcao desejada)
  if (mapExportavel) {
    try {
      const srcW = mapCanvas.width;
      const srcH_full = mapCanvas.height;
      const desiredSrcH = srcW * effectiveAR;
      let srcX = 0, srcY = 0, srcCropW = srcW, srcCropH = srcH_full;
      if (desiredSrcH <= srcH_full) {
        srcCropH = desiredSrcH;
        srcY = (srcH_full - desiredSrcH) / 2;
      } else {
        srcCropW = srcH_full / effectiveAR;
        srcX = (srcW - srcCropW) / 2;
      }
      ctx.drawImage(mapCanvas,
        Math.max(0, srcX), Math.max(0, srcY), srcCropW, srcCropH,
        mapX, mapY, contentW, mapH);
    } catch (_) { mapExportavel = false; }
  }
  if (!mapExportavel) {
    ctx.fillStyle = cor.mapFallback; ctx.fillRect(mapX, mapY, contentW, mapH);
    ctx.fillStyle = cor.sutil; ctx.font = `${14*S}px ${FF}`; ctx.textAlign = "center";
    ctx.fillText("Mapa indisponivel (CORS) \u2014 desative o satelite",
                 mapX + contentW / 2, mapY + mapH / 2);
    ctx.textAlign = "left";
  }

  // ── Overlay: bloco de texto indicador (bottom-left do mapa) ──
  if (mostrarDescricao) {
    // Overlay limita-se a no maximo 35% da largura do conteudo
    const overlayW = Math.min(300*S, contentW * 0.35);
    const oPad = 16*S;
    const oTitFont = Math.round(27*S);
    const oDescFont = Math.round(21*S);
    const oTitLineH = Math.round(34*S);
    const oDescLineH = Math.round(28*S);
    const indicadorLabel = METRICA_LABEL_CURTO[metrica] ?? metrica;
    const overlayDescLinhas = quebrarTexto(ctx, descricao, overlayW - 2*oPad, `${oDescFont}px ${FF}`);
    const overlayDescH = overlayDescLinhas.length * oDescLineH;
    const overlayTituloLinhas = quebrarTexto(ctx, indicadorLabel, overlayW - 2*oPad, `bold ${oTitFont}px ${FF}`);
    const overlayTituloH = overlayTituloLinhas.length * oTitLineH;
    const overlayH = 12*S + 18*S + overlayTituloH + 8*S + overlayDescH + 16*S;
    const ox = mapX + 14*S, oy = mapY + mapH - overlayH - 14*S;

    ctx.fillStyle = cor.calloutFundo;
    ctx.beginPath(); ctx.roundRect(ox, oy, overlayW, overlayH, 8*S); ctx.fill();
    ctx.strokeStyle = cor.calloutBorda; ctx.lineWidth = 1*S;
    ctx.beginPath(); ctx.roundRect(ox, oy, overlayW, overlayH, 8*S); ctx.stroke();

    // Barra de acento
    ctx.fillStyle = cor.barra;
    ctx.fillRect(ox + oPad, oy + 14*S, 40*S, 5*S);

    // Titulo do indicador
    ctx.fillStyle = cor.titulo; ctx.font = `bold ${oTitFont}px ${FF}`;
    let oTY = oy + 12*S + 18*S;
    for (const tl of overlayTituloLinhas) {
      ctx.fillText(tl, ox + oPad, oTY + oTitFont);
      oTY += oTitLineH;
    }
    oTY += 8*S;

    // Descricao dentro do overlay
    ctx.fillStyle = cor.sutil; ctx.font = `${oDescFont}px ${FF}`;
    for (const dl of overlayDescLinhas) {
      ctx.fillText(dl, ox + oPad, oTY + oDescFont);
      oTY += oDescLineH;
    }
  }

  // ── Overlay: inset de localizacao (sobre o overlay de texto ou acima dele) ──
  if (filtros.cod_uf && mostrarLocalizador) {
    const iW = 86*S, iH = 76*S;
    const ix = mapX + 14*S, iy = mapY + 14*S;
    ctx.fillStyle = cor.insetFundo;
    ctx.beginPath(); ctx.roundRect(ix, iy, iW, iH, 4*S); ctx.fill();
    ctx.strokeStyle = cor.insetBorda; ctx.lineWidth = 1*S;
    ctx.beginPath(); ctx.roundRect(ix, iy, iW, iH, 4*S); ctx.stroke();

    const proj = (lon, lat) => [ix + 8*S + ((lon + 75) / 42) * (iW - 16*S),
                                iy + 8*S + ((6 - lat) / 40.5) * (iH - 16*S)];
    ctx.beginPath();
    BRASIL_CONTORNO.forEach(([lo, la], i) => {
      const [px, py] = proj(lo, la);
      i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
    });
    ctx.closePath();
    ctx.fillStyle = cor.insetTerra; ctx.fill();
    ctx.strokeStyle = cor.sutil; ctx.lineWidth = 0.8; ctx.stroke();
    if (UF_CENTROIDS[filtros.cod_uf]) {
      const [lo, la] = UF_CENTROIDS[filtros.cod_uf], [px, py] = proj(lo, la);
      ctx.beginPath(); ctx.arc(px, py, 4*S, 0, Math.PI * 2);
      ctx.fillStyle = "#c62828"; ctx.fill();
      ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.5*S; ctx.stroke();
    }
  }

  // ── Overlay: callout de destaque (bottom-right do mapa) ──
  if (opts.featureSelecionada && mostrarDestaque) {
    const p = opts.featureSelecionada.properties ?? {};
    const nome = p.nome_municipio || p.nome || p.sigla || "";
    const valorF = formatarMetrica(p.valor_metrica, metrica);
    if (valorF && nome) {
      const cardW = Math.min(230*S, contentW * 0.28);
      const cardH = Math.round(cardW * 0.43);
      const cPad = Math.round(16*S);
      const cx = mapX + contentW - cardW - 14*S;
      const cy = mapY + mapH - cardH - 14*S;
      ctx.fillStyle = cor.calloutFundo;
      ctx.beginPath(); ctx.roundRect(cx, cy, cardW, cardH, 6*S); ctx.fill();
      ctx.strokeStyle = cor.calloutBorda; ctx.lineWidth = 1*S;
      ctx.beginPath(); ctx.roundRect(cx, cy, cardW, cardH, 6*S); ctx.stroke();

      // Valor grande
      ctx.fillStyle = cor.titulo; ctx.font = `bold ${34*S}px ${FF}`;
      ctx.textAlign = "right";
      ctx.fillText(`${valorF.texto}${valorF.unidade}`, cx + cardW - cPad, cy + cardH * 0.38);

      // Nome do municipio/UF
      ctx.font = `bold ${14*S}px ${FF}`;
      ctx.fillStyle = cor.subtitulo;
      const ufSigla = p.uf || p.sigla_uf || "";
      const nomeCompleto = ufSigla ? `${nome} - ${ufSigla}` : nome;
      ctx.fillText(nomeCompleto, cx + cardW - cPad, cy + cardH * 0.62);

      // Label contextual
      ctx.font = `italic ${10*S}px ${FF}`;
      ctx.fillStyle = cor.sutil;
      const metricaLbl = METRICA_LABEL_CURTO[metrica] ?? metrica;
      ctx.fillText(metricaLbl, cx + cardW - cPad, cy + cardH * 0.82);
      ctx.textAlign = "left";
    }
  }

  y += mapH + gapMapLeg;

  // ═══ LEGENDA (horizontal, labels acima dos swatches) ═══════════════════════
  if (mostrarLegenda) {
    const N_CLASSES = 5;
    const span = range.max - range.min;
    const breaks = [];
    for (let i = 0; i <= N_CLASSES; i++) breaks.push(range.min + (i / N_CLASSES) * span);

    const fmtSample = formatarMetrica(range.max, metrica);
    const unidade = fmtSample?.unidade ?? "";
    const fmtCurto = (v) => {
      const f = formatarMetrica(v, metrica);
      return f ? f.texto : String(Math.round(v));
    };

    const swatchGap = 6 * S;
    const totalItems = N_CLASSES + 1;
    const itemW = Math.floor((contentW - (totalItems - 1) * swatchGap) / totalItems);
    const swatchR = 3 * S;

    for (let i = 0; i < N_CLASSES; i++) {
      const sx = PAD + i * (itemW + swatchGap);
      const t = (i + 0.5) / N_CLASSES;
      const [r, g, b] = interpolaRGB(t, invertida);

      ctx.fillStyle = cor.texto; ctx.font = `${27*S}px ${FF}`;
      let label;
      if (i === 0)
        label = `Ate ${fmtCurto(breaks[1])}`;
      else if (i === N_CLASSES - 1)
        label = `> ${fmtCurto(breaks[N_CLASSES - 1])}`;
      else
        label = `${fmtCurto(breaks[i])} - ${fmtCurto(breaks[i + 1])}`;
      ctx.fillText(label, sx, y + legLabelH - 4*S);

      ctx.fillStyle = `rgb(${r},${g},${b})`;
      ctx.beginPath(); ctx.roundRect(sx, y + legLabelH, itemW, legSwatchH, swatchR); ctx.fill();
    }

    const sdX = PAD + N_CLASSES * (itemW + swatchGap);
    ctx.fillStyle = cor.texto; ctx.font = `${27*S}px ${FF}`;
    ctx.fillText("Sem dados", sdX, y + legLabelH - 4*S);
    ctx.fillStyle = cor.semDados;
    ctx.beginPath(); ctx.roundRect(sdX, y + legLabelH, itemW, legSwatchH, swatchR); ctx.fill();

    if (unidade.trim()) {
      ctx.fillStyle = cor.sutil; ctx.font = `italic ${24*S}px ${FF}`;
      ctx.fillText(`Valores em ${unidade.trim()}`, PAD, y + legLabelH + legSwatchH + 32*S);
    }
    y += legH;
  }

  // ═══ DESCRICAO / FILTROS (abaixo da legenda) ════════════════════════════════
  if (temBlocoExtra) {
    y += 14*S;
    ctx.strokeStyle = cor.separador; ctx.lineWidth = sepH;
    ctx.beginPath(); ctx.moveTo(PAD, y); ctx.lineTo(W - PAD, y); ctx.stroke();
    y += sepH + 14*S;

    if (descAbaixo && descLinhas.length > 0) {
      ctx.fillStyle = cor.sutil; ctx.font = descFont;
      for (const dl of descLinhas) {
        ctx.fillText(dl, PAD, y + 12*S);
        y += descLineH;
      }
    }

    if (filtrosLines.length > 0) {
      if (descLinhas.length > 0) y += 4*S;
      ctx.fillStyle = cor.subtitulo; ctx.font = `bold ${23*S}px ${FF}`;
      ctx.fillText("Filtros: ", PAD, y + 16*S);
      const filtroX = PAD + ctx.measureText("Filtros: ").width;
      ctx.fillStyle = cor.texto; ctx.font = `${23*S}px ${FF}`;
      ctx.fillText(filtrosLines.join("  \u2022  "), filtroX, y + 10*S);
      y += filtrosH;
    }
  }

  y += gapFoot;

  // ═══ RODAPE (estruturado: fonte/elaboracao esquerda, norte/escala direita) ══
  ctx.strokeStyle = cor.separador; ctx.lineWidth = sepH;
  ctx.beginPath(); ctx.moveTo(PAD, y); ctx.lineTo(W - PAD, y); ctx.stroke();
  y += 12*S;

  // Fonte (esquerda, linha 1)
  ctx.font = `bold ${20*S}px ${FF}`; ctx.fillStyle = cor.fonte;
  const fonteLabel = "Fonte: ";
  ctx.fillText(fonteLabel, PAD, y + 24*S);
  const fonteLabelW = ctx.measureText(fonteLabel).width;
  ctx.font = `${20*S}px ${FF}`; ctx.fillStyle = cor.texto;
  ctx.fillText(`${fonteDesc} \u2014 ${fonteSigla}`, PAD + fonteLabelW, y + 24*S);

  // Elaboracao (esquerda, linha 2)
  const d = new Date().toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" });
  ctx.font = `bold ${20*S}px ${FF}`; ctx.fillStyle = cor.fonte;
  const elabLabel = "Elaboracao: ";
  ctx.fillText(elabLabel, PAD, y + 52*S);
  const elabLabelW = ctx.measureText(elabLabel).width;
  ctx.font = `${20*S}px ${FF}`; ctx.fillStyle = cor.texto;
  ctx.fillText(`brasilemdados.ia.br (${d})`, PAD + elabLabelW, y + 52*S);

  // Coordenadas (esquerda, linha 3 — discretas)
  if (mostrarCoordenadas) {
    ctx.fillStyle = cor.sutil; ctx.font = `${18*S}px ${FF}`;
    const coordN = fmtCoord(bounds.north, "lat"), coordS = fmtCoord(bounds.south, "lat");
    const coordW = fmtCoord(bounds.west, "lon"), coordE = fmtCoord(bounds.east, "lon");
    ctx.fillText(`${coordN}/${coordS}  ${coordW}/${coordE}  |  SIRGAS 2000`, PAD, y + 78*S);
  }

  // Norte + escala (canto direito)
  if (mostrarNorte) {
    const nX = W - PAD - 24*S;

    // Norte: triangulo com metade preenchida (convencao cartografica)
    const nTop = y + 8*S, nBot = y + 40*S, nW = 13*S;
    // Metade esquerda preenchida
    ctx.fillStyle = cor.subtitulo;
    ctx.beginPath();
    ctx.moveTo(nX, nTop); ctx.lineTo(nX - nW, nBot); ctx.lineTo(nX, nBot * 0.4 + nTop * 0.6);
    ctx.closePath(); ctx.fill();
    // Metade direita apenas contorno
    ctx.strokeStyle = cor.subtitulo; ctx.lineWidth = 2*S; ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(nX, nTop); ctx.lineTo(nX + nW, nBot); ctx.lineTo(nX, nBot * 0.4 + nTop * 0.6);
    ctx.closePath(); ctx.stroke();
    // Haste
    ctx.lineWidth = 1.5*S;
    ctx.beginPath(); ctx.moveTo(nX, nBot); ctx.lineTo(nX, y + 56*S); ctx.stroke();
    ctx.lineCap = "butt";

    // Escala grafica (a esquerda do norte, mesma linha base)
    const mppScreen = metrosPorPixel(viewState.latitude, viewState.zoom);
    const mppReport = mppScreen * (mapCanvas.width / contentW);
    const esc = calcularEscala(mppReport, 100*S);
    const escEndX = nX - 36*S;
    const escStartX = escEndX - esc.px;
    const escY = y + 50*S;
    ctx.strokeStyle = cor.subtitulo; ctx.lineWidth = 2*S;
    ctx.beginPath(); ctx.moveTo(escStartX, escY); ctx.lineTo(escEndX, escY); ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(escStartX, escY - 6*S); ctx.lineTo(escStartX, escY + 6*S);
    ctx.moveTo(escEndX, escY - 6*S); ctx.lineTo(escEndX, escY + 6*S);
    ctx.stroke();
    ctx.fillStyle = cor.texto; ctx.font = `${23*S}px ${FF}`; ctx.textAlign = "right";
    ctx.fillText(esc.label, escEndX, escY - 10*S);
    ctx.textAlign = "left";
  }

  // ═══ EXPORTAR ou RETORNAR ═══════════════════════════════════════════════
  if (returnCanvas) return canvas;
  try {
    const link = document.createElement("a");
    link.download = `carta_${metrica}_${ano}_${tema}.jpg`;
    link.href = canvas.toDataURL("image/jpeg", 0.94);
    link.click();
  } catch (e) {
    alert("Erro ao exportar: canvas contaminado por CORS.\nDesative o satelite e tente novamente.");
  }
}


// ═════════════════════════════════════════════════════════════════════════════
//  PDF — Vetorial nativo (ISO 32000-1)
//  Texto: Helvetica Type1 (built-in, nao precisa embeddar)
//  Graficos: paths vetoriais
//  Mapa: JPEG XObject (unica parte raster)
// ═════════════════════════════════════════════════════════════════════════════

// WinAnsiEncoding: mapeamento de Unicode fora de ASCII para byte WinAnsi
const U2W = {0x2013:0x96,0x2014:0x97,0x2018:0x91,0x2019:0x92,0x201C:0x93,0x201D:0x94,0x2026:0x85,0x2022:0x95};

/** Escapa string JS para literal PDF (xxxx) em WinAnsiEncoding. */
function pdfS(s) {
  let r = "";
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c === 40 || c === 41 || c === 92) r += "\\" + s[i];        // ( ) backslash
    else if (c >= 32 && c <= 126) r += s[i];                        // ASCII printable
    else if (c >= 0xA0 && c <= 0xFF) r += "\\" + c.toString(8).padStart(3,"0"); // Latin-1
    else if (U2W[c] !== undefined) r += "\\" + U2W[c].toString(8).padStart(3,"0");
    else r += "?";
  }
  return r;
}

/** Converte hex (#RRGGBB) para "r g b" PDF (0-1). */
function rgb(hex) {
  return `${parseInt(hex.slice(1,3),16)/255} ${parseInt(hex.slice(3,5),16)/255} ${parseInt(hex.slice(5,7),16)/255}`;
}

function gerarPDF(opts) {
  const { mapCanvas, viewState, bounds, metrica, ano, nivel, nivelMeta,
          invertida, range, filtros, cid10Labels, adaptativo } = opts;

  // ── Pagina A3 landscape (pontos) ──
  const pw = 1190.55, ph = 841.89;
  const m = 28; // margem

  // Y no PDF: origem embaixo-esquerda
  const Y = (v) => (ph - v).toFixed(2);
  const X = (v) => v.toFixed(2);

  // ── Mapa como JPEG ──
  let jpegBytes;
  let mapExportavel = true;
  try {
    const jpegUrl = mapCanvas.toDataURL("image/jpeg", 0.98);
    const jpegBin = atob(jpegUrl.split(",")[1]);
    jpegBytes = new Uint8Array(jpegBin.length);
    for (let i = 0; i < jpegBin.length; i++) jpegBytes[i] = jpegBin.charCodeAt(i);
  } catch (_) {
    // Canvas tainted por CORS — gera placeholder 1×1 JPEG branco
    mapExportavel = false;
    jpegBytes = new Uint8Array([
      0xFF,0xD8,0xFF,0xE0,0x00,0x10,0x4A,0x46,0x49,0x46,0x00,0x01,0x01,0x00,0x00,0x01,
      0x00,0x01,0x00,0x00,0xFF,0xDB,0x00,0x43,0x00,0x08,0x06,0x06,0x07,0x06,0x05,0x08,
      0x07,0x07,0x07,0x09,0x09,0x08,0x0A,0x0C,0x14,0x0D,0x0C,0x0B,0x0B,0x0C,0x19,0x12,
      0x13,0x0F,0x14,0x1D,0x1A,0x1F,0x1E,0x1D,0x1A,0x1C,0x1C,0x20,0x24,0x2E,0x27,0x20,
      0x22,0x2C,0x23,0x1C,0x1C,0x28,0x37,0x29,0x2C,0x30,0x31,0x34,0x34,0x34,0x1F,0x27,
      0x39,0x3D,0x38,0x32,0x3C,0x2E,0x33,0x34,0x32,0xFF,0xC0,0x00,0x0B,0x08,0x00,0x01,
      0x00,0x01,0x01,0x01,0x11,0x00,0xFF,0xC4,0x00,0x1F,0x00,0x00,0x01,0x05,0x01,0x01,
      0x01,0x01,0x01,0x01,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x01,0x02,0x03,0x04,
      0x05,0x06,0x07,0x08,0x09,0x0A,0x0B,0xFF,0xC4,0x00,0xB5,0x10,0x00,0x02,0x01,0x03,
      0x03,0x02,0x04,0x03,0x05,0x05,0x04,0x04,0x00,0x00,0x01,0x7D,0x01,0x02,0x03,0x00,
      0x04,0x11,0x05,0x12,0x21,0x31,0x41,0x06,0x13,0x51,0x61,0x07,0x22,0x71,0x14,0x32,
      0x81,0x91,0xA1,0x08,0x23,0x42,0xB1,0xC1,0x15,0x52,0xD1,0xF0,0x24,0x33,0x62,0x72,
      0x82,0x09,0x0A,0x16,0x17,0x18,0x19,0x1A,0x25,0x26,0x27,0x28,0x29,0x2A,0x34,0x35,
      0x36,0x37,0x38,0x39,0x3A,0x43,0x44,0x45,0x46,0x47,0x48,0x49,0x4A,0x53,0x54,0x55,
      0x56,0x57,0x58,0x59,0x5A,0x63,0x64,0x65,0x66,0x67,0x68,0x69,0x6A,0x73,0x74,0x75,
      0x76,0x77,0x78,0x79,0x7A,0x83,0x84,0x85,0x86,0x87,0x88,0x89,0x8A,0x92,0x93,0x94,
      0x95,0x96,0x97,0x98,0x99,0x9A,0xA2,0xA3,0xA4,0xA5,0xA6,0xA7,0xA8,0xA9,0xAA,0xB2,
      0xB3,0xB4,0xB5,0xB6,0xB7,0xB8,0xB9,0xBA,0xC2,0xC3,0xC4,0xC5,0xC6,0xC7,0xC8,0xC9,
      0xCA,0xD2,0xD3,0xD4,0xD5,0xD6,0xD7,0xD8,0xD9,0xDA,0xE1,0xE2,0xE3,0xE4,0xE5,0xE6,
      0xE7,0xE8,0xE9,0xEA,0xF1,0xF2,0xF3,0xF4,0xF5,0xF6,0xF7,0xF8,0xF9,0xFA,0xFF,0xDA,
      0x00,0x08,0x01,0x01,0x00,0x00,0x3F,0x00,0x7B,0x94,0x11,0x00,0x00,0x00,0x00,0x7F,
      0xFF,0xD9,
    ]);
  }

  const direcao = obterIndicadorDirecao(metrica, invertida).replace(/[\u2191]/g, "^");
  const geometria = nivelMeta?.geometria ?? nivel;

  // ── Layout em pontos ──
  const cw = pw - 2*m; // largura util
  const headerH = 62;
  const mapAR = mapCanvas.height / mapCanvas.width;
  const mapW = cw;
  const mapH = Math.min(mapW * mapAR, ph - headerH - 220);
  const mapTop = m + headerH + 4;
  const legendTop = mapTop + mapH + 10;
  const legendH = 82;
  const temF = temFiltrosAtivos(filtros);
  const filtrosTop = legendTop + legendH + 2;
  const metaTop = filtrosTop + (temF ? 16 : 0) + 2;
  const footerH = 28;

  // Escala grafica: metros por ponto PDF no mapa
  const mppScreen = metrosPorPixel(viewState.latitude, viewState.zoom);
  const mppPDF = mppScreen * (mapCanvas.width / mapW);

  // ── Titulo, fonte, filtros (pre-computados) ──
  const titulo = METRICA_LABEL_LONGO[metrica] ?? metrica;
  const tituloSafe = titulo.replace(/[—–]/g, "-");
  let geo = "Brasil";
  if (filtros.cod_uf) geo = UF_NOMES_COMPLETOS[filtros.cod_uf] ?? geo;
  const subtitulo = `${geo} - ${nivelMeta?.label ?? nivel} - ${ano}`;
  const [fonteSigla, fonteDesc] = obterFonte(metrica);
  const dataStr = new Date().toLocaleDateString("pt-BR", {day:"2-digit",month:"long",year:"numeric"});
  const filtrosArr = filtrosTexto(filtros, cid10Labels);

  // ── Content stream ──
  const cs = [];

  // Fundo
  cs.push(`${rgb("#0d0f17")} rg`);
  cs.push(`0 0 ${pw} ${ph} re f`);

  // ── Moldura dupla ──
  cs.push(`${rgb("#a0aec0")} RG 1.5 w`);
  cs.push(`${m} ${m} ${cw} ${ph-2*m} re S`);
  cs.push(`${rgb("#2d3748")} RG 0.5 w`);
  cs.push(`${m+3} ${m+3} ${cw-6} ${ph-2*m-6} re S`);

  // ── Header ──
  cs.push(`BT /F2 18 Tf ${rgb("#e2e8f0")} rg ${X(m+8)} ${Y(m+22)} Td (${pdfS(tituloSafe)}) Tj ET`);
  cs.push(`BT /F1 11 Tf ${rgb("#a0aec0")} rg ${X(m+8)} ${Y(m+38)} Td (${pdfS(subtitulo)}) Tj ET`);
  cs.push(`BT /F3 8 Tf ${rgb("#718096")} rg ${X(m+8)} ${Y(m+52)} Td (${pdfS(`Carta tematica coropletica - ${geometria}`)}) Tj ET`);
  // Data e executor (direita)
  cs.push(`BT /F1 8 Tf ${rgb("#718096")} rg ${X(pw-m-200)} ${Y(m+22)} Td (${pdfS("Elaboracao: " + dataStr)}) Tj ET`);
  cs.push(`BT /F2 9 Tf ${rgb("#a0aec0")} rg ${X(pw-m-200)} ${Y(m+36)} Td (Brasil em Dados) Tj ET`);
  cs.push(`BT /F1 7 Tf ${rgb("#718096")} rg ${X(pw-m-200)} ${Y(m+48)} Td (Painel Geoespacial Interativo) Tj ET`);

  // Separador header
  cs.push(`${rgb("#2d3748")} RG 0.5 w`);
  cs.push(`${m+8} ${Y(m+headerH)} m ${pw-m-8} ${Y(m+headerH)} l S`);

  // ── Mapa (imagem JPEG) ──
  if (mapExportavel) {
    cs.push("q");
    cs.push(`${mapW.toFixed(2)} 0 0 ${mapH.toFixed(2)} ${X(m)} ${Y(mapTop+mapH)} cm`);
    cs.push("/Map Do");
    cs.push("Q");
  } else {
    // Placeholder quando mapa nao exportavel
    cs.push(`q ${rgb("#1a1d2e")} rg ${X(m)} ${Y(mapTop)} ${mapW.toFixed(2)} ${(-mapH).toFixed(2)} re f Q`);
    cs.push(`BT /F1 12 Tf ${rgb("#718096")} rg ${X(m+mapW/2-120)} ${Y(mapTop+mapH/2)} Td (Mapa indisponivel - desative satelite e recarregue) Tj ET`);
  }

  // Moldura do mapa
  cs.push(`${rgb("#e2e8f0")} RG 1 w`);
  cs.push(`${X(m)} ${Y(mapTop)} ${mapW.toFixed(2)} ${(-mapH).toFixed(2)} re S`);

  // ── Coordenadas NW e SE ──
  if (bounds) {
    const nw = `${fmtCoord(bounds.north,"lat")}  ${fmtCoord(bounds.west,"lon")}`;
    const se = `${fmtCoord(bounds.south,"lat")}  ${fmtCoord(bounds.east,"lon")}`;
    cs.push(`q`);
    cs.push(`BT /F1 7 Tf ${rgb("#a0aec0")} rg ${X(m+4)} ${Y(mapTop+10)} Td (${pdfS(nw)}) Tj ET`);
    cs.push("Q");
    cs.push(`q`);
    cs.push(`BT /F1 7 Tf ${rgb("#a0aec0")} rg ${X(pw-m-160)} ${Y(mapTop+mapH-4)} Td (${pdfS(se)}) Tj ET`);
    cs.push("Q");
  }

  // ── Seta norte (vetorial) ──
  const ncx = pw - m - 24, ncy = mapTop + 24, nr = 16;
  const k = 0.5523;
  cs.push(`q ${rgb("#0d0f17")} rg 0.8 g RG 0.75 w`);
  cs.push(`${X(ncx+nr)} ${Y(ncy)} m`);
  cs.push(`${X(ncx+nr)} ${Y(ncy-k*nr)} ${X(ncx+k*nr)} ${Y(ncy-nr)} ${X(ncx)} ${Y(ncy-nr)} c`);
  cs.push(`${X(ncx-k*nr)} ${Y(ncy-nr)} ${X(ncx-nr)} ${Y(ncy-k*nr)} ${X(ncx-nr)} ${Y(ncy)} c`);
  cs.push(`${X(ncx-nr)} ${Y(ncy+k*nr)} ${X(ncx-k*nr)} ${Y(ncy+nr)} ${X(ncx)} ${Y(ncy+nr)} c`);
  cs.push(`${X(ncx+k*nr)} ${Y(ncy+nr)} ${X(ncx+nr)} ${Y(ncy+k*nr)} ${X(ncx+nr)} ${Y(ncy)} c`);
  cs.push("B Q");
  const na = nr * 0.55;
  cs.push(`q ${rgb("#e2e8f0")} rg`);
  cs.push(`${X(ncx)} ${Y(ncy-na)} m ${X(ncx+na*0.28)} ${Y(ncy+na*0.12)} l ${X(ncx)} ${Y(ncy-na*0.05)} l f`);
  cs.push("Q");
  cs.push(`q ${rgb("#2d3748")} rg ${rgb("#e2e8f0")} RG 0.5 w`);
  cs.push(`${X(ncx)} ${Y(ncy-na)} m ${X(ncx-na*0.28)} ${Y(ncy+na*0.12)} l ${X(ncx)} ${Y(ncy-na*0.05)} l B`);
  cs.push("Q");
  cs.push(`BT /F2 9 Tf ${rgb("#e2e8f0")} rg ${X(ncx-3)} ${Y(ncy-nr+5)} Td (N) Tj ET`);

  // ── Mapa de enquadramento (se UF selecionada) ──
  if (filtros.cod_uf) {
    const iW=80, iH=72, ix=m+6, iy=mapTop+mapH-iH-6;
    cs.push(`q ${rgb("#111520")} rg ${rgb("#2d3748")} RG 1 w`);
    cs.push(`${X(ix)} ${Y(iy)} ${iW} ${-iH} re B Q`);
    const proj = (lon,lat) => [ix+4+((lon+75)/42)*(iW-8), iy+4+((6-lat)/40.5)*(iH-8)];
    cs.push(`q ${rgb("#1a2030")} rg ${rgb("#4a5568")} RG 0.5 w`);
    BRASIL_CONTORNO.forEach(([lo,la],i) => {
      const [px,py] = proj(lo,la);
      cs.push(`${X(px)} ${Y(py)} ${i===0?"m":"l"}`);
    });
    cs.push("b Q");
    if (UF_CENTROIDS[filtros.cod_uf]) {
      const [lo,la] = UF_CENTROIDS[filtros.cod_uf];
      const [px,py] = proj(lo,la);
      cs.push(`q ${rgb("#4299e1")} rg`);
      cs.push(`${X(px+3)} ${Y(py)} m ${X(px+3)} ${Y(py-1.66)} ${X(px+1.66)} ${Y(py-3)} ${X(px)} ${Y(py-3)} c`);
      cs.push(`${X(px-1.66)} ${Y(py-3)} ${X(px-3)} ${Y(py-1.66)} ${X(px-3)} ${Y(py)} c`);
      cs.push(`${X(px-3)} ${Y(py+1.66)} ${X(px-1.66)} ${Y(py+3)} ${X(px)} ${Y(py+3)} c`);
      cs.push(`${X(px+1.66)} ${Y(py+3)} ${X(px+3)} ${Y(py+1.66)} ${X(px+3)} ${Y(py)} c f Q`);
    }
    cs.push(`BT /F1 5 Tf ${rgb("#718096")} rg ${X(ix+4)} ${Y(iy+8)} Td (LOCALIZACAO) Tj ET`);
  }

  // ── Painel de detalhes da feature selecionada (sobre o mapa) ──
  if (opts.featureSelecionada) {
    const fp = opts.featureSelecionada?.properties ?? {};
    const fIsUF = fp.sigla != null || fp.regiao != null;
    const fNome = fp.nome_municipio || fp.nome || fp.sigla || `Setor ${fp.cod_setor ?? ""}`;
    const fMetricaLabel = (METRICA_LABEL_CURTO[metrica] ?? metrica).replace(/[—–]/g, "-");
    const fValor = formatarMetrica(fp.valor_metrica, metrica);
    const fPop = fp.populacao_2022 ?? fp.populacao_total;
    const fGeocod = fp.cod_ibge_7 ? `IBGE: ${fp.cod_ibge_7}` : fp.sigla ? `UF: ${fp.sigla}` : fp.cod_setor ? `Setor: ${fp.cod_setor}` : "";

    const px = m + 6, py = mapTop + 6, pw2 = 180, ph2 = 80;
    // Fundo do painel
    cs.push(`q ${rgb("#0d0f17")} rg 0.92 g`);
    cs.push(`${X(px)} ${Y(py)} ${pw2} ${-ph2} re f Q`);
    cs.push(`${rgb("#2d3748")} RG 0.5 w ${X(px)} ${Y(py)} ${pw2} ${-ph2} re S`);
    // Nome
    cs.push(`BT /F2 10 Tf ${rgb("#e2e8f0")} rg ${X(px+6)} ${Y(py+12)} Td (${pdfS(fNome)}) Tj ET`);
    if (fIsUF && fp.regiao) {
      cs.push(`BT /F1 7 Tf ${rgb("#718096")} rg ${X(px+6)} ${Y(py+22)} Td (${pdfS(fp.regiao)}) Tj ET`);
    }
    // Indicador
    cs.push(`q ${rgb("#4299e1")} rg 0.15 g`);
    cs.push(`${X(px+4)} ${Y(py+28)} ${pw2-8} ${-28} re f Q`);
    cs.push(`${rgb("#4299e1")} RG 0.3 w ${X(px+4)} ${Y(py+28)} ${pw2-8} ${-28} re S`);
    cs.push(`BT /F1 6 Tf ${rgb("#4299e1")} rg ${X(px+8)} ${Y(py+36)} Td (${pdfS(`${fMetricaLabel} - ${ano}`)}) Tj ET`);
    if (fValor) {
      cs.push(`BT /F2 12 Tf ${rgb("#e2e8f0")} rg ${X(px+8)} ${Y(py+50)} Td (${pdfS(fValor.texto + fValor.unidade)}) Tj ET`);
    } else {
      cs.push(`BT /F3 8 Tf ${rgb("#718096")} rg ${X(px+8)} ${Y(py+48)} Td (sem dados) Tj ET`);
    }
    // Populacao
    if (fPop != null) {
      cs.push(`BT /F1 7 Tf ${rgb("#a0aec0")} rg ${X(px+6)} ${Y(py+64)} Td (Pop: ${Number(fPop).toLocaleString("pt-BR", {maximumFractionDigits:0})}) Tj ET`);
    }
    // Geocod
    if (fGeocod) {
      cs.push(`BT /F1 6 Tf ${rgb("#718096")} rg ${X(px+6)} ${Y(py+74)} Td (${pdfS(fGeocod)}) Tj ET`);
    }
  }

  // ── LEGENDA ──
  cs.push(`BT /F2 9 Tf ${rgb("#e2e8f0")} rg ${X(m+8)} ${Y(legendTop+12)} Td (LEGENDA) Tj ET`);

  // Rampa continua (100 rects vetoriais)
  const rampX = m + 8, rampY = legendTop + 18, rampW = cw * 0.50, rampH = 10;
  for (let i = 0; i < 100; i++) {
    const [r,g,b] = interpolaRGB(i / 99, invertida);
    cs.push(`${(r/255).toFixed(3)} ${(g/255).toFixed(3)} ${(b/255).toFixed(3)} rg`);
    cs.push(`${X(rampX + i * rampW / 100)} ${Y(rampY)} ${(rampW/100+0.5).toFixed(2)} ${-rampH} re f`);
  }
  cs.push(`${rgb("#e2e8f0")} RG 0.3 w`);
  cs.push(`${X(rampX)} ${Y(rampY)} ${rampW.toFixed(2)} ${-rampH} re S`);

  // Tick marks + rotulos a cada 20%
  for (let p = 0; p <= 5; p++) {
    const t = p / 5;
    const tx = rampX + t * rampW;
    cs.push(`${X(tx)} ${Y(rampY + rampH)} m ${X(tx)} ${Y(rampY + rampH + 3)} l S`);
    const val = range.min + t * (range.max - range.min);
    const lbl = formatarParaLegenda(val, metrica).replace(/[—–]/g, "-");
    const labelX = p === 0 ? tx : p === 5 ? tx - 30 : tx - 12;
    cs.push(`BT /F1 7 Tf ${rgb("#a0aec0")} rg ${X(labelX)} ${Y(rampY + rampH + 12)} Td (${pdfS(lbl)}) Tj ET`);
  }

  // Indicador de direcao (sentido da escala)
  const direcaoX = rampX + rampW / 2 - 25;
  cs.push(`BT /F2 7 Tf ${rgb("#4299e1")} rg ${X(direcaoX)} ${Y(rampY + rampH + 22)} Td (${pdfS(direcao)}) Tj ET`);

  // Sem dados (convencao cartografica)
  cs.push(`q ${rgb("#4a5568")} rg ${X(rampX)} ${Y(rampY+rampH+30)} 8 -6 re f Q`);
  cs.push(`${rgb("#e2e8f0")} RG 0.2 w ${X(rampX)} ${Y(rampY+rampH+30)} 8 -6 re S`);
  cs.push(`BT /F1 7 Tf ${rgb("#718096")} rg ${X(rampX+12)} ${Y(rampY+rampH+35)} Td (Sem dados / nao aplicavel) Tj ET`);

  // Unidades de analise
  cs.push(`BT /F1 7 Tf ${rgb("#718096")} rg ${X(rampX)} ${Y(rampY+rampH+46)} Td (${pdfS(`Unidades de analise: ${geometria}`)}) Tj ET`);

  // ── Coluna direita: metodo de classificacao ──
  const lmX = rampX + rampW + 20;
  cs.push(`BT /F2 7 Tf ${rgb("#718096")} rg ${X(lmX)} ${Y(legendTop+12)} Td (METODO DE CLASSIFICACAO) Tj ET`);
  cs.push(`BT /F1 8 Tf ${rgb("#a0aec0")} rg ${X(lmX)} ${Y(legendTop+24)} Td (Normalizacao quantilica \\(percentil\\)) Tj ET`);
  if (adaptativo) {
    cs.push(`BT /F1 7 Tf ${rgb("#718096")} rg ${X(lmX)} ${Y(legendTop+36)} Td (Limites adaptativos: P2 / P98 dos dados carregados) Tj ET`);
  } else {
    cs.push(`BT /F1 7 Tf ${rgb("#718096")} rg ${X(lmX)} ${Y(legendTop+36)} Td (Faixa pre-definida por metrica) Tj ET`);
  }
  cs.push(`BT /F1 7 Tf ${rgb("#718096")} rg ${X(lmX)} ${Y(legendTop+48)} Td (Rampa continua 6 paradas: Azul > Teal > Verde > Amarelo > Laranja > Violeta) Tj ET`);

  // Faixa numerica
  const rangeMin = formatarParaLegenda(range.min, metrica).replace(/[—–]/g, "-");
  const rangeMax = formatarParaLegenda(range.max, metrica).replace(/[—–]/g, "-");
  cs.push(`BT /F1 7 Tf ${rgb("#a0aec0")} rg ${X(lmX)} ${Y(legendTop+60)} Td (${pdfS(`Faixa: ${rangeMin} a ${rangeMax}`)}) Tj ET`);

  // ── Filtros ──
  if (temF && filtrosArr.length > 0) {
    cs.push(`BT /F2 7 Tf ${rgb("#718096")} rg ${X(m+8)} ${Y(filtrosTop+10)} Td (FILTROS APLICADOS:  ) Tj`);
    cs.push(`/F1 8 Tf ${rgb("#a0aec0")} rg (${pdfS(filtrosArr.join("  |  "))}) Tj ET`);
  }

  // ── Separador ──
  cs.push(`${rgb("#2d3748")} RG 0.3 w`);
  cs.push(`${X(m+8)} ${Y(metaTop)} m ${X(pw-m-8)} ${Y(metaTop)} l S`);

  // ── Escala grafica (barra alternada) ──
  const esc = calcularEscala(mppPDF, 160);
  const bW = esc.px, bH = 5, bY = metaTop + 8;
  for (let i = 0; i < 4; i++) {
    const col = i % 2 === 0 ? rgb("#e2e8f0") : rgb("#2d3748");
    cs.push(`${col} rg ${X(m+8+i*bW/4)} ${Y(bY)} ${(bW/4).toFixed(2)} ${-bH} re f`);
  }
  cs.push(`${rgb("#e2e8f0")} RG 0.5 w ${X(m+8)} ${Y(bY)} ${bW.toFixed(2)} ${-bH} re S`);
  cs.push(`BT /F2 8 Tf ${rgb("#e2e8f0")} rg ${X(m+8)} ${Y(bY+bH+10)} Td (0) Tj ET`);
  cs.push(`BT /F2 8 Tf ${rgb("#e2e8f0")} rg ${X(m+8+bW-20)} ${Y(bY+bH+10)} Td (${pdfS(esc.label)}) Tj ET`);

  // ── Referencia geodesica (coluna 2) ──
  const gX = m + 220;
  cs.push(`BT /F2 7 Tf ${rgb("#718096")} rg ${X(gX)} ${Y(metaTop+10)} Td (REFERENCIA GEODESICA) Tj ET`);
  cs.push(`BT /F1 8 Tf ${rgb("#a0aec0")} rg ${X(gX)} ${Y(metaTop+22)} Td (Datum: SIRGAS 2000 \\(EPSG:4674\\)) Tj ET`);
  cs.push(`BT /F1 8 Tf ${rgb("#a0aec0")} rg ${X(gX)} ${Y(metaTop+34)} Td (Projecao: Web Mercator \\(EPSG:3857\\)) Tj ET`);
  cs.push(`BT /F1 7 Tf ${rgb("#718096")} rg ${X(gX)} ${Y(metaTop+46)} Td (Armazenamento: EPSG:4674 | Visualizacao: EPSG:3857) Tj ET`);

  // ── Fonte dos dados (coluna 3) ──
  const fX = m + 520;
  cs.push(`BT /F2 7 Tf ${rgb("#718096")} rg ${X(fX)} ${Y(metaTop+10)} Td (FONTE DOS DADOS) Tj ET`);
  cs.push(`BT /F1 8 Tf ${rgb("#a0aec0")} rg ${X(fX)} ${Y(metaTop+22)} Td (${pdfS(fonteSigla)}) Tj ET`);
  cs.push(`BT /F1 7 Tf ${rgb("#718096")} rg ${X(fX)} ${Y(metaTop+34)} Td (${pdfS(fonteDesc)}) Tj ET`);
  cs.push(`BT /F1 7 Tf ${rgb("#718096")} rg ${X(fX)} ${Y(metaTop+46)} Td (Base cartografica: IBGE - Malha Municipal 2022) Tj ET`);

  // ── Rodape ──
  cs.push(`${rgb("#0a0c12")} rg ${X(m+4)} ${Y(ph-m-4)} ${(cw-8).toFixed(2)} ${-footerH} re f`);
  cs.push(`BT /F2 8 Tf ${rgb("#a0aec0")} rg ${X(m+12)} ${Y(ph-m-4+10)} Td (Brasil em Dados - Painel Geoespacial Interativo do Brasil) Tj ET`);
  cs.push(`BT /F1 6 Tf ${rgb("#718096")} rg ${X(m+12)} ${Y(ph-m-4+22)} Td (ABNT NBR 15777:2009 | Datum SIRGAS 2000 - Res. IBGE R.PR-01/2015 | brasilemdados.ia.br) Tj ET`);
  cs.push(`BT /F1 6 Tf ${rgb("#718096")} rg ${X(pw-m-200)} ${Y(ph-m-4+22)} Td (${pdfS(`Zoom: ${viewState.zoom.toFixed(1)} | Nivel: ${nivelMeta?.label??nivel}`)}) Tj ET`);

  // ── Montar PDF ──
  const contentStr = cs.join("\n");
  const enc = new TextEncoder();
  const parts = [];
  const off = [];

  parts.push(enc.encode("%PDF-1.4\n%\xE2\xE3\xCF\xD3\n"));

  // Obj 1: Catalog
  off[1] = parts.reduce((a,p)=>a+p.length,0);
  parts.push(enc.encode("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"));

  // Obj 2: Pages
  off[2] = parts.reduce((a,p)=>a+p.length,0);
  parts.push(enc.encode("2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"));

  // Obj 3: Page — inclui XObject /Map mesmo se placeholder (1×1 JPEG)
  off[3] = parts.reduce((a,p)=>a+p.length,0);
  const imgW = mapExportavel ? mapCanvas.width : 1;
  const imgH = mapExportavel ? mapCanvas.height : 1;
  parts.push(enc.encode(`3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pw} ${ph}]\n/Contents 4 0 R\n/Resources <<\n  /Font << /F1 5 0 R /F2 6 0 R /F3 7 0 R >>\n  /XObject << /Map 8 0 R >>\n>>\n>>\nendobj\n`));

  // Obj 4: Content stream
  off[4] = parts.reduce((a,p)=>a+p.length,0);
  const contentBytes = enc.encode(contentStr);
  parts.push(enc.encode(`4 0 obj\n<< /Length ${contentBytes.length} >>\nstream\n`));
  parts.push(contentBytes);
  parts.push(enc.encode("\nendstream\nendobj\n"));

  // Obj 5: Font Helvetica
  off[5] = parts.reduce((a,p)=>a+p.length,0);
  parts.push(enc.encode("5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\nendobj\n"));

  // Obj 6: Font Helvetica-Bold
  off[6] = parts.reduce((a,p)=>a+p.length,0);
  parts.push(enc.encode("6 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>\nendobj\n"));

  // Obj 7: Font Helvetica-Oblique
  off[7] = parts.reduce((a,p)=>a+p.length,0);
  parts.push(enc.encode("7 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique /Encoding /WinAnsiEncoding >>\nendobj\n"));

  // Obj 8: Map image (JPEG XObject)
  off[8] = parts.reduce((a,p)=>a+p.length,0);
  parts.push(enc.encode(`8 0 obj\n<< /Type /XObject /Subtype /Image /Width ${imgW} /Height ${imgH} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpegBytes.length} >>\nstream\n`));
  parts.push(jpegBytes);
  parts.push(enc.encode("\nendstream\nendobj\n"));

  // XRef
  const xrefOff = parts.reduce((a,p)=>a+p.length,0);
  let xref = "xref\n0 9\n0000000000 65535 f \n";
  for (let i = 1; i <= 8; i++) xref += `${String(off[i]).padStart(10,"0")} 00000 n \n`;
  xref += `trailer\n<< /Size 9 /Root 1 0 R >>\nstartxref\n${xrefOff}\n%%EOF`;
  parts.push(enc.encode(xref));

  // Download
  const total = parts.reduce((a,p)=>a+p.length,0);
  const pdf = new Uint8Array(total);
  let pos = 0;
  for (const p of parts) { pdf.set(p, pos); pos += p.length; }

  const url = URL.createObjectURL(new Blob([pdf], { type: "application/pdf" }));
  const link = document.createElement("a");
  link.download = `carta-tematica_${metrica}_${ano}_${nivel}.pdf`;
  link.href = url;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
