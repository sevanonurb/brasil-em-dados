#!/usr/bin/env python3
"""
load_censo_escolar.py
Carrega taxas de rendimento escolar e distorção idade-série do INEP (Censo Escolar)
para api.metricas_municipio.

Fontes:
  TRE_municipios_{ano}.xlsx — Taxas de Rendimento Escolar por município
  TDI_municipios_{ano}.xlsx — Taxas de Distorção Idade-Série por município

Indicadores (% ponderada por matrículas, nível municipal):
  taxa_aprovacao_ef   — aprovação Ensino Fundamental total (%)
  taxa_reprovacao_ef  — reprovação Ensino Fundamental total (%)
  taxa_abandono_ef    — abandono Ensino Fundamental total (%)
  taxa_aprovacao_em   — aprovação Ensino Médio total (%)
  taxa_abandono_em    — abandono Ensino Médio total (%)
  distorcao_idade_serie_ef — distorção idade-série Ens. Fundamental (%)
  distorcao_idade_serie_em — distorção idade-série Ens. Médio (%)

Uso:
    python load_censo_escolar.py                     # 2010-2024, todos indicadores
    python load_censo_escolar.py --anos 2020 2021 2022
    python load_censo_escolar.py --skip-distorcao    # só taxas de rendimento
"""

import argparse
import io
import os
import time

import psycopg2
import pandas as pd
import requests
from psycopg2.extras import execute_values

DB_PARAMS = dict(
    host=os.environ.get("POSTGRES_HOST", "localhost"),
    port=int(os.environ.get("POSTGRES_PORT", 5432)),
    database=os.environ.get("POSTGRES_DB", "brasil_dados"),
    user=os.environ.get("POSTGRES_USER", "brasil"),
    password=os.environ.get("POSTGRES_PASSWORD", ""),
)

# URLs base das planilhas INEP
INEP_BASE = "https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais"
TRE_URL   = f"{INEP_BASE}/taxas_de_rendimento/TRE_municipios_{{ano}}.xlsx"
TDI_URL   = f"{INEP_BASE}/distorcao_idade_serie/TDI_municipios_{{ano}}.xlsx"


def download_excel(url: str, ano: int) -> pd.DataFrame | None:
    """Baixa planilha Excel INEP e retorna DataFrame, ou None em caso de erro."""
    print(f"  GET {url} ...")
    for tentativa in range(3):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200:
                break
            print(f"    HTTP {r.status_code}, aguardando 5s...")
            time.sleep(5)
        except requests.exceptions.Timeout:
            print(f"    Timeout tentativa {tentativa+1}/3, aguardando 5s...")
            time.sleep(5)
    else:
        print(f"  ERRO: {url} falhou após 3 tentativas")
        return None

    try:
        df = pd.read_excel(io.BytesIO(r.content), header=8, dtype=str)
        return df
    except Exception as e:
        print(f"  ERRO ao ler Excel: {e}")
        return None


def upsert_metricas(rows: list[tuple], conn):
    """Insere/atualiza registros em api.metricas_municipio."""
    if not rows:
        print("  Sem dados para inserir.")
        return
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO api.metricas_municipio (cod_municipio, metrica, ano, valor)
            VALUES %s
            ON CONFLICT (cod_municipio, metrica, ano)
            DO UPDATE SET valor = EXCLUDED.valor
            """,
            rows,
            page_size=2000,
        )
    conn.commit()
    print(f"  Upserted {len(rows):,} registros em api.metricas_municipio")


def _safe_float(val) -> float | None:
    """Converte para float, ignorando '-', '--', NaN, etc."""
    try:
        v = float(str(val).replace(",", ".").strip())
        if v < 0 or v > 100:
            return None
        return v
    except (ValueError, TypeError):
        return None


def _find_col(df: pd.DataFrame, *candidates: str) -> str | None:
    """Encontra a primeira coluna que corresponde a um dos candidatos (case-insensitive, strip)."""
    cols_lower = {c.strip().lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in cols_lower:
            return cols_lower[cand.lower()]
    # Busca parcial
    for cand in candidates:
        for col_low, col_orig in cols_lower.items():
            if cand.lower() in col_low:
                return col_orig
    return None


def carregar_tre(conn, anos: list[int]):
    """
    Carrega Taxas de Rendimento Escolar (aprovação, reprovação, abandono) por município.
    Planilha TRE tem colunas: CO_MUNICIPIO, APR (total EF), REP (total EF), ABA (total EF),
    APR (total EM), ABA (total EM), etc.
    A estrutura exata das colunas muda entre anos — usamos busca flexível.
    """
    print("\n=== INEP: Taxas de Rendimento Escolar (TRE) ===")
    for ano in anos:
        url = TRE_URL.format(ano=ano)
        df = download_excel(url, ano)
        if df is None:
            continue

        # Normaliza nomes de coluna
        df.columns = [str(c).strip() for c in df.columns]
        print(f"  Ano {ano}: colunas = {list(df.columns[:20])}")

        # Coluna de código de município (7 dígitos)
        col_cod = _find_col(df, "CO_MUNICIPIO", "Cod_Municipio", "CO_MUN", "cod_municipio")
        if col_cod is None:
            print(f"  AVISO: coluna de código de município não encontrada — pulando {ano}")
            continue

        # Converte cod_municipio para int
        df[col_cod] = pd.to_numeric(df[col_cod], errors="coerce")
        df = df.dropna(subset=[col_cod])
        df[col_cod] = df[col_cod].astype(int)

        rows = []

        # Detecta colunas de EF Total — podem ter nome "EF - Total" ou "Ensino Fundamental"
        # Aprovação EF
        col_apr_ef = _find_col(df, "APR", "Aprovação", "Aprovacao")
        # Reprovação EF
        col_rep_ef = _find_col(df, "REP", "Reprovação", "Reprovacao")
        # Abandono EF
        col_aba_ef = _find_col(df, "ABA", "Abandono")

        # A planilha TRE normalmente tem múltiplas colunas com o mesmo nome (APR, REP, ABA)
        # para cada nível de ensino. Pandas adiciona sufixos .1, .2, etc.
        # Padrão típico: col 0=EF-Iniciais, 1=EF-Finais, 2=EF-Total, 3=EM
        # Buscamos por posição após identificar o bloco correto.
        col_names = list(df.columns)

        # Estratégia: encontrar todas as colunas APR, REP, ABA e usar a terceira (EF Total)
        apr_cols = [c for c in col_names if "APR" in str(c).upper() or "APROVAÇÃO" in str(c).upper() or "APROVACAO" in str(c).upper()]
        rep_cols = [c for c in col_names if "REP" in str(c).upper() or "REPROVAÇÃO" in str(c).upper() or "REPROVACAO" in str(c).upper()]
        aba_cols = [c for c in col_names if "ABA" in str(c).upper() or "ABANDONO" in str(c).upper()]

        print(f"    APR cols: {apr_cols[:6]}, REP cols: {rep_cols[:4]}, ABA cols: {aba_cols[:4]}")

        # EF Total = índice 2 (0=EF-Iniciais, 1=EF-Finais, 2=EF-Total)
        # EM = índice 3
        def get_col(cols, idx):
            return cols[idx] if len(cols) > idx else None

        col_apr_ef_t = get_col(apr_cols, 2)   # EF Total
        col_rep_ef_t = get_col(rep_cols, 2)   # EF Total
        col_aba_ef_t = get_col(aba_cols, 2)   # EF Total
        col_apr_em   = get_col(apr_cols, 3)   # EM
        col_aba_em   = get_col(aba_cols, 3)   # EM

        metricas = [
            (col_apr_ef_t, "taxa_aprovacao_ef"),
            (col_rep_ef_t, "taxa_reprovacao_ef"),
            (col_aba_ef_t, "taxa_abandono_ef"),
            (col_apr_em,   "taxa_aprovacao_em"),
            (col_aba_em,   "taxa_abandono_em"),
        ]

        for col, metrica in metricas:
            if col is None or col not in df.columns:
                print(f"    AVISO: coluna para {metrica} não encontrada")
                continue
            for _, row in df.iterrows():
                cod = row[col_cod]
                val = _safe_float(row[col])
                if val is not None:
                    rows.append((int(cod), metrica, ano, val))

        print(f"  Ano {ano}: {len(rows)} registros")
        upsert_metricas(rows, conn)


def carregar_tdi(conn, anos: list[int]):
    """
    Carrega Taxas de Distorção Idade-Série por município.
    Planilha TDI tem: CO_MUNICIPIO, colunas EF Total, EM.
    """
    print("\n=== INEP: Distorção Idade-Série (TDI) ===")
    for ano in anos:
        url = TDI_URL.format(ano=ano)
        df = download_excel(url, ano)
        if df is None:
            continue

        df.columns = [str(c).strip() for c in df.columns]
        print(f"  Ano {ano}: colunas = {list(df.columns[:20])}")

        col_cod = _find_col(df, "CO_MUNICIPIO", "Cod_Municipio", "CO_MUN", "cod_municipio")
        if col_cod is None:
            print(f"  AVISO: coluna de código não encontrada — pulando {ano}")
            continue

        df[col_cod] = pd.to_numeric(df[col_cod], errors="coerce")
        df = df.dropna(subset=[col_cod])
        df[col_cod] = df[col_cod].astype(int)

        col_names = list(df.columns)

        # TDI: colunas de distorção para EF Total e EM
        # Busca colunas que contenham valores percentuais por nível
        # Padrão: [EF - Anos Iniciais, EF - Anos Finais, EF - Total, EM]
        # Pegamos a 3ª ocorrência (EF Total) e 4ª (EM) de qualquer coluna numérica após CO_MUNICIPIO
        num_cols = [c for c in col_names if c != col_cod and c not in ("CO_UF", "CO_MESORREGIAO", "CO_MICRORREGIAO", "NO_MUNICIPIO", "NO_UF", "SG_UF", "NO_REGIAO")]

        # Filtra colunas com valores numéricos
        valid_num = []
        for c in num_cols:
            series = pd.to_numeric(df[c].astype(str).str.replace(",", "."), errors="coerce")
            if series.notna().sum() > 10:
                valid_num.append(c)

        print(f"    Colunas numéricas: {valid_num[:8]}")

        # EF Total = índice 2, EM = índice 3 (assumindo EF-Ini, EF-Fin, EF-Tot, EM)
        col_ef = valid_num[2] if len(valid_num) > 2 else None
        col_em = valid_num[3] if len(valid_num) > 3 else None

        rows = []
        for col, metrica in [(col_ef, "distorcao_idade_serie_ef"), (col_em, "distorcao_idade_serie_em")]:
            if col is None:
                print(f"    AVISO: coluna para {metrica} não encontrada")
                continue
            for _, row in df.iterrows():
                cod = row[col_cod]
                val = _safe_float(row[col])
                if val is not None:
                    rows.append((int(cod), metrica, ano, val))

        print(f"  Ano {ano}: {len(rows)} registros")
        upsert_metricas(rows, conn)


def main():
    parser = argparse.ArgumentParser(
        description="Carrega Censo Escolar INEP em api.metricas_municipio"
    )
    parser.add_argument(
        "--anos", nargs="+", type=int,
        default=list(range(2010, 2025)),
        help="Anos a carregar (padrão: 2010-2024)"
    )
    parser.add_argument("--skip-rendimento", action="store_true",
                        help="Pula taxas de rendimento (TRE)")
    parser.add_argument("--skip-distorcao",  action="store_true",
                        help="Pula distorção idade-série (TDI)")
    args = parser.parse_args()

    print("Conectando ao banco...")
    conn = psycopg2.connect(**DB_PARAMS)

    try:
        if not args.skip_rendimento:
            carregar_tre(conn, args.anos)
        if not args.skip_distorcao:
            carregar_tdi(conn, args.anos)
    finally:
        conn.close()

    print("\n=== Concluído ===")
    print("Verificar com:")
    print("  SELECT metrica, ano, COUNT(*), ROUND(AVG(valor)::numeric,1) AS media")
    print("  FROM api.metricas_municipio")
    print("  WHERE metrica LIKE 'taxa_aprovacao%' OR metrica LIKE 'distorcao%'")
    print("  GROUP BY metrica, ano ORDER BY metrica, ano;")


if __name__ == "__main__":
    main()
