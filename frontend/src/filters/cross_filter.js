/**
 * cross_filter.js
 * Gerencia os filtros multidimensionais do painel.
 *
 * Todos os filtros — incluindo faixa etária e cor/raça — são enviados como
 * query params server-side para o Martin. O PostGIS agrega os registros
 * individuais de sim_mortalidade aplicando os filtros demográficos antes
 * de calcular a taxa por 100k. Isso garante que o mapa sempre mostre dados
 * corretos independentemente de como os filtros são combinados.
 */

import { create } from "zustand";

// Anos-padrão por métrica (fallback até o fetch da API completar).
// Mostra apenas o último ano com dados confirmados para evitar mapa em branco.
export const ANOS_POR_METRICA_DEFAULT = {
  taxa_mortalidade:   [2023],
  taxa_homicidio:     [2023],
  pib_per_capita:     [2022],
  receita_per_capita: [2022],
  densidade_pop:      [2022],
};

// Re-exporta para compatibilidade com imports existentes
export const ANOS_POR_METRICA = ANOS_POR_METRICA_DEFAULT;

// ─────────────────────────────────────────────────────────────────────────────
// Store Zustand: estado global dos filtros
// ─────────────────────────────────────────────────────────────────────────────
export const useFiltrosStore = create((set, get) => ({
  // Filtros server-side (mudar recarrega tiles)
  ano: 2023,
  cod_uf: null,
  cid10_capitulo: null,
  metrica: "taxa_mortalidade",

  // Filtros demográficos (também server-side — passados ao PostGIS via Martin)
  faixa_etaria_min: 0,
  faixa_etaria_max: 17,
  cor_raca: null,  // null = todos; 1=Branca, 2=Preta, 4=Parda, 5=Indígena

  // Anos disponíveis por métrica — preenchido pelo fetch da API em main.jsx
  anosDisponiveis: ANOS_POR_METRICA_DEFAULT,

  // Ações
  setAno: (ano) => set({ ano }),
  setUF: (cod_uf) => set({ cod_uf }),
  setCID10: (cid10_capitulo) => set({ cid10_capitulo }),
  setMetrica: (metrica) => {
    const anos = get().anosDisponiveis[metrica] ?? [2023];
    const currentAno = get().ano;
    set({ metrica, ano: anos.includes(currentAno) ? currentAno : anos[0] });
  },
  setFaixaEtaria: ([min, max]) => set({ faixa_etaria_min: min, faixa_etaria_max: max }),
  setCorRaca: (cor_raca) => set({ cor_raca }),
  setAnosDisponiveis: (anosDisponiveis) => {
    // Quando os anos chegam, corrige o ano selecionado se não estiver disponível
    const { metrica, ano } = get();
    const anos = anosDisponiveis[metrica] ?? [2023];
    set({ anosDisponiveis, ano: anos.includes(ano) ? ano : anos[0] });
  },

  resetFiltros: () => set({
    ano: get().anosDisponiveis["taxa_mortalidade"]?.[0] ?? 2023,
    cod_uf: null,
    cid10_capitulo: null,
    metrica: "taxa_mortalidade",
    faixa_etaria_min: 0,
    faixa_etaria_max: 17,
    cor_raca: null,
  }),

  // Serializa os filtros como query params para o Martin.
  // Filtros demográficos só são incluídos quando não estão no valor padrão
  // (evita fragmentar o cache para métricas que não os usam).
  getServerParams: () => {
    const { ano, cod_uf, cid10_capitulo, metrica, faixa_etaria_min, faixa_etaria_max, cor_raca } = get();
    const params = { ano, cod_uf, cid10_capitulo, metrica };

    // Filtros demográficos afetam apenas métricas de saúde
    if (metrica === "taxa_mortalidade" || metrica === "taxa_homicidio") {
      if (faixa_etaria_min !== 0 || faixa_etaria_max !== 17) {
        params.faixa_etaria_min = faixa_etaria_min;
        params.faixa_etaria_max = faixa_etaria_max;
      }
      if (cor_raca !== null) {
        params.cor_raca = cor_raca;
      }
    }
    return params;
  },
}));
