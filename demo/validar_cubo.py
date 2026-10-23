"""Oráculo do cubo: a taxa que a demo calcula no navegador (window.__demoTaxas) tem de ser IGUAL
à que o banco devolve por api.tiles_municipios / api.tiles_ufs, para combinações sorteadas de
causa × sexo × cor/raça × faixa etária × ano, mais casos-limite escritos à mão.

    python3 demo/servir.py 8392 &          (servidor com Range)
    python3 demo/validar_cubo.py [URL] [N]  (POSTGRES_* no ambiente)
"""
import json, os, random, sys
import psycopg2
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from extrair_catalogo import valores, DB  # noqa: E402  mesmas funções e tiles da extração

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8392/brasil-em-dados/"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 24
CAUSAS = [None, "suicidio"] + list("ICJEKNGBAVWXYOPFQ")

LIMITES = [
    {"metrica": "taxa_mortalidade", "ano": 2023, "cid10_capitulo": "I"},
    {"metrica": "taxa_mortalidade", "ano": 2021, "sexo": "M"},
    {"metrica": "taxa_mortalidade", "ano": 2015, "cor_raca": 5, "faixa_etaria_min": 0, "faixa_etaria_max": 0},
    {"metrica": "taxa_mortalidade", "ano": 2020, "cid10_capitulo": "suicidio", "sexo": "F", "faixa_etaria_min": 17, "faixa_etaria_max": 17},
    {"metrica": "taxa_homicidio", "ano": 2023, "sexo": "M", "cor_raca": 2, "faixa_etaria_min": 4, "faixa_etaria_max": 6},
    {"metrica": "taxa_homicidio", "ano": 2019, "cor_raca": 3},
]


def sorteio(rng):
    p = {"metrica": rng.choice(["taxa_mortalidade", "taxa_mortalidade", "taxa_homicidio"]), "ano": rng.randint(2015, 2023)}
    if p["metrica"] == "taxa_mortalidade" and (c := rng.choice(CAUSAS)):
        p["cid10_capitulo"] = c
    if (s := rng.choice([None, "M", "F"])):
        p["sexo"] = s
    if (r := rng.choice([None, None, 1, 2, 3, 4, 5])):
        p["cor_raca"] = r
    if rng.random() < 0.5:
        a, b = sorted(rng.sample(range(18), 2))
        p["faixa_etaria_min"], p["faixa_etaria_max"] = a, b
    return p


def comparar(banco, demo):
    chaves = set(banco) | set(demo)
    dif = [(k, banco.get(k), demo.get(k)) for k in chaves
           if banco.get(k) is None or demo.get(k) is None or abs(banco[k] - demo[k]) > 1e-9]
    return len(chaves), dif


def main():
    rng = random.Random(7)
    casos = LIMITES + [sorteio(rng) for _ in range(N)]
    cur = psycopg2.connect(**DB).cursor()
    total_dif = 0
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome")
        pg = b.new_page(); pg.goto(URL); pg.wait_for_function("window.__demoTaxas", timeout=30000)
        for i, p in enumerate(casos, 1):
            demo = pg.evaluate("q => window.__demoTaxas(q)", {k: str(v) for k, v in p.items()})
            banco = {"m": valores(cur, "tiles_municipios", "municipios", "cod_ibge_7", p),
                     "u": valores(cur, "tiles_ufs", "ufs", "cod_uf", p)}
            linha = []
            for k in ("m", "u"):
                n, dif = comparar(banco[k], {kk: float(v) for kk, v in demo[k].items()})
                total_dif += len(dif)
                linha.append(f"{'mun' if k == 'm' else 'UF'} {n - len(dif)}/{n}" + (f" DIF {dif[:3]}" if dif else ""))
            print(f"{i:2d} {'OK ' if all('DIF' not in x for x in linha) else 'ERR'} {json.dumps(p, ensure_ascii=False)}  →  {' · '.join(linha)}", flush=True)
        b.close()
    print(f"\nRESULTADO: {len(casos)} combinações, {total_dif} valores divergentes")
    sys.exit(1 if total_dif else 0)


if __name__ == "__main__":
    main()
