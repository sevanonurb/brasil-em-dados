"""
load_populacao_demografica.py
Carrega o breakdown demográfico do IBGE Censo 2022 (via SIDRA) para as tabelas:
  - censo.populacao_raca_municipio   (cor/raça × município)
  - censo.populacao_faixa_municipio  (faixa etária × município)

Esses dados são usados como denominadores corretos nas taxas de mortalidade
quando o painel filtra por raça ou faixa etária — evita a distorção de usar
a população total como base para um subgrupo demográfico específico.

Fontes SIDRA:
  - Tabela 9605 (raça):  https://sidra.ibge.gov.br/tabela/9605
  - Tabela 9514 (idade): https://sidra.ibge.gov.br/tabela/9514
"""

import os
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2
import requests
from psycopg2.extras import execute_values

SIDRA_BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"

# ─── Mapeamentos ─────────────────────────────────────────────────────────────

# SIDRA categoria_id (tabela 9605) → cor_raca (código SIM/DataSUS)
RACA_CAT_MAP = {
    "2776": 1,  # Branca
    "2777": 2,  # Preta
    "2778": 3,  # Amarela
    "2779": 4,  # Parda
    "2780": 5,  # Indígena
}
RACA_CATS = ",".join(RACA_CAT_MAP.keys())

# SIDRA categoria_id (tabela 9514) → faixa_etaria (encoding SIM 0-17)
# Faixas com mapeamento 1:1
FAIXA_SINGLE = {
    "6557":  0,   # Menos de 1 ano
    "93084": 2,   # 5 a 9 anos
    "93085": 3,   # 10 a 14 anos
    "93086": 4,   # 15 a 19 anos
    "93087": 5,   # 20 a 24 anos
    "93088": 6,   # 25 a 29 anos
    "93089": 7,   # 30 a 34 anos
    "93090": 8,   # 35 a 39 anos
    "93091": 9,   # 40 a 44 anos
    "93092": 10,  # 45 a 49 anos
    "93093": 11,  # 50 a 54 anos
    "93094": 12,  # 55 a 59 anos
    "93095": 13,  # 60 a 64 anos
    "93096": 14,  # 65 a 69 anos
    "93097": 15,  # 70 a 74 anos
    "93098": 16,  # 75 a 79 anos
}
# Faixa 1 (1–4 anos): soma dos anos individuais (SIDRA não tem grupo 1-4 pronto)
FAIXA1_CATS = ["6558", "6559", "6560", "6561"]   # 1, 2, 3, 4 anos
# Faixa 17 (80+): soma de todos os grupos 80+
FAIXA17_CATS = ["49108", "49109", "60040", "60041", "6653"]  # 80-84, 85-89, 90-94, 95-99, 100+

ALL_FAIXA_CATS = ",".join(list(FAIXA_SINGLE.keys()) + FAIXA1_CATS + FAIXA17_CATS)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def sidra_get(url: str, retries: int = 4) -> list:
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == retries - 1:
                raise RuntimeError(f"SIDRA falhou após {retries} tentativas: {e}\nURL: {url}") from e
            wait = 2 ** attempt
            print(f"  Tentativa {attempt + 1} falhou ({e}), aguardando {wait}s...")
            time.sleep(wait)


def get_db_conn():
    return psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        database=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def parse_pop(valor: str) -> int | None:
    """Converte string do SIDRA para inteiro; retorna None para '-' ou vazio."""
    if not valor or valor.strip() in ("-", "...", "X"):
        return None
    try:
        return int(valor.replace(".", "").replace(",", ""))
    except ValueError:
        return None


# ─── Carga de Raça ───────────────────────────────────────────────────────────

def load_raca() -> list[tuple]:
    """
    Busca população por cor/raça × município (tabela SIDRA 9605).
    Uma única chamada N6[all] → ~5570 municípios × 5 raças.
    """
    url = (
        f"{SIDRA_BASE}/9605/periodos/2022/variaveis/93"
        f"?localidades=N6[all]&classificacao=86[{RACA_CATS}]"
    )
    print("Buscando população por raça (tabela SIDRA 9605)...")
    data = sidra_get(url)

    rows = []
    for item in data:
        for resultado in item.get("resultados", []):
            # Extrai cat_id da raça neste resultado
            classif_86 = next(
                (c for c in resultado.get("classificacoes", []) if c.get("id") == "86"),
                None
            )
            if not classif_86:
                continue
            cat_id = next(iter(classif_86.get("categoria", {}).keys()), None)
            cor_raca = RACA_CAT_MAP.get(cat_id)
            if cor_raca is None:
                continue

            for serie in resultado.get("series", []):
                loc_id = serie.get("localidade", {}).get("id")
                val = parse_pop(serie.get("serie", {}).get("2022", ""))
                if loc_id and val is not None:
                    try:
                        rows.append((int(loc_id), cor_raca, val))
                    except ValueError:
                        pass

    print(f"  → {len(rows):,} registros (raça × município)")
    return rows


# ─── Carga de Faixa Etária ───────────────────────────────────────────────────

def _fetch_single_age_cat(cat_id: str) -> tuple[str, dict[int, int]]:
    """
    Busca população de UMA categoria de idade para todos os municípios.
    SIDRA retorna 500 se passarmos N6[all] + múltiplas categorias na tabela 9514,
    mas aceita uma categoria por vez.
    """
    url = (
        f"{SIDRA_BASE}/9514/periodos/2022/variaveis/93"
        f"?localidades=N6[all]&classificacao=287[{cat_id}]"
    )
    data = sidra_get(url)
    result: dict[int, int] = {}
    for item in data:
        for resultado in item.get("resultados", []):
            for serie in resultado.get("series", []):
                loc_id = serie.get("localidade", {}).get("id")
                val = parse_pop(serie.get("serie", {}).get("2022", ""))
                if loc_id and val is not None:
                    try:
                        result[int(loc_id)] = val
                    except ValueError:
                        pass
    return cat_id, result


def load_faixa() -> list[tuple]:
    """
    Busca população por idade × município (tabela SIDRA 9514).
    Faz uma chamada por categoria (N6[all] + múltiplas categorias retorna 500),
    paralelizando com 5 workers. Agrega nas 18 faixas do SIM.
    """
    all_cat_ids = list(FAIXA_SINGLE.keys()) + FAIXA1_CATS + FAIXA17_CATS
    n = len(all_cat_ids)
    print(f"Buscando população por faixa etária (tabela SIDRA 9514, {n} chamadas paralelas)...")

    by_mun: dict[int, dict[str, int]] = {}

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_fetch_single_age_cat, cat_id): cat_id for cat_id in all_cat_ids}
        done = 0
        for future in as_completed(futures):
            cat_id, mun_pop = future.result()
            done += 1
            print(f"  [{done}/{n}] cat {cat_id}: {len(mun_pop):,} municípios")
            for cod_mun, pop in mun_pop.items():
                by_mun.setdefault(cod_mun, {})[cat_id] = pop

    rows = []
    for cod_mun, cats in by_mun.items():
        # Faixas simples 1:1
        for cat_id, faixa in FAIXA_SINGLE.items():
            pop = cats.get(cat_id)
            if pop is not None:
                rows.append((cod_mun, faixa, pop))

        # Faixa 1 (1–4 anos): soma dos anos individuais 1, 2, 3, 4
        pop_faixa1 = sum(cats.get(c, 0) for c in FAIXA1_CATS)
        if pop_faixa1 > 0:
            rows.append((cod_mun, 1, pop_faixa1))

        # Faixa 17 (80+): soma de todos os grupos 80–84, 85–89, 90–94, 95–99, 100+
        pop_faixa17 = sum(cats.get(c, 0) for c in FAIXA17_CATS)
        if pop_faixa17 > 0:
            rows.append((cod_mun, 17, pop_faixa17))

    print(f"  → {len(rows):,} registros (faixa × município)")
    return rows


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    rows_raca  = load_raca()
    rows_faixa = load_faixa()

    print("Conectando ao banco...")
    conn = get_db_conn()

    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE censo.populacao_raca_municipio")
            execute_values(
                cur,
                "INSERT INTO censo.populacao_raca_municipio (cod_municipio, cor_raca, populacao) VALUES %s",
                rows_raca,
                page_size=5000,
            )
            print(f"  ✓ {len(rows_raca):,} linhas inseridas em censo.populacao_raca_municipio")

            cur.execute("TRUNCATE censo.populacao_faixa_municipio")
            execute_values(
                cur,
                "INSERT INTO censo.populacao_faixa_municipio (cod_municipio, faixa_etaria, populacao) VALUES %s",
                rows_faixa,
                page_size=5000,
            )
            print(f"  ✓ {len(rows_faixa):,} linhas inseridas em censo.populacao_faixa_municipio")

        conn.commit()

        # Sanidade: verifica São Paulo (7 dígitos = 3550308)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT cor_raca, populacao FROM censo.populacao_raca_municipio
                WHERE cod_municipio = 3550308 ORDER BY cor_raca
            """)
            print("\nSanidade SP (raça):")
            nomes = {1:'Branca', 2:'Preta', 3:'Amarela', 4:'Parda', 5:'Indígena'}
            for row in cur.fetchall():
                print(f"  {nomes.get(row[0], row[0])}: {row[1]:,}")

            cur.execute("""
                SELECT faixa_etaria, populacao FROM censo.populacao_faixa_municipio
                WHERE cod_municipio = 3550308 ORDER BY faixa_etaria
            """)
            print("\nSanidade SP (faixa etária, primeiras 5):")
            faixas = ["<1a","1-4a","5-9a","10-14a","15-19a","20-24a","25-29a","30-34a",
                      "35-39a","40-44a","45-49a","50-54a","55-59a","60-64a","65-69a","70-74a","75-79a","80+"]
            for row in cur.fetchall()[:5]:
                print(f"  faixa {row[0]} ({faixas[row[0]]}): {row[1]:,}")

    finally:
        conn.close()

    print("\nConcluído com sucesso.")


if __name__ == "__main__":
    main()
