"""
load_sinasc.py
Carrega dados de nascidos vivos do SINASC/DataSUS via PySUS.

Uso:
    python load_sinasc.py                   # carrega 2015–2023, todos os estados
    python load_sinasc.py --anos 2020 2021  # apenas esses anos
    python load_sinasc.py --ufs SP RJ       # apenas esses estados

Resultado: saude.sinasc_municipios (cod_municipio 6 dígitos DataSUS, por ano)
"""

import argparse
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

import psycopg2
import pandas as pd
from psycopg2.extras import execute_values

try:
    from pysus.online_data.sinasc import SINASC
except ImportError:
    try:
        from pysus.online_data import SINASC
    except ImportError:
        raise ImportError("PySUS não encontrado. Instale: pip install pysus")

UFS_BRASIL = [
    "AC","AL","AP","AM","BA","CE","DF","ES","GO",
    "MA","MT","MS","MG","PA","PB","PR","PE","PI",
    "RJ","RN","RS","RO","RR","SC","SP","SE","TO",
]

UF_COD = {
    "AC": 12, "AL": 27, "AP": 16, "AM": 13, "BA": 29, "CE": 23,
    "DF": 53, "ES": 32, "GO": 52, "MA": 21, "MT": 51, "MS": 50,
    "MG": 31, "PA": 15, "PB": 25, "PR": 41, "PE": 26, "PI": 22,
    "RJ": 33, "RN": 24, "RS": 43, "RO": 11, "RR": 14, "SC": 42,
    "SP": 35, "SE": 28, "TO": 17,
}

ANO_INICIO = 2015
ANO_FIM    = 2023

DB_PARAMS = dict(
    host=os.environ.get("POSTGRES_HOST", "localhost"),
    port=int(os.environ.get("POSTGRES_PORT", 5432)),
    database=os.environ.get("POSTGRES_DB", "brasil_dados"),
    user=os.environ.get("POSTGRES_USER", "brasil"),
    password=os.environ.get("POSTGRES_PASSWORD", ""),
)


def get_conn():
    return psycopg2.connect(**DB_PARAMS)


def processar_uf_ano(uf: str, ano: int) -> dict:
    """
    Baixa SINASC para UF/ano, retorna dicionário
    cod_municipio (6-dig) → nascidos_vivos.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            parquet_set = SINASC.download("DN", uf, ano, data_dir=tmpdir)
            df = parquet_set.to_dataframe()
        except Exception as e:
            print(f"  ERRO download SINASC {uf}/{ano}: {e}")
            return {}

    if df.empty:
        return {}

    # CODMUNRES em SINASC é 6 dígitos DataSUS (diferente de SIM que também usa 6)
    # Em algumas versões do pysus o campo é CODMUNNASC ou CODMUNRES
    campo_mun = None
    for campo in ["CODMUNRES", "CODMUNNASC", "CODMUNOCOR"]:
        if campo in df.columns:
            campo_mun = campo
            break

    if campo_mun is None:
        print(f"  AVISO: campo de município não encontrado em {uf}/{ano}. Colunas: {list(df.columns[:10])}")
        return {}

    df["cod_municipio"] = pd.to_numeric(df[campo_mun], errors="coerce")
    df = df.dropna(subset=["cod_municipio"])
    df = df[df["cod_municipio"] > 0]

    # Converte 7 dígitos para 6 se necessário (SINASC às vezes retorna 7)
    df["cod_municipio"] = df["cod_municipio"].astype(int)
    df.loc[df["cod_municipio"] > 999999, "cod_municipio"] //= 10

    contagem = df.groupby("cod_municipio").size().to_dict()
    return contagem


def main():
    parser = argparse.ArgumentParser(description="Carrega SINASC multi-ano")
    parser.add_argument("--anos", nargs="+", type=int,
                        default=list(range(ANO_INICIO, ANO_FIM + 1)))
    parser.add_argument("--ufs", nargs="+", default=UFS_BRASIL)
    parser.add_argument("--workers", type=int, default=1,
                        help="Workers paralelos (padrão: 1 — DataSUS FTP limita paralelo)")
    args = parser.parse_args()

    anos = sorted(args.anos)
    ufs  = [u.upper() for u in args.ufs]
    tarefas = [(uf, ano) for ano in anos for uf in ufs]

    print(f"Carregando SINASC: {len(tarefas)} combinações ({len(ufs)} UFs × {len(anos)} anos)")

    # Agrupa por ano para fazer 1 INSERT por ano
    por_ano = defaultdict(lambda: defaultdict(int))

    def processar(uf, ano):
        result = processar_uf_ano(uf, ano)
        print(f"  {uf}/{ano}: {sum(result.values()):,} nascidos")
        return ano, UF_COD.get(uf), result

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futuros = {ex.submit(processar, uf, ano): (uf, ano) for uf, ano in tarefas}
        for fut in as_completed(futuros):
            uf_ano = futuros[fut]
            try:
                ano, cod_uf, contagem = fut.result()
                for cod_mun, n in contagem.items():
                    por_ano[ano][cod_mun] += n
            except Exception as e:
                print(f"  ERRO em {uf_ano}: {e}")

    # Insere no banco, um ano por vez
    conn = get_conn()
    try:
        for ano in sorted(por_ano):
            contagem_ano = por_ano[ano]
            # Remove registros existentes para este ano (idempotência)
            with conn.cursor() as cur:
                cur.execute("DELETE FROM saude.sinasc_municipios WHERE ano = %s", (ano,))

                rows = []
                for cod_mun, n in contagem_ano.items():
                    cod_uf = cod_mun // 10000
                    rows.append((cod_mun, cod_uf, ano, n))

                execute_values(
                    cur,
                    """
                    INSERT INTO saude.sinasc_municipios
                        (cod_municipio, cod_uf, ano, nascidos_vivos)
                    VALUES %s
                    """,
                    rows,
                    page_size=2000,
                )
                print(f"  Ano {ano}: {len(rows):,} municípios inseridos")
            conn.commit()
    finally:
        conn.close()

    print("Concluído.")


if __name__ == "__main__":
    main()
