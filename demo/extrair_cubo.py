"""Exporta o cubo de mortalidade para a demo estática calcular QUALQUER combinação de filtros
(causa × sexo × cor/raça × faixa etária) no navegador, com a mesma conta de api.tiles_*:

    taxa = round(óbitos do subgrupo × 100000 / população do mesmo subgrupo, 1)

Gerar as ~460 mil combinações prontas daria ~15 GB; as contagens elementares são ~5 M células.

Saída em demo/cubo/:
  municipios.json        ordem dos municípios (cod_ibge_7, cod_uf, populacao_2022) e das UFs
  populacao.bin.gz       Uint32 denso [município][cor_raca 0..5][sexo M,F][faixa 0..17]  (SIDRA 9606)
  obitos-<ano>.bin.gz    colunas: N (Uint32) | mun Uint16[N] | n Uint16[N] | causa Uint8[N] | sr Uint8[N] | faixa Uint8[N]
                         mun = índice em municipios.json, ou nMun + índice da UF para óbito sem município válido
                         causa = capítulo (A=0..Z=25) | suicídio X60–X84 << 5 | homicídio X85–Y09 << 6
                         sr = sexo (0 ignorado, 1 M, 2 F) | cor_raca (0 ignorada, 1..5) << 2
"""
import gzip, json, os, pathlib
import numpy as np
import psycopg2

DB = dict(host="127.0.0.1", port=5432, dbname=os.environ["POSTGRES_DB"], user=os.environ["POSTGRES_USER"],
          password=os.environ["POSTGRES_PASSWORD"])
SAIDA = pathlib.Path("demo/cubo")
ANOS = range(2015, 2024)


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    cur = psycopg2.connect(**DB).cursor()

    cur.execute("SELECT cod_ibge_7, cod_uf, COALESCE(populacao_2022, 0) FROM geo.municipios ORDER BY cod_ibge_7")
    muns = cur.fetchall()
    cur.execute("SELECT cod_uf, COALESCE(populacao_2022, 0) FROM geo.ufs ORDER BY cod_uf")
    ufs = cur.fetchall()
    idx_mun = {c // 10: i for i, (c, _, _) in enumerate(muns)}      # SIM usa 6 dígitos
    uf_mun = {c // 10: u for c, u, _ in muns}
    idx_uf = {u: i for i, (u, _) in enumerate(ufs)}
    n_mun = len(muns)
    (SAIDA / "municipios.json").write_text(json.dumps({
        "cod": [c for c, _, _ in muns], "uf": [u for _, u, _ in muns], "pop": [p for _, _, p in muns],
        "ufs": [u for u, _ in ufs], "pop_uf": [p for _, p in ufs],
    }, separators=(",", ":")))

    pop = np.zeros((n_mun, 6, 2, 18), dtype=np.uint32)
    pos7 = {c: i for i, (c, _, _) in enumerate(muns)}
    cur.execute("SELECT cod_municipio, cor_raca, sexo, faixa_etaria, populacao FROM censo.populacao_rsi_municipio")
    fora = 0
    for c, r, s, f, p in cur:
        if c in pos7:
            pop[pos7[c], r, 0 if s == "M" else 1, f] = p
        else:
            fora += p
    (SAIDA / "populacao.bin.gz").write_bytes(gzip.compress(pop.tobytes(), 9))
    print(f"população: {n_mun} municípios, {int(pop[:, 0].sum()):,} hab (total), fora da geo: {fora:,}")

    for ano in ANOS:
        cur.execute("""
            SELECT cod_municipio, cod_uf,
                   ascii(cid10_capitulo) - 65
                     | ((cid10_codigo >= 'X60' AND cid10_codigo < 'X85')::int << 5)
                     | ((cid10_codigo >= 'X85' AND cid10_codigo < 'Y1')::int << 6),
                   (CASE sexo WHEN '1' THEN 1 WHEN '2' THEN 2 ELSE 0 END)
                     | (CASE WHEN cor_raca BETWEEN 1 AND 5 THEN cor_raca ELSE 0 END << 2),
                   faixa_etaria, count(*)
            FROM saude.sim_mortalidade WHERE ano = %s
            GROUP BY 1, 2, 3, 4, 5 ORDER BY 1, 3, 4, 5""", (ano,))
        linhas = cur.fetchall()
        mun = np.empty(len(linhas), np.uint16); n = np.empty(len(linhas), np.uint16)
        causa = np.empty(len(linhas), np.uint8); sr = np.empty(len(linhas), np.uint8); fx = np.empty(len(linhas), np.uint8)
        sem_mun = uf_diverge = 0
        for i, (cm, cu, ca, s, f, k) in enumerate(linhas):
            if cm in idx_mun and uf_mun[cm] == cu:
                mun[i] = idx_mun[cm]
            else:
                assert cm not in idx_mun, f"óbito com município {cm} e UF {cu} divergente: o cubo não representa isso"
                mun[i] = n_mun + idx_uf[cu]; sem_mun += k
            assert k < 65536 and 0 <= ca < 128
            n[i], causa[i], sr[i], fx[i] = k, ca, s, f
        corpo = np.uint32(len(linhas)).tobytes() + mun.tobytes() + n.tobytes() + causa.tobytes() + sr.tobytes() + fx.tobytes()
        gz = gzip.compress(corpo, 9)
        (SAIDA / f"obitos-{ano}.bin.gz").write_bytes(gz)
        print(f"{ano}: {len(linhas):,} células, {int(n.sum()):,} óbitos ({sem_mun:,} sem município válido), "
              f"{len(corpo)/1e6:.1f} MB → {len(gz)/1e6:.1f} MB gz", flush=True)


if __name__ == "__main__":
    main()
