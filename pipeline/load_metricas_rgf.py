#!/usr/bin/env python3
"""
load_metricas_rgf.py
Carrega indicadores fiscais do Siconfi RGF (Relatório de Gestão Fiscal) para
api.metricas_municipio.

Indicadores (% da RCL ajustada, Poder Executivo, fim do exercício):
  divida_rcl           — Dívida Consolidada Líquida / RCL   (limite LRF: 120%)
  despesa_pessoal_rcl  — Despesa Total com Pessoal / RCL    (limite LRF: 54%)

Os dois vêm do RGF-Anexo 06 (Demonstrativo Simplificado), que todo município publica no último
período do ano — no RGF completo (quadrimestral, período 3) e no RGF Simplificado (semestral,
período 2), que é o que municípios < 50 mil hab. podem entregar (LRF art. 63). Medido em
25/10/2026: o loader antigo só pedia o RGF quadrimestral e perdia 2.269 municípios em 2022 —
20 de 20 sorteados entre eles tinham RGF Simplificado semestral; e o Anexo 06 repete exatamente
os Anexos 01 (pessoal) e 02 (DCL, "Até o 3º Quadrimestre") em 3 capitais × 2015 e 2023.

Do ano mais recente ao mais antigo; cada município baixado vai na hora para
pipeline/.cache/rgf-<ano>.jsonl, então cair no meio não perde nada. Um ano só é gravado quando
todos os municípios voltaram sem erro de rede — e então substitui as duas métricas daquele ano,
descartando valor fora de PLAUSIVEL.

Uso:
    python3 pipeline/load_metricas_rgf.py                  # 2023 → 2015
    python3 pipeline/load_metricas_rgf.py 2022 2021
"""

import json
import pathlib
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from psycopg2.extras import execute_values

from load_economic_data import RITMO, _esperar_rede, _sem_rede, get_conn

RGF_BASE = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rgf"
CACHE = pathlib.Path(__file__).parent / ".cache"
ANOS = [int(a) for a in sys.argv[1:]] or list(range(2023, 2014, -1))

# (tipo, periodicidade, último período do ano)
VARIANTES = [("RGF", "Q", 3), ("RGF Simplificado", "S", 2), ("RGF", "S", 2), ("RGF Simplificado", "Q", 3)]
# Faixa plausível, % da RCL. Fora dela é erro de preenchimento na fonte, e não vai ao banco (o cache
# guarda o bruto). Medido em 2023: pessoal 5.519 valores, p5 36,6 / p95 60,9, e casos de 0,43 e 5.031;
# dívida 5.261 valores com 11 acima de |300| — um único -17.970.525% levava o Mato Grosso do Sul a
# -71.250% na média estadual ponderada.
PLAUSIVEL = {"p": (5.0, 150.0), "d": (-500.0, 500.0)}
CONTAS = {"DespesaTotalComPessoalDemonstrativo": "pessoal", "DividaConsolidadaLiquidaDemonstrativo": "divida"}


def _anexo06(cod: int, ano: int, tipo: str, per: str, n: int, tentativas: int = 8) -> list:
    q = urllib.parse.urlencode({"an_exercicio": ano, "in_periodicidade": per, "nr_periodo": n,
                                "co_tipo_demonstrativo": tipo, "no_anexo": "RGF-Anexo 06",
                                "co_esfera": "M", "co_poder": "E", "id_ente": cod})
    for t in range(tentativas):
        RITMO.esperar()
        try:
            req = urllib.request.Request(f"{RGF_BASE}?{q}", headers={"User-Agent": "brasil-em-dados/1.0"})
            return json.loads(urllib.request.urlopen(req, timeout=90).read()).get("items", [])
        except urllib.error.HTTPError as e:
            if t == tentativas - 1:
                raise
            if e.code == 429:
                RITMO.punir(30 * (t + 1))
            else:
                time.sleep(2 ** t)
        except urllib.error.URLError as e:
            if _sem_rede(e):
                _esperar_rede()
                continue
            if t == tentativas - 1:
                raise
            time.sleep(2 ** t)
        except Exception:
            if t == tentativas - 1:
                raise
            time.sleep(2 ** t)
    raise RuntimeError("tentativas esgotadas")


def buscar(cod: int, ano: int, primeiro: int = 0) -> dict:
    """{"c", "d" (divida %), "p" (pessoal %), "v" (índice da variante), "erro"}"""
    ordem = [primeiro] + [i for i in range(len(VARIANTES)) if i != primeiro]
    try:
        for i in ordem:
            itens = _anexo06(cod, ano, *VARIANTES[i])
            if not itens:
                continue
            v = {}
            for it in itens:
                chave = next((k for p, k in CONTAS.items() if it.get("cod_conta", "").startswith(p)), None)
                if chave and "RCL" in it.get("coluna", "").upper() and it.get("valor") is not None:
                    v.setdefault(chave, float(it["valor"]))
            return {"c": cod, "d": v.get("divida"), "p": v.get("pessoal"), "v": i, "erro": None}
        return {"c": cod, "d": None, "p": None, "v": None, "erro": None}      # não entregou: lacuna da fonte
    except Exception as e:
        return {"c": cod, "d": None, "p": None, "v": None, "erro": f"{type(e).__name__}: {e}"[:120]}


def ler(arq):
    feitos = {}
    if arq.exists():
        for linha in arq.read_text().splitlines():
            d = json.loads(linha)
            feitos[d["c"]] = d                 # a última linha de cada município vale
    return feitos


def main():
    CACHE.mkdir(exist_ok=True)
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT cod_ibge_7 FROM geo.municipios ORDER BY 1")
        cods = [r[0] for r in cur.fetchall()]
        cur.execute("""CREATE TABLE IF NOT EXISTS api.metricas_rgf_antes_20261025 AS
                       SELECT * FROM api.metricas_municipio WHERE metrica IN ('divida_rcl', 'despesa_pessoal_rcl')""")
        conn.commit()
    palpite = {}                               # a variante que o município usou no ano seguinte
    for ano in ANOS:
        arq = CACHE / f"rgf-{ano}.jsonl"
        feitos = ler(arq)
        faltam = [c for c in cods if c not in feitos or feitos[c].get("erro")]
        if faltam:
            print(f"  RGF {ano}: {len(faltam)} municípios...", flush=True)
            t0, trava, n_err = time.time(), threading.Lock(), 0
            with arq.open("a") as saida, ThreadPoolExecutor(max_workers=4) as pool:
                futs = [pool.submit(buscar, c, ano, palpite.get(c, 0)) for c in faltam]
                for n, fut in enumerate(as_completed(futs), 1):
                    d = fut.result()
                    n_err += bool(d["erro"])
                    with trava:
                        saida.write(json.dumps(d) + "\n"); saida.flush()
                    if n % 500 == 0:
                        print(f"    {n}/{len(faltam)} ({time.time()-t0:.0f}s) erros={n_err}", flush=True)
            feitos = ler(arq)
        palpite = {c: d["v"] for c, d in feitos.items() if d.get("v") is not None}
        erros = [c for c in cods if feitos[c].get("erro")]
        if erros:
            print(f"  {ano}: {len(erros)} com erro de rede — NÃO gravado; rode de novo para retomar", flush=True)
            continue
        ok = lambda c, k: feitos[c][k] is not None and PLAUSIVEL[k][0] <= feitos[c][k] <= PLAUSIVEL[k][1]
        linhas = [(c, m, ano, feitos[c][k]) for c in cods for m, k in (("divida_rcl", "d"), ("despesa_pessoal_rcl", "p"))
                  if ok(c, k)]
        with conn.cursor() as cur:
            cur.execute("DELETE FROM api.metricas_municipio WHERE ano = %s AND metrica IN ('divida_rcl', 'despesa_pessoal_rcl')", (ano,))
            execute_values(cur, "INSERT INTO api.metricas_municipio (cod_municipio, metrica, ano, valor) VALUES %s", linhas, page_size=2000)
            conn.commit()
        simp = sum(1 for c in cods if feitos[c]["v"] in (1, 3))
        cnt = lambda k: sum(1 for c in cods if ok(c, k))
        fora = lambda k: sum(1 for c in cods if feitos[c][k] is not None and not ok(c, k))
        print(f"  {ano}: GRAVADO — dívida {cnt('d')}, pessoal {cnt('p')} de {len(cods)} ({simp} pelo RGF Simplificado; "
              f"fora da faixa plausível, descartados: dívida {fora('d')}, pessoal {fora('p')})", flush=True)


if __name__ == "__main__":
    main()
