#!/usr/bin/env python3
"""
load_metricas_rgf.py
Carrega indicadores fiscais do Siconfi RGF (Relatório de Gestão Fiscal) para
api.metricas_municipio.

Indicadores:
  divida_rcl           — Dívida Consolidada Líquida / RCL (%)  [RGF Anexo 01]
  despesa_pessoal_rcl  — Despesa Total com Pessoal / RCL (%)   [RGF Anexo 02]

Referência legal:
  Lei de Responsabilidade Fiscal (LC 101/2000)
  Limite dívida: 120% da RCL
  Limite pessoal: 54% da RCL

Uso:
    python load_metricas_rgf.py                          # anos 2019–2022
    python load_metricas_rgf.py --anos 2020 2021 2022
    python load_metricas_rgf.py --workers 20             # paralelismo (padrão 30)
"""

import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

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

RGF_BASE = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rgf"

# Maior periodicidade da RGF: Q (quadrimestral), período 3 = dez acumulado 12 meses
# Cobertura: jan-dez do exercício
PERIODICIDADE = "Q"
PERIODO = 3


def fetch_rgf_municipio(cod_ibge: int, ano: int) -> tuple[int, float | None, float | None]:
    """
    Busca RGF do município e extrai:
      - Dívida Consolidada Líquida / RCL% (Anexo 02, cod_conta=PercentualDaDCLSobreARCL)
      - Despesa Total com Pessoal / RCL% (Anexo 01, cod_conta=DespesaComPessoalTotal,
        coluna="% sobre a RCL Ajustada")

    Parâmetros obrigatórios da API Siconfi RGF:
      co_esfera=M (Municipal), co_poder=E (Executivo)

    Retorna (cod_ibge, divida_rcl_pct, pessoal_rcl_pct).
    """
    divida_pct = None
    pessoal_pct = None
    base_params = {
        "an_exercicio": ano,
        "in_periodicidade": PERIODICIDADE,
        "nr_periodo": PERIODO,
        "co_tipo_demonstrativo": "RGF",
        "id_ente": cod_ibge,
        "co_esfera": "M",
        "co_poder": "E",
    }
    headers = {"User-Agent": "brasil-em-dados/1.0"}

    # ── Anexo 01 — Despesa de Pessoal ────────────────────────────────────────
    try:
        r = requests.get(RGF_BASE,
                         params={**base_params, "no_anexo": "RGF-Anexo 01", "limit": 200},
                         timeout=20, headers=headers)
        if r.status_code == 200:
            for item in r.json().get("items", []):
                if (item.get("cod_conta") == "DespesaComPessoalTotal"
                        and "% sobre a RCL" in item.get("coluna", "")):
                    try:
                        pessoal_pct = float(item["valor"])
                        break
                    except (TypeError, ValueError):
                        pass
    except Exception:
        pass

    # ── Anexo 02 — Dívida Consolidada ────────────────────────────────────────
    try:
        r = requests.get(RGF_BASE,
                         params={**base_params, "no_anexo": "RGF-Anexo 02", "limit": 200},
                         timeout=20, headers=headers)
        if r.status_code == 200:
            for item in r.json().get("items", []):
                if item.get("cod_conta") == "PercentualDaDCLSobreARCL":
                    # Prefer "3º Quadrimestre" (full year); fallback to any quadrimestre
                    col = item.get("coluna", "")
                    if "3º" in col or "3o" in col.lower():
                        try:
                            divida_pct = float(item["valor"])
                            break
                        except (TypeError, ValueError):
                            pass
            # Fallback: any % da DCL entry
            if divida_pct is None:
                for item in r.json().get("items", []):
                    if item.get("cod_conta") == "PercentualDaDCLSobreARCL":
                        try:
                            divida_pct = float(item["valor"])
                            break
                        except (TypeError, ValueError):
                            pass
    except Exception:
        pass

    return cod_ibge, divida_pct, pessoal_pct


def probe_rgf_structure(cod_ibge: int, ano: int):
    """Imprime estrutura do RGF para um município (diagnóstico)."""
    for anexo in ["RGF-Anexo 01", "RGF-Anexo 02"]:
        params = {
            "an_exercicio": ano, "in_periodicidade": PERIODICIDADE,
            "nr_periodo": PERIODO, "co_tipo_demonstrativo": "RGF",
            "no_anexo": anexo, "id_ente": cod_ibge,
            "co_esfera": "M", "co_poder": "E", "limit": 20,
        }
        print(f"\n  === {anexo} — município {cod_ibge} ano {ano} ===")
        r = requests.get(RGF_BASE, params=params, timeout=30,
                         headers={"User-Agent": "brasil-em-dados/1.0"})
        if r.status_code != 200:
            print(f"  HTTP {r.status_code}")
            continue
        items = r.json().get("items", [])[:10]
        for item in items:
            print(f"  cod_conta={item.get('cod_conta','')[:60]:<62}"
                  f"  coluna={item.get('coluna','')[:40]:<42}"
                  f"  valor={item.get('valor')}")


def main():
    parser = argparse.ArgumentParser(description="Carrega RGF Siconfi para api.metricas_municipio")
    parser.add_argument("--anos", nargs="+", type=int,
                        default=[2019, 2020, 2021, 2022],
                        help="Anos do exercício (padrão: 2019–2022)")
    parser.add_argument("--workers", type=int, default=30,
                        help="Threads paralelas (padrão: 30)")
    parser.add_argument("--probe", type=int, default=None,
                        metavar="COD_IBGE",
                        help="Imprime estrutura do RGF para um município específico e sai")
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_PARAMS)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT cod_ibge_7 FROM geo.municipios ORDER BY cod_ibge_7")
            municipios = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    # Modo probe: diagnóstico de estrutura do RGF
    if args.probe:
        probe_rgf_structure(args.probe, args.anos[-1])
        return

    print(f"Municípios: {len(municipios)}")

    for ano in args.anos:
        print(f"\n=== RGF {ano} — {len(municipios)} municípios ({args.workers} workers) ===")
        t0 = time.time()

        divida_map: dict[int, float] = {}
        pessoal_map: dict[int, float] = {}
        done = 0

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(fetch_rgf_municipio, cod, ano): cod for cod in municipios}
            for future in as_completed(futures):
                cod_ibge, divida, pessoal = future.result()
                if divida  is not None: divida_map[cod_ibge]  = divida
                if pessoal is not None: pessoal_map[cod_ibge] = pessoal
                done += 1
                if done % 500 == 0:
                    elapsed = time.time() - t0
                    print(f"  {done}/{len(municipios)} — {elapsed:.0f}s"
                          f"  divida={len(divida_map)} pessoal={len(pessoal_map)}")

        elapsed = time.time() - t0
        print(f"  Concluído {ano} em {elapsed:.0f}s"
              f"  divida={len(divida_map)} pessoal={len(pessoal_map)}")

        # Persistir no banco
        rows = []
        for cod, v in divida_map.items():
            rows.append((cod, "divida_rcl", ano, v))
        for cod, v in pessoal_map.items():
            rows.append((cod, "despesa_pessoal_rcl", ano, v))

        if rows:
            db = psycopg2.connect(**DB_PARAMS)
            try:
                with db.cursor() as cur:
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
                db.commit()
                print(f"  Upserted {len(rows):,} registros")
            finally:
                db.close()

    print("\n=== Concluído ===")
    print("Verificar com:")
    print("  SELECT metrica, ano, COUNT(*), ROUND(AVG(valor)::numeric,2) AS media")
    print("  FROM api.metricas_municipio")
    print("  WHERE metrica IN ('divida_rcl','despesa_pessoal_rcl')")
    print("  GROUP BY metrica, ano ORDER BY metrica, ano;")


if __name__ == "__main__":
    main()
