#!/usr/bin/env python3
"""
load_censo_escolar.py
Carrega taxas de rendimento escolar e distorção idade-série do INEP (Censo Escolar)
para api.metricas_municipio.

Fontes (arquivos ZIP com XLSX interno):
  TRE — https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/{ano}/tx_rend_municipios_{ano}.zip
  TDI — https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/{ano}/TDI_{ano}_MUNICIPIOS.zip

Indicadores (nível municipal, filtro Total/Total):
  taxa_aprovacao_ef   — 1_CAT_FUN  (aprovação EF Total, %)
  taxa_reprovacao_ef  — 2_CAT_FUN  (reprovação EF Total, %)
  taxa_abandono_ef    — 3_CAT_FUN  (abandono EF Total, %)
  taxa_aprovacao_em   — 1_CAT_MED  (aprovação EM Total, %)
  taxa_abandono_em    — 3_CAT_MED  (abandono EM Total, %)
  distorcao_idade_serie_ef — FUN_CAT_0 (distorção EF Total, %)
  distorcao_idade_serie_em — MED_CAT_0 (distorção EM Total, %)

Uso:
    python load_censo_escolar.py                     # 2015-2024, todos indicadores
    python load_censo_escolar.py --anos 2020 2021 2022
    python load_censo_escolar.py --skip-distorcao    # só taxas de rendimento
"""

import argparse
import io
import os
import time
import zipfile
import warnings

import psycopg2
import pandas as pd
import requests
import urllib3
from psycopg2.extras import execute_values

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

DB_PARAMS = dict(
    host=os.environ.get("POSTGRES_HOST", "localhost"),
    port=int(os.environ.get("POSTGRES_PORT", 5432)),
    database=os.environ.get("POSTGRES_DB", "brasil_dados"),
    user=os.environ.get("POSTGRES_USER", "brasil"),
    password=os.environ.get("POSTGRES_PASSWORD", ""),
)

INEP_BASE = "https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais"

# URL templates para os ZIPs municipais
TRE_ZIP_URL = f"{INEP_BASE}/{{ano}}/tx_rend_municipios_{{ano}}.zip"
TDI_ZIP_URL = f"{INEP_BASE}/{{ano}}/TDI_{{ano}}_MUNICIPIOS.zip"


def download_zip(url: str) -> bytes | None:
    """Baixa um ZIP via HTTPS (sem verificação de SSL) com retry."""
    print(f"  GET {url} ...")
    for tentativa in range(3):
        try:
            r = requests.get(url, timeout=180, verify=False)
            if r.status_code == 200:
                return r.content
            print(f"    HTTP {r.status_code}, aguardando 5s...")
            time.sleep(5)
        except requests.exceptions.Timeout:
            print(f"    Timeout tentativa {tentativa+1}/3, aguardando 5s...")
            time.sleep(5)
        except Exception as e:
            print(f"    Erro tentativa {tentativa+1}/3: {e}")
            time.sleep(5)
    print(f"  ERRO: {url} falhou após 3 tentativas")
    return None


def extract_xlsx_from_zip(zip_bytes: bytes) -> bytes | None:
    """Extrai o primeiro arquivo .xlsx do ZIP e retorna seu conteúdo."""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            xlsx_names = [n for n in z.namelist() if n.lower().endswith(".xlsx")]
            if not xlsx_names:
                print("  AVISO: nenhum .xlsx encontrado no ZIP")
                return None
            with z.open(xlsx_names[0]) as f:
                return f.read()
    except Exception as e:
        print(f"  ERRO ao extrair ZIP: {e}")
        return None


def read_inep_xlsx(xlsx_bytes: bytes, kind: str = "generic") -> pd.DataFrame | None:
    """
    Lê planilha INEP. Suporta dois formatos:
    - Moderno (2020+): linha 8 tem nomes de máquina (NU_ANO_CENSO, CO_MUNICIPIO, ...)
    - Legado (TRE 2019): linha 8 é NaN; dados começam na linha 9 (colunas posicionais)

    Retorna DataFrame filtrado para Total/Total com nomes de coluna padronizados.
    kind: "tre" (ativa mapeamento posicional para formato legado) ou "tdi"/"generic"
    """
    # Peeka linha 8 para detectar formato
    try:
        raw = pd.read_excel(io.BytesIO(xlsx_bytes), header=None, dtype=str, nrows=10, engine="openpyxl")
    except Exception as e:
        print(f"  ERRO ao ler XLSX: {e}")
        return None

    row8 = list(raw.iloc[8]) if len(raw) > 8 else []
    is_modern = any("CO_MUNICIPIO" in str(v) or "NU_ANO_CENSO" in str(v) for v in row8)

    if is_modern:
        # Formato moderno: linha 8 é o cabeçalho de máquina
        try:
            df = pd.read_excel(io.BytesIO(xlsx_bytes), header=8, dtype=str, engine="openpyxl")
        except Exception as e:
            print(f"  ERRO ao ler XLSX (moderno): {e}")
            return None
    else:
        # Formato legado (TRE 2019): dados na linha 9, colunas posicionais
        try:
            df = pd.read_excel(io.BytesIO(xlsx_bytes), header=None,
                               skiprows=9, dtype=str, engine="openpyxl")
        except Exception as e:
            print(f"  ERRO ao ler XLSX (legado): {e}")
            return None

        # Renomeia colunas posicionais para nomes padronizados
        col_map = {
            df.columns[3]: "CO_MUNICIPIO",
            df.columns[5]: "NO_CATEGORIA",
            df.columns[6]: "NO_DEPENDENCIA",
        }
        if kind == "tre" and len(df.columns) > 55:
            col_map.update({
                df.columns[7]:  "1_CAT_FUN",   # APR EF Total
                df.columns[19]: "1_CAT_MED",   # APR EM Total
                df.columns[25]: "2_CAT_FUN",   # REP EF Total
                df.columns[43]: "3_CAT_FUN",   # ABA EF Total
                df.columns[55]: "3_CAT_MED",   # ABA EM Total
            })
        df = df.rename(columns=col_map)

    if df is None or df.empty:
        return None

    # Filtra só Total × Total (município agregado, todas dependências)
    if "NO_CATEGORIA" in df.columns and "NO_DEPENDENCIA" in df.columns:
        mask = (df["NO_CATEGORIA"].astype(str).str.strip() == "Total") & \
               (df["NO_DEPENDENCIA"].astype(str).str.strip() == "Total")
        df = df[mask].reset_index(drop=True)

    return df


def _safe_float(val) -> float | None:
    """Converte para float, ignorando '--', '-', NaN, etc."""
    try:
        v = float(str(val).replace(",", ".").strip())
        if v < 0 or v > 100:
            return None
        return v
    except (ValueError, TypeError):
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


def carregar_tre(conn, anos: list[int]):
    """
    Carrega Taxas de Rendimento Escolar (aprovação, reprovação, abandono).
    Colunas relevantes: 1_CAT_FUN (APR EF), 2_CAT_FUN (REP EF), 3_CAT_FUN (ABA EF),
                        1_CAT_MED (APR EM), 3_CAT_MED (ABA EM).
    """
    print("\n=== INEP: Taxas de Rendimento Escolar (TRE) ===")
    for ano in anos:
        url = TRE_ZIP_URL.format(ano=ano)
        zip_bytes = download_zip(url)
        if zip_bytes is None:
            continue

        xlsx_bytes = extract_xlsx_from_zip(zip_bytes)
        if xlsx_bytes is None:
            continue

        df = read_inep_xlsx(xlsx_bytes, kind="tre")
        if df is None or df.empty:
            print(f"  Ano {ano}: DataFrame vazio após leitura")
            continue

        print(f"  Ano {ano}: {len(df)} municípios, colunas disponíveis: {list(df.columns[:10])}")

        metricas = [
            ("1_CAT_FUN", "taxa_aprovacao_ef"),
            ("2_CAT_FUN", "taxa_reprovacao_ef"),
            ("3_CAT_FUN", "taxa_abandono_ef"),
            ("1_CAT_MED", "taxa_aprovacao_em"),
            ("3_CAT_MED", "taxa_abandono_em"),
        ]

        rows = []
        for col, metrica in metricas:
            if col not in df.columns:
                print(f"    AVISO: coluna {col} não encontrada para {metrica}")
                continue
            for _, row in df.iterrows():
                try:
                    cod = int(float(str(row["CO_MUNICIPIO"]).strip()))
                except (ValueError, KeyError):
                    continue
                val = _safe_float(row[col])
                if val is not None:
                    rows.append((cod, metrica, ano, val))

        print(f"  Ano {ano}: {len(rows)} registros")
        upsert_metricas(rows, conn)


def carregar_tdi(conn, anos: list[int]):
    """
    Carrega Taxas de Distorção Idade-Série por município.
    Colunas relevantes: FUN_CAT_0 (EF Total), MED_CAT_0 (EM Total).
    """
    print("\n=== INEP: Distorção Idade-Série (TDI) ===")
    for ano in anos:
        url = TDI_ZIP_URL.format(ano=ano)
        zip_bytes = download_zip(url)
        if zip_bytes is None:
            continue

        xlsx_bytes = extract_xlsx_from_zip(zip_bytes)
        if xlsx_bytes is None:
            continue

        df = read_inep_xlsx(xlsx_bytes, kind="tdi")
        if df is None or df.empty:
            print(f"  Ano {ano}: DataFrame vazio após leitura")
            continue

        print(f"  Ano {ano}: {len(df)} municípios, colunas disponíveis: {list(df.columns[:10])}")

        metricas = [
            ("FUN_CAT_0", "distorcao_idade_serie_ef"),
            ("MED_CAT_0", "distorcao_idade_serie_em"),
        ]

        rows = []
        for col, metrica in metricas:
            if col not in df.columns:
                print(f"    AVISO: coluna {col} não encontrada para {metrica}")
                continue
            for _, row in df.iterrows():
                try:
                    cod = int(float(str(row["CO_MUNICIPIO"]).strip()))
                except (ValueError, KeyError):
                    continue
                val = _safe_float(row[col])
                if val is not None:
                    rows.append((cod, metrica, ano, val))

        print(f"  Ano {ano}: {len(rows)} registros")
        upsert_metricas(rows, conn)


def main():
    parser = argparse.ArgumentParser(
        description="Carrega Censo Escolar INEP em api.metricas_municipio"
    )
    parser.add_argument(
        "--anos", nargs="+", type=int,
        default=list(range(2015, 2025)),
        help="Anos a carregar (padrão: 2015-2024)"
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
