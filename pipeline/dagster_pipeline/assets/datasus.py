"""
Assets Dagster para ingestão dos microdados DataSUS (SIM — Sistema de
Informações sobre Mortalidade). Usa PySUS para extração incremental.
Leitura em batches de 100k registros para controle de memória (anti-OOM).
"""

import os
from pathlib import Path

import pandas as pd
import psycopg2
import structlog
from dagster import (
    AssetExecutionContext,
    MetadataValue,
    Output,
    asset,
)
from sqlalchemy import create_engine, text

log = structlog.get_logger()

BATCH_SIZE = 100_000  # registros por batch — ~15MB RAM peak

# Mapeamento de capitais de CID-10 para leitura humana
CID10_CAPITULOS = {
    "A": "Doenças infecciosas e parasitárias",
    "B": "Doenças infecciosas e parasitárias",
    "C": "Neoplasias malignas",
    "D": "Neoplasias benignas",
    "E": "Doenças endócrinas e metabólicas",
    "F": "Transtornos mentais",
    "G": "Doenças do sistema nervoso",
    "H": "Olhos e ouvidos",
    "I": "Doenças cardiovasculares",
    "J": "Doenças respiratórias",
    "K": "Doenças digestivas",
    "P": "Perinatais",
    "Q": "Malformações congênitas",
    "R": "Sintomas e sinais",
    "S": "Lesões e traumatismos",
    "T": "Envenenamentos",
    "V": "Causas externas — acidentes",
    "W": "Causas externas — quedas",
    "X": "Causas externas — outros",
    "Y": "Causas externas — agressões",
    "Z": "Fatores de saúde",
}


def get_db_conn():
    return psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        database=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def normalizar_sim(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza e seleciona colunas dos microdados SIM.
    O DataSUS tem naming conventions inconsistentes entre anos.
    """
    # Mapeamento de colunas entre versões do SIM
    col_map = {
        "CODMUNRES": "cod_municipio",   # município de residência (7 dígitos)
        "DTOBITO": "data_obito",
        "CAUSABAS": "cid10_codigo",
        "IDADE": "idade_raw",
        "SEXO": "sexo",
        "RACACOR": "cor_raca",
        "ESC": "escolaridade",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # cod_municipio: primeiros 7 dígitos (código IBGE)
    if "cod_municipio" in df.columns:
        df["cod_municipio"] = pd.to_numeric(
            df["cod_municipio"].astype(str).str[:7],
            errors="coerce",
        ).astype("Int64")

    # UF: primeiros 2 dígitos do código de município
    # SIM usa código IBGE 6 dígitos (SSMMMMM): primeiros 2 = UF → dividir por 10000
    df["cod_uf"] = (df["cod_municipio"] // 10000).astype("Int16")

    # Ano e mês a partir da data de óbito (DDMMAAAA)
    if "data_obito" in df.columns:
        dt = pd.to_datetime(
            df["data_obito"].astype(str).str.zfill(8),
            format="%d%m%Y",
            errors="coerce",
        )
        df["ano"] = dt.dt.year.astype("Int16")
        df["mes"] = dt.dt.month.astype("Int16")
    else:
        df["ano"] = None
        df["mes"] = None

    # Capítulo CID-10 (primeira letra do código)
    if "cid10_codigo" in df.columns:
        df["cid10_capitulo"] = (
            df["cid10_codigo"].astype(str).str[0].str.upper()
        )
        # Valida: apenas letras A-Z
        df.loc[~df["cid10_capitulo"].str.match(r"^[A-Z]$", na=False), "cid10_capitulo"] = None

    # Faixa etária padronizada (0-17)
    # DataSUS codifica idade de forma peculiar: 4XX = XX anos, 3XX = XX meses, etc.
    if "idade_raw" in df.columns:
        idade_str = df["idade_raw"].astype(str).str.zfill(3)
        tipo = idade_str.str[0].astype(int, errors="ignore")
        valor = pd.to_numeric(idade_str.str[1:], errors="coerce")

        # Converte para anos
        anos = pd.Series(index=df.index, dtype="float64")
        anos[tipo == 4] = valor[tipo == 4]           # 4XX = anos
        anos[tipo == 3] = valor[tipo == 3] / 12      # 3XX = meses → anos
        anos[tipo <= 2] = 0                           # dias/horas → <1 ano

        # Faixas de 5 anos (0=<1ano, 1=1-4, 2=5-9, ..., 17=80+)
        bins = [-1, 0.99, 4, 9, 14, 19, 24, 29, 34, 39, 44, 49, 54, 59, 64, 69, 74, 79, 999]
        df["faixa_etaria"] = pd.cut(
            anos, bins=bins, labels=range(18), right=True
        ).astype("Int16")

    # Normalização de cor/raça
    if "cor_raca" in df.columns:
        df["cor_raca"] = pd.to_numeric(df["cor_raca"], errors="coerce").astype("Int16")
        df.loc[~df["cor_raca"].isin([1, 2, 3, 4, 5]), "cor_raca"] = None

    # Sexo
    if "sexo" in df.columns:
        df["sexo"] = df["sexo"].astype(str).str.upper().str[0]
        df.loc[~df["sexo"].isin(["M", "F"]), "sexo"] = "I"

    if "escolaridade" in df.columns:
        df["escolaridade"] = pd.to_numeric(df["escolaridade"], errors="coerce").astype("Int16")

    # Seleciona apenas colunas necessárias
    cols = ["cod_municipio", "cod_uf", "ano", "mes", "cid10_codigo",
            "cid10_capitulo", "faixa_etaria", "sexo", "cor_raca", "escolaridade"]
    return df[[c for c in cols if c in df.columns]]


@asset(
    group_name="datasus_sim",
    description=(
        "Ingestão incremental do SIM/DataSUS usando PySUS v1.x. "
        "Download via FTP DataSUS → ParquetSet → DataFrame. "
        "Leitura em batches de 100k registros (anti-OOM). "
        "Dados normalizados e carregados particionados por UF."
    ),
    compute_kind="pysus",
)
def sim_mortalidade_raw(context: AssetExecutionContext) -> Output[None]:
    try:
        from pysus.online_data import SIM
    except ImportError:
        raise ImportError("PySUS não instalado. Execute: pip install pysus")

    import tempfile

    # Estados a processar neste run
    ufs_alvo = context.op_config.get("ufs", ["SP", "RJ", "MG", "BA", "RS"])
    ano_alvo = context.op_config.get("ano", 2022)  # 2022 é o mais recente estável no FTP

    total_inseridos = 0
    conn = get_db_conn()

    try:
        from psycopg2.extras import execute_values

        for sigla_uf in ufs_alvo:
            context.log.info(f"Processando SIM/{sigla_uf}/{ano_alvo}...")

            try:
                # PySUS v1.x: download retorna ParquetSet
                with tempfile.TemporaryDirectory() as tmpdir:
                    parquet_set = SIM.download("CID10", sigla_uf, ano_alvo, data_dir=tmpdir)
                    df_raw = parquet_set.to_dataframe()
            except Exception as e:
                context.log.warning(
                    f"Falha ao baixar SIM/{sigla_uf}/{ano_alvo}: {e}. Pulando."
                )
                continue

            total_rows = len(df_raw)
            context.log.info(f"SIM/{sigla_uf}: {total_rows:,} registros brutos")

            with conn.cursor() as cur:
                for batch_start in range(0, total_rows, BATCH_SIZE):
                    batch = normalizar_sim(
                        df_raw.iloc[batch_start:batch_start + BATCH_SIZE].copy()
                    )
                    batch = batch.dropna(subset=["cod_municipio", "ano", "cid10_capitulo"])

                    if batch.empty:
                        continue

                    # Converte nullable Int → object (None para NA); psycopg2 não adapta numpy.int64
                    for col in batch.select_dtypes(include=["Int8","Int16","Int32","Int64"]).columns:
                        batch[col] = batch[col].astype(object).where(batch[col].notna(), None)

                    insert_sql = """
                        INSERT INTO saude.sim_mortalidade
                            (cod_municipio, cod_uf, ano, mes, cid10_codigo,
                             cid10_capitulo, faixa_etaria, sexo, cor_raca, escolaridade)
                        VALUES %s
                        ON CONFLICT DO NOTHING
                    """
                    execute_values(
                        cur,
                        insert_sql,
                        batch.itertuples(index=False, name=None),
                        page_size=BATCH_SIZE,
                    )
                    total_inseridos += cur.rowcount

                conn.commit()
                context.log.info(f"SIM/{sigla_uf}/{ano_alvo}: commit OK")

    finally:
        conn.close()

    # Após ingestão: refresh das views e notificação de cache
    engine = create_engine(
        f"postgresql+psycopg2://"
        f"{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
        f"@{os.environ['POSTGRES_HOST']}:5432/{os.environ['POSTGRES_DB']}"
    )
    with engine.begin() as c:
        c.execute(text("REFRESH MATERIALIZED VIEW api.indicadores_municipio"))
        c.execute(text("REFRESH MATERIALIZED VIEW api.indicadores_uf"))
        c.execute(text("SELECT api.notify_cache_invalidation('sim_mortalidade', NULL)"))

    return Output(
        None,
        metadata={
            "registros_inseridos": MetadataValue.int(total_inseridos),
            "ufs_processadas": MetadataValue.text(", ".join(ufs_alvo)),
            "ano": MetadataValue.int(ano_alvo),
        },
    )
