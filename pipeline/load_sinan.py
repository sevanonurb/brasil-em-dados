#!/usr/bin/env python3
"""
load_sinan.py
Carrega dados do SINAN (Sistema de Informação de Agravos de Notificação), direto do FTP do
DataSUS, para api.metricas_municipio.

Calcula incidência (casos por 100k hab.) por município DE RESIDÊNCIA e ano:
  incidencia_dengue        — DENG, casos prováveis: tudo menos descartado (CLASSI_FIN 5). O arquivo
                             FINAIS já vem sem descartados (2015: só 10/11/12 e 8 inconclusivo), então a
                             regra só pesa nos PRELIM
  incidencia_tuberculose   — TUBE, casos novos: TRATAMENTO 1/4/6 (novo, não sabe, pós-óbito),
                             sem mudança de diagnóstico (SITUA_ENCE 5)
  incidencia_hanseniase    — HANS, casos novos: MODOENTR 1
  incidencia_leishmaniose  — LEIV (visceral), casos confirmados: CLASSI_FIN 1

Por que essas regras (medido em 27/10/2026): o loader antigo contava TODA notificação pelo
município que notificou. Na leishmaniose 2023 isso eram 8.190 registros, dos quais 1.717
confirmados e 5.923 descartados — a incidência saía ~5× maior; e 35,6% dos registros têm
residência ≠ notificação (7,8% na tuberculose, 8,3% na hanseníase).

Arquivo: /dissemin/publicos/SINAN/DADOS/FINAIS/<DOENÇA>BR<aa>.dbc, ou PRELIM quando ainda não
fechou. O .dbc fica em pipeline/.cache/sinan/ e a contagem em sinan-<DOENÇA>-<ano>.json, então
rodar de novo não baixa nada.

Uso (precisa de pyreaddbc e dbfread — pipeline/.venv):
    .venv/bin/python load_sinan.py                       # 2015–2023, as quatro
    .venv/bin/python load_sinan.py --anos 2022 --doencas DENG
"""

import argparse
import collections
import json
import os
import pathlib
import time
from ftplib import FTP

import psycopg2
from dbfread import DBF
from psycopg2.extras import execute_values
from pyreaddbc import dbc2dbf

DB_PARAMS = dict(
    host=os.environ.get("POSTGRES_HOST", "localhost"),
    port=int(os.environ.get("POSTGRES_PORT", 5432)),
    database=os.environ.get("POSTGRES_DB", "brasil_dados"),
    user=os.environ.get("POSTGRES_USER", "brasil"),
    password=os.environ.get("POSTGRES_PASSWORD", ""),
)

DOENCAS = {
    "DENG": ("incidencia_dengue",       lambda r: r["CLASSI_FIN"] != "5"),
    "TUBE": ("incidencia_tuberculose",  lambda r: r["TRATAMENTO"] in ("1", "4", "6") and r["SITUA_ENCE"].strip() != "5"),
    "HANS": ("incidencia_hanseniase",   lambda r: r["MODOENTR"] == "1"),
    "LEIV": ("incidencia_leishmaniose", lambda r: r["CLASSI_FIN"] == "1"),
}
CAMPOS = {"DENG": ["CLASSI_FIN"], "TUBE": ["TRATAMENTO", "SITUA_ENCE"], "HANS": ["MODOENTR"], "LEIV": ["CLASSI_FIN"]}
FTP_HOST, FTP_DIR = "ftp.datasus.gov.br", "/dissemin/publicos/SINAN/DADOS"
CACHE = pathlib.Path(__file__).parent / ".cache" / "sinan"


def baixar(doenca: str, ano: int) -> tuple[pathlib.Path, str]:
    nome = f"{doenca}BR{ano % 100:02d}.dbc"
    destino = CACHE / nome
    for pasta in ("FINAIS", "PRELIM"):
        if destino.exists() and (CACHE / f"{nome}.{pasta}").exists():
            return destino, pasta
    for tentativa in range(5):
        try:
            ftp = FTP(FTP_HOST, timeout=300); ftp.login()
            for pasta in ("FINAIS", "PRELIM"):
                if nome in [p.rsplit("/", 1)[-1] for p in ftp.nlst(f"{FTP_DIR}/{pasta}")]:
                    parcial = destino.with_suffix(".parcial")
                    with open(parcial, "wb") as o:
                        ftp.retrbinary(f"RETR {FTP_DIR}/{pasta}/{nome}", o.write)
                    parcial.rename(destino)
                    (CACHE / f"{nome}.{pasta}").touch()
                    return destino, pasta
            raise FileNotFoundError(nome)
        except FileNotFoundError:
            raise
        except Exception as e:
            print(f"    FTP {nome}: {type(e).__name__}: {e} — tentativa {tentativa + 1}", flush=True)
            time.sleep(30 * (tentativa + 1))
    raise RuntimeError(f"FTP {nome}: tentativas esgotadas")


def contar(doenca: str, ano: int) -> dict:
    """{"casos": {cod6_residência: n}, "notificacoes", "casos_total", "sem_residencia", "fonte"}"""
    arq = CACHE / f"sinan-{doenca}-{ano}.json"
    if arq.exists():
        return json.loads(arq.read_text())
    dbc, pasta = baixar(doenca, ano)
    dbf = dbc.with_suffix(".dbf")
    dbc2dbf(str(dbc), str(dbf))
    regra = DOENCAS[doenca][1]
    casos, n, sem = collections.Counter(), 0, 0
    try:
        for r in DBF(str(dbf), encoding="latin-1", load=False):
            n += 1
            if not regra({k: (r.get(k) or "") for k in CAMPOS[doenca]}):
                continue
            mun = (r.get("ID_MN_RESI") or "").strip()
            if mun.isdigit():
                casos[int(mun[:6])] += 1
            else:
                sem += 1
    finally:
        dbf.unlink(missing_ok=True)
    res = {"casos": {str(k): v for k, v in casos.items()}, "notificacoes": n,
           "casos_total": sum(casos.values()) + sem, "sem_residencia": sem, "fonte": pasta}
    arq.write_text(json.dumps(res))
    return res


def main():
    ap = argparse.ArgumentParser(description="Carrega SINAN (agravos de notificação) em api.metricas_municipio")
    ap.add_argument("--anos", nargs="+", type=int, default=list(range(2015, 2024)))
    ap.add_argument("--doencas", nargs="+", default=list(DOENCAS), choices=list(DOENCAS))
    args = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)

    conn = psycopg2.connect(**DB_PARAMS)
    with conn.cursor() as cur:
        cur.execute("SELECT cod_ibge_7, populacao_2022 FROM geo.municipios WHERE populacao_2022 > 0")
        pop = {c // 10: (c, p) for c, p in cur.fetchall()}
        cur.execute("""CREATE TABLE IF NOT EXISTS api.metricas_sinan_antes_20261027 AS
                       SELECT * FROM api.metricas_municipio WHERE metrica LIKE 'incidencia\\_%'""")
        conn.commit()

    for doenca in args.doencas:
        metrica = DOENCAS[doenca][0]
        for ano in args.anos:
            t = time.time()
            try:
                c = contar(doenca, ano)
            except FileNotFoundError as e:
                print(f"  {doenca} {ano}: não publicado ({e})", flush=True)
                continue
            casos = {int(k): v for k, v in c["casos"].items()}
            fora = sum(v for k, v in casos.items() if k not in pop)
            # todo município com população entra: sem caso no ano é incidência ZERO, não "sem dado"
            linhas = [(cod7, metrica, ano, casos.get(cod6, 0) / p * 100_000) for cod6, (cod7, p) in pop.items()]
            with conn.cursor() as cur:
                cur.execute("DELETE FROM api.metricas_municipio WHERE metrica = %s AND ano = %s", (metrica, ano))
                execute_values(cur, "INSERT INTO api.metricas_municipio (cod_municipio, metrica, ano, valor) VALUES %s",
                               linhas, page_size=2000)
                conn.commit()
            print(f"  {doenca} {ano} [{c['fonte']}]: {c['notificacoes']:,} notificações → {c['casos_total']:,} casos "
                  f"(sem residência {c['sem_residencia']:,}, residência fora da malha {fora:,}); "
                  f"{len(linhas)} municípios ({time.time() - t:.0f}s)", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
