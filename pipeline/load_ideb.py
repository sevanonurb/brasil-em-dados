"""
load_ideb.py
Carrega dados do IDEB (Índice de Desenvolvimento da Educação Básica) — INEP.

IDEB observado dos anos iniciais e finais do ensino fundamental, por município, REDE PÚBLICA
(municipal + estadual), que é o IDEB do município como um todo.

Fonte: a divulgação de 2023, que traz a série inteira (VL_OBSERVADO_2005 … _2023) numa planilha
por etapa, com uma linha por município × rede (Estadual, Municipal, Pública, Federal):
    https://download.inep.gov.br/ideb/resultados/divulgacao_anos_{iniciais,finais}_municipios_2023.zip
O endereço antigo (educacao_basica/portal_ideb/planilhas_para_download/<ano>/…xlsx) dá 404 para
2017 e 2023 (medido em 27/10/2026), por isso o loader antigo só tinha 2019 e 2021. Ele também não
filtrava a rede: ficava com a última linha que tivesse valor para o município.

O zip fica em pipeline/.cache/ideb/.

Uso:
    python load_ideb.py                  # 2005–2023
    python load_ideb.py --anos 2019 2021 2023

Resultado: educacao.ideb_municipios (cod_municipio 7 dígitos IBGE, por ano)
"""

import argparse
import io
import os
import pathlib
import zipfile

import pandas as pd
import psycopg2
import requests
import urllib3
from psycopg2.extras import execute_values

# O servidor do INEP (download.inep.gov.br) usa certificado sem CA reconhecida no bundle padrão.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DB_PARAMS = dict(
    host=os.environ.get("POSTGRES_HOST", "localhost"),
    port=int(os.environ.get("POSTGRES_PORT", 5432)),
    database=os.environ.get("POSTGRES_DB", "brasil_dados"),
    user=os.environ.get("POSTGRES_USER", "brasil"),
    password=os.environ.get("POSTGRES_PASSWORD", ""),
)

URL = "https://download.inep.gov.br/ideb/resultados/divulgacao_anos_{etapa}_municipios_2023.zip"
CACHE = pathlib.Path(__file__).parent / ".cache" / "ideb"
ANOS_IDEB = list(range(2005, 2024, 2))


def planilha(etapa: str) -> pd.DataFrame:
    arq = CACHE / f"ideb_{etapa}_2023.zip"
    if not arq.exists():
        r = requests.get(URL.format(etapa=etapa), timeout=300, verify=False)
        r.raise_for_status()
        arq.write_bytes(r.content)
    z = zipfile.ZipFile(arq)
    nome = next(n for n in z.namelist() if n.endswith(".xlsx"))
    # linhas 0–8 são título e cabeçalho por extenso; a 9 tem os nomes de coluna
    return pd.read_excel(io.BytesIO(z.read(nome)), header=9, dtype=str)


def serie(etapa: str, anos: list[int]) -> dict[int, dict[int, float]]:
    """{ano: {cod_municipio: ideb}} da rede pública. '-' na planilha é sem IDEB."""
    df = planilha(etapa)
    df = df[df["REDE"] == "Pública"]
    cod = pd.to_numeric(df["CO_MUNICIPIO"], errors="coerce")
    out = {}
    for ano in anos:
        v = pd.to_numeric(df[f"VL_OBSERVADO_{ano}"], errors="coerce")
        ok = cod.notna() & v.notna()
        out[ano] = dict(zip(cod[ok].astype(int), v[ok].astype(float)))
    return out


def main():
    parser = argparse.ArgumentParser(description="Carrega IDEB/INEP multi-ano")
    parser.add_argument("--anos", nargs="+", type=int, default=ANOS_IDEB)
    args = parser.parse_args()
    anos = sorted(args.anos)
    CACHE.mkdir(parents=True, exist_ok=True)

    iniciais, finais = serie("iniciais", anos), serie("finais", anos)
    conn = psycopg2.connect(**DB_PARAMS)
    try:
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS educacao.ideb_municipios_antes_20261027 AS
                           SELECT * FROM educacao.ideb_municipios""")
        for ano in anos:
            municipios = set(iniciais[ano]) | set(finais[ano])
            rows = [(c, ano, iniciais[ano].get(c), finais[ano].get(c)) for c in sorted(municipios)]
            with conn.cursor() as cur:
                cur.execute("DELETE FROM educacao.ideb_municipios WHERE ano = %s", (ano,))
                execute_values(cur, """INSERT INTO educacao.ideb_municipios
                                       (cod_municipio, ano, ideb_anos_iniciais, ideb_anos_finais) VALUES %s""",
                               rows, page_size=2000)
            conn.commit()
            print(f"  {ano}: {len(rows):,} municípios (iniciais {len(iniciais[ano]):,}, finais {len(finais[ano]):,})",
                  flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
