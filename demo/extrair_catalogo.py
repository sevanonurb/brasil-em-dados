"""Extrai TODOS os pares indicador-ano (demo/anos.json, gerado por api.server.query_anos)
para demo/dados/<metrica>/<ano>.json = {"m": {cod_ibge_7: valor}, "u": {cod_uf: valor}}.
Usa as mesmas funções api.tiles_* do painel, com os filtros padrão. Retoma de onde parou."""
import json, os, sys, time, pathlib
import psycopg2, mapbox_vector_tile

TILES_Z4 = [(4, x, y) for x in (4, 5, 6) for y in (7, 8, 9)]
DB = dict(host="127.0.0.1", port=5432, dbname=os.environ["POSTGRES_DB"], user=os.environ["POSTGRES_USER"],
          password=os.environ["POSTGRES_PASSWORD"])

def valores(cur, funcao, camada, chave, params):
    res = {}
    for z, x, y in TILES_Z4:
        cur.execute(f"select api.{funcao}(%s,%s,%s,%s::json)", (z, x, y, json.dumps(params)))
        dados = cur.fetchone()[0]
        if not dados:
            continue
        for f in mapbox_vector_tile.decode(bytes(dados)).get(camada, {}).get("features", []):
            p = f["properties"]
            if p.get(chave) is not None and p.get("valor_metrica") is not None:
                res[str(p[chave])] = round(float(p["valor_metrica"]), 4)
    return res

def main():
    anos = json.load(open("demo/anos.json"))
    base = pathlib.Path("demo/dados")
    conn = psycopg2.connect(**DB); conn.autocommit = True; cur = conn.cursor()
    pares = [(m, a) for m, lista in anos.items() for a in lista]
    t0 = time.time()
    for i, (m, a) in enumerate(pares, 1):
        alvo = base / m / f"{a}.json"
        if alvo.exists():
            continue
        alvo.parent.mkdir(parents=True, exist_ok=True)
        p = {"metrica": m, "ano": a}
        try:
            d = {"m": valores(cur, "tiles_municipios", "municipios", "cod_ibge_7", p),
                 "u": valores(cur, "tiles_ufs", "ufs", "cod_uf", p)}
            alvo.write_text(json.dumps(d, separators=(",", ":")))
            print(f"{i}/{len(pares)} {m} {a}: {len(d['m'])} mun, {len(d['u'])} UF, {time.time()-t0:.0f}s", flush=True)
        except Exception as e:
            print(f"{i}/{len(pares)} {m} {a}: ERRO {e}", flush=True)
    print("FIM", flush=True)

if __name__ == "__main__":
    main()
