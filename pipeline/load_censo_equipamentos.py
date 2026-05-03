#!/usr/bin/env python3
"""
load_censo_equipamentos.py
Carrega indicadores de posse de bens duráveis e equipamentos domésticos do Censo 2022
para api.metricas_municipio.

Fonte: IBGE SIDRA — tabelas do Censo 2022 de existência de equipamentos nos domicílios.
Todos os indicadores são estáticos (ano=2022).

Indicadores:
    pct_geladeira           — % domicílios com geladeira/freezer (T9878 V1000381)
    pct_ar_condicionado     — % domicílios com ar-condicionado (T9887 V1000381)
    pct_freezer             — % domicílios com freezer independente (T9908 V1000381)
    pct_tv                  — % domicílios com televisão (T9909 V1000381)
    pct_automovel_domicilio — % domicílios com automóvel (T9911 V1000381)
    pct_motocicleta_domicilio — % domicílios com motocicleta (T9912 V1000381)
    pct_microondas          — % domicílios com microondas (T9913 V1000381)
    pct_computador          — % domicílios com computador sem internet (T9921 V1000381)

Uso:
    python load_censo_equipamentos.py
    python load_censo_equipamentos.py --skip-geladeira --skip-tv
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

# Todas as tabelas de bens duráveis do Censo 2022 usam o mesmo padrão:
# variável 1000381 (percentual), classificação C1977[73092]=Sim (tem o bem),
# C63[95826]=Total condição de ocupação, C125[2932]=Total tipo domicílio.
CLASSIF_PADRAO = "1977[73092]|63[95826]|125[2932]"


def sidra_fetch_pct(tabela: int, metrica: str) -> list[tuple]:
    """
    Busca percentual de domicílios com o equipamento para todos os municípios.
    Retorna lista de (cod_municipio, metrica, 2022, valor).
    """
    url = (
        f"{SIDRA_BASE}/{tabela}/periodos/2022/variaveis/1000381"
        f"?localidades=N6[all]&classificacao={CLASSIF_PADRAO}"
    )
    print(f"  GET T{tabela} V1000381 (2022) — {metrica} ...")
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
        print(f"  ERRO: T{tabela} falhou após 3 tentativas")
        return []

    rows = []
    for bloco in r.json():
        for res_item in bloco.get("resultados", []):
            for serie in res_item.get("series", []):
                try:
                    cod = int(serie["localidade"]["id"])
                    val_str = serie["serie"].get("2022", "-")
                    if val_str and val_str not in ("-", "...", "X", "", ".."):
                        rows.append((cod, metrica, 2022, float(val_str)))
                except (ValueError, KeyError):
                    pass
    print(f"    → {len(rows)} municípios")
    return rows


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


def carregar_geladeira(conn):
    """T9878 — % domicílios com geladeira ou freezer/refrigerador."""
    print("\n=== T9878: % domicílios com geladeira — Censo 2022 ===")
    rows = sidra_fetch_pct(9878, "pct_geladeira")
    upsert_metricas(rows, conn)


def carregar_ar_condicionado(conn):
    """T9887 — % domicílios com ar-condicionado."""
    print("\n=== T9887: % domicílios com ar-condicionado — Censo 2022 ===")
    rows = sidra_fetch_pct(9887, "pct_ar_condicionado")
    upsert_metricas(rows, conn)


def carregar_freezer(conn):
    """T9908 — % domicílios com freezer independente."""
    print("\n=== T9908: % domicílios com freezer — Censo 2022 ===")
    rows = sidra_fetch_pct(9908, "pct_freezer")
    upsert_metricas(rows, conn)


def carregar_tv(conn):
    """T9909 — % domicílios com televisão."""
    print("\n=== T9909: % domicílios com televisão — Censo 2022 ===")
    rows = sidra_fetch_pct(9909, "pct_tv")
    upsert_metricas(rows, conn)


def carregar_automovel(conn):
    """T9911 — % domicílios com automóvel."""
    print("\n=== T9911: % domicílios com automóvel — Censo 2022 ===")
    rows = sidra_fetch_pct(9911, "pct_automovel_domicilio")
    upsert_metricas(rows, conn)


def carregar_motocicleta(conn):
    """T9912 — % domicílios com motocicleta."""
    print("\n=== T9912: % domicílios com motocicleta — Censo 2022 ===")
    rows = sidra_fetch_pct(9912, "pct_motocicleta_domicilio")
    upsert_metricas(rows, conn)


def carregar_microondas(conn):
    """T9913 — % domicílios com microondas."""
    print("\n=== T9913: % domicílios com microondas — Censo 2022 ===")
    rows = sidra_fetch_pct(9913, "pct_microondas")
    upsert_metricas(rows, conn)


def carregar_computador(conn):
    """T9921 — % domicílios com computador (sem internet)."""
    print("\n=== T9921: % domicílios com computador — Censo 2022 ===")
    rows = sidra_fetch_pct(9921, "pct_computador")
    upsert_metricas(rows, conn)


def main():
    parser = argparse.ArgumentParser(
        description="Carrega equipamentos domésticos Censo 2022 em api.metricas_municipio"
    )
    parser.add_argument("--skip-geladeira",    action="store_true", help="Pula T9878 geladeira")
    parser.add_argument("--skip-ar",           action="store_true", help="Pula T9887 ar-condicionado")
    parser.add_argument("--skip-freezer",      action="store_true", help="Pula T9908 freezer")
    parser.add_argument("--skip-tv",           action="store_true", help="Pula T9909 televisão")
    parser.add_argument("--skip-automovel",    action="store_true", help="Pula T9911 automóvel")
    parser.add_argument("--skip-motocicleta",  action="store_true", help="Pula T9912 motocicleta")
    parser.add_argument("--skip-microondas",   action="store_true", help="Pula T9913 microondas")
    parser.add_argument("--skip-computador",   action="store_true", help="Pula T9921 computador")
    args = parser.parse_args()

    print("Conectando ao banco...")
    conn = psycopg2.connect(**DB_PARAMS)

    try:
        print("\n──── Censo 2022 — Equipamentos Domésticos ────")
        if not args.skip_geladeira:
            carregar_geladeira(conn)
        if not args.skip_ar:
            carregar_ar_condicionado(conn)
        if not args.skip_freezer:
            carregar_freezer(conn)
        if not args.skip_tv:
            carregar_tv(conn)
        if not args.skip_automovel:
            carregar_automovel(conn)
        if not args.skip_motocicleta:
            carregar_motocicleta(conn)
        if not args.skip_microondas:
            carregar_microondas(conn)
        if not args.skip_computador:
            carregar_computador(conn)
    finally:
        conn.close()

    print("\n=== Concluído ===")
    print("Verificar com:")
    print("  SELECT metrica, COUNT(*), ROUND(AVG(valor)::numeric,1) AS media")
    print("  FROM api.metricas_municipio")
    print("  WHERE metrica LIKE 'pct_%' AND ano=2022")
    print("  GROUP BY metrica ORDER BY metrica;")


if __name__ == "__main__":
    main()
