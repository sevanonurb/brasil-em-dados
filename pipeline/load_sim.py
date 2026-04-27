"""
load_sim.py
Baixa e carrega dados do SIM/DataSUS (Sistema de Informações sobre Mortalidade)
para múltiplos anos, usando PySUS.

Uso:
    python load_sim.py                   # carrega 2015–2023, todos os estados
    python load_sim.py --anos 2020 2021  # apenas esses anos
    python load_sim.py --ufs SP RJ       # apenas esses estados

A tabela saude.sim_mortalidade é particionada por cod_uf e aceita INSERT
idempotente via ON CONFLICT DO NOTHING (chave: id, cod_uf, ano).
Para recarregar um ano limpo, passe --limpar-ano <ano>.
"""

import argparse
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2
import pandas as pd
from psycopg2.extras import execute_values
from pysus.online_data import SIM

# ─── Configuração ─────────────────────────────────────────────────────────────

UFS_BRASIL = [
    "AC","AL","AP","AM","BA","CE","DF","ES","GO",
    "MA","MT","MS","MG","PA","PB","PR","PE","PI",
    "RJ","RN","RS","RO","RR","SC","SP","SE","TO",
]

# Mapa sigla → cod_uf numérico (IBGE) — necessário para DELETE antes do INSERT
UF_COD = {
    "AC": 12, "AL": 27, "AP": 16, "AM": 13, "BA": 29, "CE": 23,
    "DF": 53, "ES": 32, "GO": 52, "MA": 21, "MT": 51, "MS": 50,
    "MG": 31, "PA": 15, "PB": 25, "PR": 41, "PE": 26, "PI": 22,
    "RJ": 33, "RN": 24, "RS": 43, "RO": 11, "RR": 14, "SC": 42,
    "SP": 35, "SE": 28, "TO": 17,
}

ANO_INICIO = 2015
ANO_FIM    = 2023

# Mapeamento DataSUS → faixa SIM (0–17)
# IDADE: código 4 = anos completos; campo IDADE = 4XX onde XX = anos
def idade_para_faixa(idade_raw) -> int | None:
    """
    Converte o campo IDADE do SIM (formato DataSUS) para faixa etária (0–17).

    Encoding DataSUS:
      000        = ignorado / não informado → None
      001–099    = horas (< 1 ano)         → faixa 0
      100–199    = dias  (< 1 ano)         → faixa 0
      200–299    = meses (< 1 ano)         → faixa 0
      300–399    = outros sub-anuais       → faixa 0
      400–499    = anos: 4XX − 400 = anos  → faixa correspondente
      500+       = 100+ anos: 5XX − 400    → faixa 17
    """
    try:
        v = int(idade_raw)
    except (ValueError, TypeError):
        return None

    if v == 0:    return None   # ignorado
    if v < 400:   return 0      # horas / dias / meses = < 1 ano

    anos = v - 400              # 400 → 0a, 401 → 1a, 487 → 87a, 500 → 100a
    if anos < 0:  return 0
    limites = [1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80]
    for i, lim in enumerate(limites):
        if anos < lim:
            return i
    return 17  # 80+


DB_PARAMS = dict(
    host=os.environ.get("POSTGRES_HOST", "localhost"),
    port=int(os.environ.get("POSTGRES_PORT", 5432)),
    database=os.environ.get("POSTGRES_DB", "brasil_dados"),
    user=os.environ.get("POSTGRES_USER", "brasil"),
    password=os.environ.get("POSTGRES_PASSWORD", ""),
)


def get_conn():
    return psycopg2.connect(**DB_PARAMS)


# ─── Processamento de um arquivo SIM ─────────────────────────────────────────

def processar_uf_ano(uf: str, ano: int) -> int:
    """
    Baixa os dados do SIM para uma UF/ano, transforma e insere no banco.
    Retorna número de registros inseridos.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            parquet_set = SIM.download("CID10", uf, ano, data_dir=tmpdir)
            df = parquet_set.to_dataframe()
        except Exception as e:
            print(f"  ERRO download {uf}/{ano}: {e}")
            return 0

    if df.empty:
        return 0

    # ── Normalização dos campos ───────────────────────────────────────────────
    # CODMUNRES: 6 dígitos DataSUS
    df["cod_municipio"] = pd.to_numeric(df.get("CODMUNRES", pd.Series(dtype="object")),
                                        errors="coerce")
    # UF: primeiros 2 dígitos do código do município
    df["cod_uf"] = (df["cod_municipio"] // 10000).astype("Int16")

    df["ano"] = ano
    df["mes"] = pd.to_numeric(df.get("DTOBITO", pd.Series(dtype="object"))
                              .astype(str).str[2:4], errors="coerce").astype("Int16")

    # CID-10
    df["cid10_codigo"]   = df.get("CAUSABAS", pd.Series(dtype="object")).astype(str).str.strip().str[:5]
    df["cid10_capitulo"] = df["cid10_codigo"].str[:1]

    # Faixa etária
    df["faixa_etaria"] = df.get("IDADE", pd.Series(dtype="object")).apply(idade_para_faixa)

    # Sexo: 1=Masculino, 2=Feminino (0/9/outros → NULL)
    # DataSUS usa código numérico; pysus às vezes entrega como string ou int.
    # Garante que apenas 1 e 2 são armazenados — outros valores viram NULL.
    _sexo_raw = pd.to_numeric(
        df.get("SEXO", pd.Series(dtype="object")), errors="coerce"
    ).astype("Int8")
    df["sexo"] = _sexo_raw.where(_sexo_raw.isin([1, 2]))

    # Cor/raça: 1=Branca, 2=Preta, 3=Amarela, 4=Parda, 5=Indígena
    df["cor_raca"] = pd.to_numeric(df.get("RACACOR", pd.Series(dtype="object")), errors="coerce").astype("Int8")

    # Escolaridade
    df["escolaridade"] = pd.to_numeric(df.get("ESC", pd.Series(dtype="object")), errors="coerce").astype("Int8")

    # Filtra linhas sem município ou CID-10 válido
    df = df.dropna(subset=["cod_municipio", "cid10_capitulo"])
    df = df[df["cod_municipio"] > 0]
    df = df[df["cid10_capitulo"].str.match(r"^[A-Z]$", na=False)]

    # ── Conversão de tipos para psycopg2 ──────────────────────────────────────
    # psycopg2 não aceita numpy/pandas Int16/Int8 nullable — converte para object
    for col in df.select_dtypes(include=["Int8","Int16","Int32","Int64"]).columns:
        df[col] = df[col].astype(object).where(df[col].notna(), None)

    rows = [
        (
            int(r.cod_municipio),
            int(r.cod_uf) if r.cod_uf is not None else None,
            ano,
            r.mes,
            r.cid10_capitulo,
            r.cid10_codigo[:5] if r.cid10_codigo else None,
            r.faixa_etaria,
            r.sexo,
            r.cor_raca,
            r.escolaridade,
        )
        for r in df.itertuples(index=False)
        if r.cod_uf is not None
    ]

    if not rows:
        return 0

    cod_uf_val = UF_COD.get(uf)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Remove dados existentes para este UF+ano antes de inserir
            # (garante idempotência: re-execuções não criam duplicatas)
            if cod_uf_val:
                cur.execute(
                    "DELETE FROM saude.sim_mortalidade WHERE cod_uf = %s AND ano = %s",
                    (cod_uf_val, ano),
                )
            execute_values(
                cur,
                """
                INSERT INTO saude.sim_mortalidade
                    (cod_municipio, cod_uf, ano, mes, cid10_capitulo,
                     cid10_codigo, faixa_etaria, sexo, cor_raca, escolaridade)
                VALUES %s
                """,
                rows,
                page_size=5000,
            )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Carrega SIM/DataSUS multi-ano")
    parser.add_argument("--anos", nargs="+", type=int,
                        default=list(range(ANO_INICIO, ANO_FIM + 1)),
                        help=f"Anos a carregar (padrão: {ANO_INICIO}–{ANO_FIM})")
    parser.add_argument("--ufs", nargs="+", default=UFS_BRASIL,
                        help="Siglas de UF a carregar (padrão: todas)")
    parser.add_argument("--limpar-ano", type=int, default=None,
                        help="Apaga todos os registros desse ano antes de recarregar")
    parser.add_argument("--workers", type=int, default=4,
                        help="Número de downloads paralelos (padrão: 4)")
    args = parser.parse_args()

    anos = sorted(args.anos)
    ufs  = [u.upper() for u in args.ufs]
    tarefas = [(uf, ano) for ano in anos for uf in ufs]

    print(f"Carregando SIM CID-10: {len(tarefas)} combinações "
          f"({len(ufs)} UFs × {len(anos)} anos: {anos[0]}–{anos[-1]})")
    print(f"Workers paralelos: {args.workers}")

    if args.limpar_ano:
        print(f"Limpando ano {args.limpar_ano} antes de recarregar...")
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM saude.sim_mortalidade WHERE ano = %s", (args.limpar_ano,))
            print(f"  {cur.rowcount:,} registros removidos")
        conn.commit()
        conn.close()

    total = 0
    erros = []
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(processar_uf_ano, uf, ano): (uf, ano)
                   for uf, ano in tarefas}
        done = 0
        for future in as_completed(futures):
            uf, ano = futures[future]
            try:
                n = future.result()
                total += n
            except Exception as e:
                erros.append((uf, ano, str(e)))
                n = 0
            done += 1
            elapsed = time.time() - t0
            print(f"  [{done:3d}/{len(tarefas)}] {uf}/{ano}: {n:,} registros "
                  f"| total={total:,} | {elapsed:.0f}s")

    print(f"\n{'='*60}")
    print(f"Concluído: {total:,} registros inseridos em {time.time()-t0:.0f}s")
    if erros:
        print(f"Erros ({len(erros)}):")
        for uf, ano, msg in erros:
            print(f"  {uf}/{ano}: {msg}")

    # Sanidade
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT ano, COUNT(*) FROM saude.sim_mortalidade GROUP BY ano ORDER BY ano")
        print("\nRegistros por ano no banco:")
        for row in cur.fetchall():
            print(f"  {row[0]}: {row[1]:,}")
    conn.close()


if __name__ == "__main__":
    # Tenta ler POSTGRES_PASSWORD do .env se não estiver no ambiente
    if not DB_PARAMS["password"]:
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
        try:
            for line in open(env_path):
                if line.startswith("POSTGRES_PASSWORD="):
                    DB_PARAMS["password"] = line.strip().split("=", 1)[1]
        except FileNotFoundError:
            pass

    main()
