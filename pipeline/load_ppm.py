#!/usr/bin/env python3
"""
load_ppm.py
Carrega dados da Pesquisa Pecuária Municipal (PPM) do IBGE SIDRA para
api.metricas_municipio.

Fontes:
  T3939 — Efetivo dos rebanhos por tipo de rebanho (bovino, suíno, ovino, etc.)
  T74   — Produção de leite, mel e ovos

Indicadores carregados (anuais):
  rebanho_bovino_por_km2     — cabeças bovinas / km² (T3939 V105)
  rebanho_bovino_por_hab     — cabeças bovinas / habitante (T3939 V105)
  rebanho_suino_por_hab      — cabeças suínas / habitante (T3939 V107)
  rebanho_ovino_por_hab      — cabeças ovinas / habitante (T3939 V108)
  rebanho_caprino_por_hab    — cabeças caprinas / habitante (T3939 V109)
  rebanho_galinaceos_por_hab — galináceos / habitante (T3939 V112)
  rebanho_equino_por_hab     — equinos / habitante (T3939 V106)
  producao_leite_por_vaca    — litros de leite por vaca ordenhada (T74 V214/V213)
  producao_mel_por_colmeia   — kg de mel por colmeia (T74 V216/V2356)
  producao_ovos_total        — mil dúzias de ovos (T74 V217, valores absolutos)

Uso:
    python load_ppm.py                             # 2019-2023, todos indicadores
    python load_ppm.py --anos 2020 2021 2022       # anos específicos
    python load_ppm.py --skip-bovino --skip-leite  # pula indicadores
"""

import argparse
import os
import time

import psycopg2
import requests
from psycopg2.extras import execute_values

DB_PARAMS = dict(
    host=os.environ.get("POSTGRES_HOST", "localhost"),
    port=int(os.environ.get("POSTGRES_PORT", 5432)),
    database=os.environ.get("POSTGRES_DB", "brasil_dados"),
    user=os.environ.get("POSTGRES_USER", "brasil"),
    password=os.environ.get("POSTGRES_PASSWORD", ""),
)

SIDRA_BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"


def sidra_fetch(tabela: int, variavel: int, periodo: int | str,
                classificacao: str = None) -> dict[int, float]:
    """
    Baixa dados para todos os municípios (N6[all]).
    Retorna dict {cod_municipio_7digits: valor}.
    classificacao: e.g. "79[2670]" para bovino em T3939.
    """
    url = (
        f"{SIDRA_BASE}/{tabela}/periodos/{periodo}/variaveis/{variavel}"
        f"?localidades=N6[all]"
    )
    if classificacao:
        url += f"&classificacao={classificacao}"
    print(f"  GET T{tabela} V{variavel} C={classificacao or 'all'} {periodo} ...")
    for tentativa in range(3):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200:
                break
            print(f"    HTTP {r.status_code}, aguardando 10s...")
            time.sleep(10)
        except requests.exceptions.Timeout:
            print(f"    Timeout tentativa {tentativa+1}/3, aguardando 10s...")
            time.sleep(10)
    else:
        print(f"  ERRO: T{tabela} V{variavel} {periodo} falhou após 3 tentativas")
        return {}

    resultado = {}
    for bloco in r.json():
        for res_item in bloco.get("resultados", []):
            for serie in res_item.get("series", []):
                try:
                    cod = int(serie["localidade"]["id"])
                    val_str = serie["serie"].get(str(periodo), "-")
                    if val_str and val_str not in ("-", "...", "X", "", ".."):
                        resultado[cod] = float(val_str)
                except (ValueError, KeyError):
                    pass
    print(f"    → {len(resultado)} municípios")
    return resultado


def upsert_metricas(rows: list[tuple], conn):
    """Insere/atualiza registros em api.metricas_municipio."""
    if not rows:
        print("  Sem dados para inserir.")
        return
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO api.metricas_municipio (cod_municipio, metrica, ano, valor)
            VALUES %s
            ON CONFLICT (cod_municipio, metrica, ano)
            DO UPDATE SET valor = EXCLUDED.valor
            """,
            rows,
            page_size=2000,
        )
    conn.commit()
    print(f"  Upserted {len(rows):,} registros em api.metricas_municipio")


def get_geo_maps(conn) -> tuple[dict, dict]:
    """
    Retorna (pop_map, area_map): {cod_ibge_7: populacao_2022}, {cod_ibge_7: area_km2}.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT cod_ibge_7, populacao_2022, area_km2 FROM geo.municipios"
        )
        rows = cur.fetchall()
    pop_map  = {r[0]: float(r[1]) for r in rows if r[1] and r[1] > 0}
    area_map = {r[0]: float(r[2]) for r in rows if r[2] and r[2] > 0}
    return pop_map, area_map


# T3939 tem apenas V105 (Efetivo dos rebanhos). O tipo de animal é
# especificado via classificação 79[categoria]. IDs das categorias:
REBANHO_CATS = {
    "bovino":     2670,
    "equino":     2672,
    "suino":      32794,
    "ovino":      2677,
    "caprino":    2681,
    "galinaceos": 32796,
}

# ─── T3939 — Rebanhos ─────────────────────────────────────────────────────────

def carregar_rebanho(conn, nome_animal: str,
                     anos: list[int],
                     pop_map: dict, area_map: dict,
                     skip_km2: bool = False):
    """
    Carrega efetivo de um rebanho (T3939 V105) e calcula métricas per-hab e per-km².
    O tipo de animal é selecionado via classificação 79[cat_id].
    """
    cat_id = REBANHO_CATS[nome_animal]
    classif = f"79[{cat_id}]"
    print(f"\n=== T3939 V105 C={classif}: rebanho {nome_animal} ===")
    for ano in anos:
        dados = sidra_fetch(3939, 105, ano, classificacao=classif)
        rows_hab = []
        rows_km2 = []
        for cod, cabecas in dados.items():
            pop = pop_map.get(cod)
            if pop and pop > 0:
                rows_hab.append((cod, f"rebanho_{nome_animal}_por_hab", ano, cabecas / pop))
            if not skip_km2:
                area = area_map.get(cod)
                if area and area > 0:
                    rows_km2.append((cod, f"rebanho_{nome_animal}_por_km2", ano, cabecas / area))
        print(f"  Ano {ano}: {len(rows_hab)} mun. (hab), {len(rows_km2)} mun. (km²)")
        upsert_metricas(rows_hab, conn)
        if rows_km2:
            upsert_metricas(rows_km2, conn)


# ─── T74 — Produção pecuária ──────────────────────────────────────────────────

def carregar_leite(conn, anos: list[int], pop_map: dict):
    """
    T74 V214 — Produção de leite (1000 litros).
    T74 V213 — Vacas ordenhadas.
    Derivado: producao_leite_por_vaca = (V214 * 1000) / V213 (litros/vaca).
    Também carrega producao_leite_per_capita = (V214 * 1000) / pop_2022 (litros/hab).
    """
    print("\n=== T74 V214/V213: Produção de leite ===")
    for ano in anos:
        leite  = sidra_fetch(74, 214, ano)  # mil litros
        vacas  = sidra_fetch(74, 213, ano)  # vacas ordenhadas

        rows_vaca = []
        rows_pc   = []
        for cod, mil_litros in leite.items():
            litros = mil_litros * 1000
            n_vacas = vacas.get(cod)
            if n_vacas and n_vacas > 0:
                rows_vaca.append((cod, "producao_leite_por_vaca", ano, litros / n_vacas))
            pop = pop_map.get(cod)
            if pop and pop > 0:
                rows_pc.append((cod, "producao_leite_per_capita", ano, litros / pop))
        print(f"  Ano {ano}: {len(rows_vaca)} mun. (por vaca), {len(rows_pc)} mun. (per capita)")
        upsert_metricas(rows_vaca, conn)
        upsert_metricas(rows_pc, conn)


def carregar_mel(conn, anos: list[int]):
    """
    T74 V216 — Quantidade de mel produzido (kg).
    T74 V2356 — Colmeias (colônias) em produção.
    Derivado: producao_mel_por_colmeia = V216 / V2356 (kg/colmeia).
    Carrega também producao_mel_kg (valor absoluto) para municípios relevantes.
    """
    print("\n=== T74 V216/V2356: Produção de mel ===")
    for ano in anos:
        mel     = sidra_fetch(74, 216, ano)   # kg de mel
        colmeias = sidra_fetch(74, 2356, ano) # colmeias em produção

        rows_colmeia = []
        rows_abs     = []
        for cod, kg_mel in mel.items():
            n_col = colmeias.get(cod)
            if n_col and n_col > 0:
                rows_colmeia.append((cod, "producao_mel_por_colmeia", ano, kg_mel / n_col))
            rows_abs.append((cod, "producao_mel_kg", ano, kg_mel))

        print(f"  Ano {ano}: {len(rows_colmeia)} mun. (por colmeia), {len(rows_abs)} mun. (abs)")
        upsert_metricas(rows_colmeia, conn)
        upsert_metricas(rows_abs, conn)


def carregar_ovos(conn, anos: list[int], pop_map: dict):
    """
    T74 V217 — Quantidade de ovos de galinha (mil dúzias).
    Carrega valor absoluto e per capita.
    """
    print("\n=== T74 V217: Produção de ovos ===")
    for ano in anos:
        ovos = sidra_fetch(74, 217, ano)  # mil dúzias

        rows_abs = []
        rows_pc  = []
        for cod, mil_duzias in ovos.items():
            rows_abs.append((cod, "producao_ovos_total", ano, mil_duzias))
            pop = pop_map.get(cod)
            if pop and pop > 0:
                # dúzias por habitante
                rows_pc.append((cod, "producao_ovos_per_capita", ano, (mil_duzias * 1000) / pop))

        print(f"  Ano {ano}: {len(rows_abs)} mun. (abs), {len(rows_pc)} mun. (per capita)")
        upsert_metricas(rows_abs, conn)
        upsert_metricas(rows_pc, conn)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Carrega PPM (Pesquisa Pecuária Municipal) em api.metricas_municipio"
    )
    parser.add_argument(
        "--anos", nargs="+", type=int,
        default=[2019, 2020, 2021, 2022, 2023],
        help="Anos a carregar (padrão: 2019-2023)"
    )
    parser.add_argument("--skip-bovino",     action="store_true", help="Pula rebanho bovino")
    parser.add_argument("--skip-equino",     action="store_true", help="Pula rebanho equino")
    parser.add_argument("--skip-suino",      action="store_true", help="Pula rebanho suíno")
    parser.add_argument("--skip-ovino",      action="store_true", help="Pula rebanho ovino")
    parser.add_argument("--skip-caprino",    action="store_true", help="Pula rebanho caprino")
    parser.add_argument("--skip-galinaceos", action="store_true", help="Pula galináceos")
    parser.add_argument("--skip-leite",      action="store_true", help="Pula produção de leite (V214)")
    parser.add_argument("--skip-mel",        action="store_true", help="Pula produção de mel (V216)")
    parser.add_argument("--skip-ovos",       action="store_true", help="Pula produção de ovos (V217)")
    args = parser.parse_args()

    print("Conectando ao banco...")
    conn = psycopg2.connect(**DB_PARAMS)

    try:
        pop_map, area_map = get_geo_maps(conn)
        print(f"  Geo maps: {len(pop_map)} municípios com pop, {len(area_map)} com área")

        print("\n──── PPM — Efetivo dos Rebanhos (T3939 V105) ────")
        if not args.skip_bovino:
            carregar_rebanho(conn, "bovino", args.anos, pop_map, area_map)
        if not args.skip_equino:
            carregar_rebanho(conn, "equino", args.anos, pop_map, area_map, skip_km2=True)
        if not args.skip_suino:
            carregar_rebanho(conn, "suino", args.anos, pop_map, area_map, skip_km2=True)
        if not args.skip_ovino:
            carregar_rebanho(conn, "ovino", args.anos, pop_map, area_map, skip_km2=True)
        if not args.skip_caprino:
            carregar_rebanho(conn, "caprino", args.anos, pop_map, area_map, skip_km2=True)
        if not args.skip_galinaceos:
            carregar_rebanho(conn, "galinaceos", args.anos, pop_map, area_map, skip_km2=True)

        print("\n──── PPM — Produção Pecuária (T74) ────")
        if not args.skip_leite:
            carregar_leite(conn, args.anos, pop_map)
        if not args.skip_mel:
            carregar_mel(conn, args.anos)
        if not args.skip_ovos:
            carregar_ovos(conn, args.anos, pop_map)

    finally:
        conn.close()

    print("\n=== Concluído ===")
    print("Verificar com:")
    print("  SELECT metrica, ano, COUNT(*), ROUND(AVG(valor)::numeric,3) AS media")
    print("  FROM api.metricas_municipio")
    print("  WHERE metrica LIKE 'rebanho_%' OR metrica LIKE 'producao_%'")
    print("  GROUP BY metrica, ano ORDER BY metrica, ano;")


if __name__ == "__main__":
    main()
