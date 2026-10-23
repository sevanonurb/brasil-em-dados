"""
load_populacao_raca_sexo_idade.py
Carrega a população do Censo 2022 por cor/raça × sexo × faixa etária × município
(SIDRA tabela 9606) em censo.populacao_rsi_municipio.

Por que existe: as taxas de mortalidade filtradas precisam do denominador do MESMO subgrupo.
As tabelas 9605 (raça) e 9514 (idade) não têm sexo nem o cruzamento raça × idade, e com elas
  - o filtro de sexo dividia óbitos de homens pela população total (taxa ~metade da real);
  - raça + idade estimava o denominador supondo independência (pr × pf / total).
Com a 9606 o denominador é exato para qualquer combinação: soma das células do subgrupo.

cor_raca 0 = total (categoria 95251 do SIDRA), 1..5 como no SIM. sexo 'M'/'F'.
faixa_etaria 0..17 no encoding do SIM (mesmo mapeamento de load_populacao_demografica.py).

Uso:  python3 pipeline/load_populacao_raca_sexo_idade.py      (POSTGRES_* no ambiente)
Fonte: https://sidra.ibge.gov.br/tabela/9606
"""
import os
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, os.path.dirname(__file__))
from load_populacao_demografica import (  # noqa: E402  mesmo mapeamento de faixas e mesmo cliente
    SIDRA_BASE, FAIXA_SINGLE, FAIXA1_CATS, FAIXA17_CATS, ALL_FAIXA_CATS, parse_pop, sidra_get,
)

RACA = {"95251": 0, "2776": 1, "2777": 2, "2778": 3, "2779": 4, "2780": 5}
SEXO = {"4": "M", "5": "F"}
UFS = [11, 12, 13, 14, 15, 16, 17, 21, 22, 23, 24, 25, 26, 27, 28, 29,
       31, 32, 33, 35, 41, 42, 43, 50, 51, 52, 53]


def faixa_de(cat):
    if cat in FAIXA_SINGLE:
        return FAIXA_SINGLE[cat]
    if cat in FAIXA1_CATS:
        return 1
    if cat in FAIXA17_CATS:
        return 17
    return None


def buscar(uf, raca_cat):
    """Uma UF × uma cor/raça: ≤ 645 municípios × 2 sexos × 25 categorias de idade (< limite do SIDRA)."""
    url = (f"{SIDRA_BASE}/9606/periodos/2022/variaveis/93?localidades=N6[N3[{uf}]]"
           f"&classificacao=86[{raca_cat}]|2[4,5]|287[{ALL_FAIXA_CATS}]")
    soma = defaultdict(int)
    for item in sidra_get(url):
        for res in item.get("resultados", []):
            cats = {c["id"]: next(iter(c["categoria"])) for c in res.get("classificacoes", [])}
            sexo, faixa = SEXO.get(cats.get("2")), faixa_de(cats.get("287"))
            if sexo is None or faixa is None:
                continue
            for serie in res.get("series", []):
                v = parse_pop(serie.get("serie", {}).get("2022", ""))
                if v is not None:
                    soma[(int(serie["localidade"]["id"]), RACA[raca_cat], sexo, faixa)] += v
    return soma


def main():
    tarefas = [(uf, r) for uf in UFS for r in RACA]
    linhas = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        for i, parte in enumerate(ex.map(lambda t: buscar(*t), tarefas), 1):
            linhas.update(parte)
            print(f"  {i}/{len(tarefas)}  {len(linhas):,} células", flush=True)

    conn = psycopg2.connect(host=os.environ.get("POSTGRES_HOST", "127.0.0.1"), dbname=os.environ["POSTGRES_DB"],
                            user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"])
    with conn, conn.cursor() as cur:
        cur.execute(open(os.path.join(os.path.dirname(__file__), "..", "database", "init",
                                      "06_populacao_raca_sexo_idade.sql")).read())
        cur.execute("TRUNCATE censo.populacao_rsi_municipio")
        execute_values(cur, "INSERT INTO censo.populacao_rsi_municipio VALUES %s",
                       [(*k, v) for k, v in linhas.items()], page_size=10000)
        # conferência: o total por raça (cor_raca 0) tem de bater com a soma das 5 raças e com a 9605
        cur.execute("""
            SELECT sum(populacao) FILTER (WHERE cor_raca = 0),
                   sum(populacao) FILTER (WHERE cor_raca > 0),
                   (SELECT sum(populacao) FROM censo.populacao_raca_municipio)
            FROM censo.populacao_rsi_municipio""")
        total, soma_racas, t9605 = cur.fetchone()
        print(f"  ✓ {len(linhas):,} linhas · total {total:,} · soma das raças {soma_racas:,} · 9605 {t9605:,}")


if __name__ == "__main__":
    main()
