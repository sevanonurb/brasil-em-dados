"""Recarrega receita, despesa em saúde e despesa em educação (Siconfi RREO) com o fetch corrigido de
load_economic_data.py (RREO + RREO Simplificado; saúde e educação por função; ritmo de 1,8 req/s).
Só toca nessas três colunas. Do ano mais recente ao mais antigo; cada município baixado vai na hora
para pipeline/.cache/siconfi-<ano>.jsonl, então cair no meio não perde nada. Um ano só é gravado no
banco quando todos os 5.570 municípios voltaram sem erro de rede.

    python3 pipeline/recarregar_siconfi.py [anos...]      (POSTGRES_* no ambiente; ~16 h para 2015–2023)
"""
import json, pathlib, sys, threading
from psycopg2.extras import execute_values
from load_economic_data import baixar_receita_siconfi, get_conn

CACHE = pathlib.Path(__file__).parent / ".cache"
ANOS = [int(a) for a in sys.argv[1:]] or list(range(2023, 2014, -1))


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
    for ano in ANOS:
        arq = CACHE / f"siconfi-{ano}.jsonl"
        feitos = ler(arq)
        faltam = [c for c in cods if c not in feitos or feitos[c].get("erro")]
        if faltam:
            with conn.cursor() as cur:
                cur.execute("SELECT cod_municipio FROM economia.siconfi_municipios_antes_20261023 "
                            "WHERE ano=%s AND receita_total IS NOT NULL", (ano,))
                completos = {r[0] for r in cur.fetchall()}
            trava = threading.Lock()
            with arq.open("a") as saida:
                def gravar(c, r, s, e, erro):
                    with trava:
                        saida.write(json.dumps({"c": c, "r": r, "s": s, "e": e, "erro": erro}) + "\n"); saida.flush()
                baixar_receita_siconfi(faltam, ano, tipo_primeiro={c: "RREO" if c in completos else "RREO Simplificado" for c in faltam},
                                       ao_receber=gravar)
            feitos = ler(arq)
        erros = [c for c in cods if feitos[c].get("erro")]
        if erros:
            print(f"  {ano}: {len(erros)} com erro de rede — NÃO gravado; rode de novo para retomar", flush=True)
            continue
        with conn.cursor() as cur:
            execute_values(cur, """
                UPDATE economia.siconfi_municipios t SET receita_total = v.r, despesa_saude = v.s, despesa_educacao = v.e
                FROM (VALUES %s) AS v(c, r, s, e, a) WHERE t.cod_municipio = v.c AND t.ano = v.a""",
                [(c, feitos[c]["r"], feitos[c]["s"], feitos[c]["e"], ano) for c in cods],
                template="(%s, %s::float8, %s::float8, %s::float8, %s::smallint)", page_size=1000)
            conn.commit()
        n = lambda k: sum(1 for c in cods if feitos[c][k] is not None)
        print(f"  {ano}: GRAVADO — receita {n('r')}, saúde {n('s')}, educação {n('e')} de {len(cods)}", flush=True)


if __name__ == "__main__":
    main()
