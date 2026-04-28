"""
load_cnes.py
Carrega dados do CNES/DataSUS (Cadastro Nacional de Estabelecimentos de Saúde)
via PySUS: leitos (grupo LT) e médicos (grupo PF).

Estratégia: baixa o mês de dezembro de cada ano (competência mais recente).
Agrupa por município (CODUFMUN, 6 dígitos) e soma leitos SUS e médicos (CBO 22xx).

Uso:
    python load_cnes.py                    # carrega 2015–2023
    python load_cnes.py --anos 2022 2023   # apenas esses anos
    python load_cnes.py --ufs SP RJ        # apenas esses estados

Resultado: saude.cnes_municipios (cod_municipio 6 dígitos DataSUS, por ano)
"""

import argparse
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

import psycopg2
import pandas as pd
from psycopg2.extras import execute_values

try:
    from pysus.online_data.CNES import CNES
except ImportError:
    try:
        from pysus.online_data import CNES
    except ImportError:
        raise ImportError("PySUS não encontrado. Instale: pip install pysus")

# PySUS v1.x: CNES é uma classe, precisa ser instanciada
_cnes = CNES()

UFS_BRASIL = [
    "AC","AL","AP","AM","BA","CE","DF","ES","GO",
    "MA","MT","MS","MG","PA","PB","PR","PE","PI",
    "RJ","RN","RS","RO","RR","SC","SP","SE","TO",
]

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


def baixar_grupo(grupo: str, uf: str, ano: int) -> pd.DataFrame:
    """Baixa arquivo CNES do grupo informado para UF/ano (mês 12). PySUS v1.x."""
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            files = _cnes.get_files(grupo, uf=uf, year=ano, month=12)
            if not files:
                return pd.DataFrame()
            parquet_set = _cnes.download(files, local_dir=tmpdir)
            return parquet_set.to_dataframe()
        except Exception as e:
            print(f"  ERRO {grupo} {uf}/{ano}: {e}")
            return pd.DataFrame()


def processar_leitos(uf: str, ano: int) -> dict:
    """Retorna dicionário cod_municipio → (leitos_sus, leitos_total)."""
    df = baixar_grupo("LT", uf, ano)
    if df.empty:
        return {}

    # Campo de município: CODUFMUN (6 dígitos) ou CODMUNICIPIO
    campo = "CODUFMUN" if "CODUFMUN" in df.columns else "CODMUNICIPIO"
    if campo not in df.columns:
        print(f"  AVISO LT {uf}/{ano}: campo município não encontrado")
        return {}

    df["cod_mun"] = pd.to_numeric(df[campo], errors="coerce")
    df = df.dropna(subset=["cod_mun"])

    qt_sus   = pd.to_numeric(df.get("QT_SUS", 0), errors="coerce").fillna(0)
    qt_exist = pd.to_numeric(df.get("QT_EXIST", 0), errors="coerce").fillna(0)
    df = df.assign(qt_sus=qt_sus, qt_exist=qt_exist)

    resultado = (
        df.groupby("cod_mun")[["qt_sus", "qt_exist"]]
          .sum()
          .astype(int)
          .to_dict("index")
    )
    return {int(k): (v["qt_sus"], v["qt_exist"]) for k, v in resultado.items()}


def processar_medicos(uf: str, ano: int) -> dict:
    """
    Retorna dicionário cod_municipio → count de médicos.
    Médicos: CBO começa com '22' (grupo médico conforme CBO 2002).
    """
    df = baixar_grupo("PF", uf, ano)
    if df.empty:
        return {}

    campo = "CODUFMUN" if "CODUFMUN" in df.columns else "CODMUNICIPIO"
    if campo not in df.columns:
        return {}

    df["cod_mun"] = pd.to_numeric(df[campo], errors="coerce")
    df = df.dropna(subset=["cod_mun"])

    # Filtra médicos: CBO começa com '22'
    cbo_col = "CBO" if "CBO" in df.columns else None
    if cbo_col:
        df["cbo_str"] = df[cbo_col].astype(str).str.strip()
        df = df[df["cbo_str"].str.startswith("22")]

    # Conta profissionais únicos por município (um profissional pode estar em vários estabelecimentos)
    # Usa NOMEPROF ou CNS_PROF como chave de deduplicação, se disponível
    chave = None
    for c in ["CNS_PROF", "NOMEPROF", "CPF_PROF"]:
        if c in df.columns:
            chave = c
            break

    if chave:
        resultado = df.groupby("cod_mun")[chave].nunique().to_dict()
    else:
        resultado = df.groupby("cod_mun").size().to_dict()

    return {int(k): int(v) for k, v in resultado.items()}


def main():
    parser = argparse.ArgumentParser(description="Carrega CNES multi-ano")
    parser.add_argument("--anos", nargs="+", type=int,
                        default=list(range(ANO_INICIO, ANO_FIM + 1)))
    parser.add_argument("--ufs", nargs="+", default=UFS_BRASIL)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()

    anos = sorted(args.anos)
    ufs  = [u.upper() for u in args.ufs]
    tarefas = [(uf, ano) for ano in anos for uf in ufs]

    print(f"Carregando CNES: {len(tarefas)} combinações (UFs × anos)")

    por_ano: dict[int, dict[int, list]] = {ano: defaultdict(lambda: [0, 0, 0]) for ano in anos}

    def processar(uf, ano):
        leitos = processar_leitos(uf, ano)
        medicos = processar_medicos(uf, ano)
        print(f"  {uf}/{ano}: {len(leitos)} municípios com leitos, {len(medicos)} com médicos")
        return ano, leitos, medicos

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futuros = {ex.submit(processar, uf, ano): (uf, ano) for uf, ano in tarefas}
        for fut in as_completed(futuros):
            uf_ano = futuros[fut]
            try:
                ano, leitos, medicos = fut.result()
                for cod, (sus, total) in leitos.items():
                    por_ano[ano][cod][0] += sus
                    por_ano[ano][cod][1] += total
                for cod, med in medicos.items():
                    por_ano[ano][cod][2] += med
            except Exception as e:
                print(f"  ERRO em {uf_ano}: {e}")

    conn = get_conn()
    try:
        for ano in sorted(por_ano):
            dados_ano = por_ano[ano]
            with conn.cursor() as cur:
                cur.execute("DELETE FROM saude.cnes_municipios WHERE ano = %s", (ano,))

                rows = []
                for cod_mun, (leitos_sus, leitos_total, medicos) in dados_ano.items():
                    cod_uf = cod_mun // 10000
                    rows.append((cod_mun, cod_uf, ano, leitos_sus, leitos_total, medicos))

                execute_values(
                    cur,
                    """
                    INSERT INTO saude.cnes_municipios
                        (cod_municipio, cod_uf, ano, leitos_sus, leitos_total, medicos)
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
