"""
Carrega dados econômicos no PostGIS:
1. PIB municipal 2022 — IBGE SIDRA (tabela 5938, variável 37)
2. Receita municipal 2022 — Siconfi/RREO STN
3. Reconstrói vistas materializadas com homicídio via SIM (CID X85-Y09)

Correções aplicadas após leitura dos docs das APIs:
- IBGE SIDRA: separador de IDs múltiplos é vírgula (,), não pipe (|).
  N6[all] retorna todos os 5570 sem paginação.
- Siconfi RREO: os parâmetros no_conta / co_conta / no_coluna são ignorados
  pelo servidor — não filtram nada. A resposta sempre contém todos os
  registros do demonstrativo. O limite padrão é 5000, suficiente para o
  total máximo de ~4034 linhas por município. Filtro correto é local,
  sobre os campos `cod_conta` e `coluna`.
"""

import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2
from psycopg2.extras import execute_values

DB_PARAMS = dict(
    host=os.environ.get("POSTGRES_HOST", "localhost"),
    port=int(os.environ.get("POSTGRES_PORT", 5432)),
    database=os.environ.get("POSTGRES_DB", "brasil_dados"),
    user=os.environ.get("POSTGRES_USER", "brasil"),
    password=os.environ.get("POSTGRES_PASSWORD", ""),
)


def get_conn():
    return psycopg2.connect(**DB_PARAMS)


# ─── 1. PIB via IBGE SIDRA ────────────────────────────────────────────────────
# Docs: https://servicodados.ibge.gov.br/api/docs/agregados?versao=3
#
# Tabela 5938 — Produto Interno Bruto dos Municípios
# Variável 37 — PIB a preços correntes (Mil Reais)
# Nível N6 = municípios; N6[all] retorna todos os 5570
# Separador de IDs múltiplos: vírgula (,) — e.g. N6[3550308,3304557]
# Não há paginação: a resposta retorna array JSON com todos os resultados
# Sem Rate Limit documentado; boas práticas: evitar múltiplas chamadas simultâneas

def baixar_pib_ibge(ano: int) -> dict[int, float]:
    """
    Baixa PIB municipal para um ano via IBGE SIDRA tabela 5938 (variável 37).
    Retorna dict {cod_ibge_7: valor_reais}.
    Disponível de 2002 a ~2022 (IBGE publica com ~2 anos de atraso).
    """
    url = (
        f"https://servicodados.ibge.gov.br/api/v3/agregados/5938"
        f"/periodos/{ano}/variaveis/37?localidades=N6[all]"
    )
    print(f"  Baixando PIB municipal {ano} (IBGE SIDRA tabela 5938)...")
    try:
        resp = urllib.request.urlopen(url, timeout=60)
        data = json.loads(resp.read())
    except Exception as e:
        print(f"  AVISO: PIB {ano} indisponível ({e})")
        return {}

    series = data[0]["resultados"][0]["series"]
    pib_map = {}
    for s in series:
        cod_ibge = int(s["localidade"]["id"])   # 7 dígitos
        valor_str = s["serie"].get(str(ano))
        if valor_str and valor_str not in ("-", "...", "X"):
            pib_map[cod_ibge] = float(valor_str) * 1000  # Mil Reais → Reais
    print(f"    → {len(pib_map)}/{len(series)} municípios com PIB {ano}")
    return pib_map


# ─── 2. Receita via Siconfi RREO ─────────────────────────────────────────────
# Docs: https://apidatalake.tesouro.gov.br/ords/siconfi/metadata-catalog/
#       https://apidatalake.tesouro.gov.br/docs/siconfi/
#
# Endpoint: GET /ords/siconfi/tt/rreo
# Parâmetros:
#   an_exercicio  — ano do exercício (obrigatório)
#   nr_periodo    — número do período bimestral (1-6); 6 = 6º bimestre (acumulado anual)
#   co_tipo_demonstrativo — tipo: RREO, RGF, DCA etc. (obrigatório para filtrar)
#   id_ente       — código IBGE do município (obrigatório para filtrar por ente)
#   in_periodicidade — B=bimestral, S=semestral (opcional; RREO só tem B)
#   limit / offset — paginação (padrão limit=5000; máximo ~4034 linhas por ente)
#
# IMPORTANTE (descoberto empiricamente):
#   Os parâmetros no_conta, co_conta, no_coluna são IGNORADOS pelo servidor.
#   A resposta sempre contém todos os registros do demonstrativo para o ente/período.
#   Filtro deve ser feito localmente pelos campos `cod_conta` e `coluna`.
#
# Conta alvo: cod_conta = "ReceitasExcetoIntraOrcamentarias"
# Coluna alvo: coluna = "Até o Bimestre (c)"  → receita realizada acumulada no ano

SICONFI_BASE = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo"

# Parâmetros: an_exercicio é injetado dinamicamente por ano
SICONFI_PARAMS = "?an_exercicio={ano}&nr_periodo=6&co_tipo_demonstrativo=RREO&id_ente={cod_ibge}"

COD_CONTA_ALVO = "ReceitasExcetoIntraOrcamentarias"
COLUNA_ALVO    = "Até o Bimestre (c)"

# Gasto em saúde (LC 141/2012 — mínimo constitucional Saúde)
# Fonte: RREO Anexo 10 — Despesas com Ações e Serviços Públicos de Saúde
COD_CONTA_SAUDE  = "AplicacaoTotalDasDespesasComAcoesEServicosPublicosDeSaude"
COLUNA_SAUDE     = "Valor Apurado Até o Bimestre"

# Gasto em educação (CF art. 212 — mínimo constitucional MDE)
# Fonte: RREO Demonstrativo Simplificado — Mínimo Anual da Receita de Impostos na MDE
COD_CONTA_EDU    = "MinimoAnualDasReceitasDeImpostosNaManutencaoEDesenvolvimentoDoEnsinoDemonstrativoSimplificado"
COLUNA_EDU       = "Valor Apurado Até o Bimestre"


def _fetch_receita_municipio(cod_ibge: int, ano: int) -> tuple[int, float | None, float | None, float | None]:
    """Retorna (cod_ibge, receita_total, despesa_saude, despesa_educacao)."""
    url = SICONFI_BASE + SICONFI_PARAMS.format(ano=ano, cod_ibge=cod_ibge)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "brasil-em-dados/1.0"})
        resp = urllib.request.urlopen(req, timeout=20)
        data = json.loads(resp.read())
        items = data.get("items", [])

        receita = saude = educacao = None

        for item in items:
            cod = item.get("cod_conta", "")
            col = item.get("coluna", "")

            # Receita total
            if receita is None and cod == COD_CONTA_ALVO and col == COLUNA_ALVO:
                try: receita = float(item["valor"])
                except (TypeError, ValueError): pass

            # Despesa saúde (ASPS)
            if saude is None and cod == COD_CONTA_SAUDE and col == COLUNA_SAUDE:
                try: saude = float(item["valor"])
                except (TypeError, ValueError): pass

            # Despesa educação (MDE)
            if educacao is None and cod == COD_CONTA_EDU and col == COLUNA_EDU:
                try: educacao = float(item["valor"])
                except (TypeError, ValueError): pass

        # Fallback receita: nome completo da conta
        if receita is None:
            for item in items:
                conta = item.get("conta", "")
                if "EXCETO INTRA" in conta and item.get("coluna") == COLUNA_ALVO:
                    try: receita = float(item["valor"])
                    except (TypeError, ValueError): pass
                    break

        return cod_ibge, receita, saude, educacao
    except Exception:
        return cod_ibge, None, None, None


def baixar_receita_siconfi(
    cod_ibge_list: list[int], ano: int, workers: int = 40
) -> tuple[dict[int, float], dict[int, float], dict[int, float]]:
    """Retorna (receita_map, saude_map, educacao_map) em uma única passagem pela API."""
    print(f"  Baixando receita + despesas Siconfi RREO {ano} para {len(cod_ibge_list)} municípios...")
    receita_map: dict[int, float] = {}
    saude_map:   dict[int, float] = {}
    edu_map:     dict[int, float] = {}
    done = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_receita_municipio, cod, ano): cod for cod in cod_ibge_list}
        for future in as_completed(futures):
            cod_ibge, receita, saude, educacao = future.result()
            if receita   is not None: receita_map[cod_ibge] = receita
            if saude     is not None: saude_map[cod_ibge]   = saude
            if educacao  is not None: edu_map[cod_ibge]     = educacao
            done += 1
            if done % 500 == 0:
                elapsed = time.time() - t0
                print(f"    {done}/{len(cod_ibge_list)} ({elapsed:.0f}s)"
                      f" — receita={len(receita_map)} saude={len(saude_map)} edu={len(edu_map)}")

    print(f"    → receita={len(receita_map)} saude={len(saude_map)} edu={len(edu_map)}"
          f" / {len(cod_ibge_list)} municípios ({time.time()-t0:.0f}s)")
    return receita_map, saude_map, edu_map


# ─── 3. Inserção no PostGIS ───────────────────────────────────────────────────

def inserir_siconfi(pib_map: dict, receita_map: dict, ano: int,
                    saude_map: dict | None = None, edu_map: dict | None = None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT cod_ibge_7, cod_uf FROM geo.municipios ORDER BY cod_ibge_7")
            municipios = cur.fetchall()

            rows = []
            for cod_ibge_7, cod_uf in municipios:
                pib      = pib_map.get(cod_ibge_7)
                receita  = receita_map.get(cod_ibge_7)
                desp_s   = (saude_map  or {}).get(cod_ibge_7)
                desp_e   = (edu_map    or {}).get(cod_ibge_7)
                if pib is not None or receita is not None or desp_s is not None or desp_e is not None:
                    rows.append((cod_ibge_7, cod_uf, ano, receita, desp_s, desp_e, None, pib))

            execute_values(
                cur,
                """
                INSERT INTO economia.siconfi_municipios
                    (cod_municipio, cod_uf, ano, receita_total, despesa_saude,
                     despesa_educacao, transferencias_sus, pib)
                VALUES %s
                ON CONFLICT (cod_municipio, ano) DO UPDATE SET
                    receita_total      = EXCLUDED.receita_total,
                    pib                = EXCLUDED.pib,
                    despesa_saude      = EXCLUDED.despesa_saude,
                    despesa_educacao   = EXCLUDED.despesa_educacao,
                    transferencias_sus = EXCLUDED.transferencias_sus
                """,
                rows,
                page_size=1000,
            )
            conn.commit()
        n_rec = sum(1 for r in rows if r[3] is not None)
        n_pib = sum(1 for r in rows if r[7] is not None)
        n_sau = sum(1 for r in rows if r[4] is not None)
        n_edu = sum(1 for r in rows if r[5] is not None)
        print(f"  Upsert {ano} OK — receita={n_rec} pib={n_pib} saude={n_sau} edu={n_edu}")
    finally:
        conn.close()


# ─── 4. Recria vistas materializadas ─────────────────────────────────────────

SQL_DROP = """
DROP MATERIALIZED VIEW IF EXISTS api.indicadores_uf CASCADE;
DROP MATERIALIZED VIEW IF EXISTS api.indicadores_municipio CASCADE;
"""

SQL_MUN = """
CREATE MATERIALIZED VIEW api.indicadores_municipio AS
SELECT
    m.cod_ibge_7,
    m.cod_uf,
    m.nome                                          AS nome_municipio,
    m.geom,
    m.geom_simplified,
    m.area_km2,
    m.populacao_2022,
    COUNT(s.id) FILTER (WHERE s.ano = 2023)         AS obitos_2023,
    ROUND(
        COUNT(s.id) FILTER (WHERE s.ano = 2023)
        * 100000.0 / NULLIF(m.populacao_2022, 0), 1
    )                                               AS taxa_mortalidade_2023,
    COUNT(s.id) FILTER (
        WHERE s.ano = 2023 AND s.cid10_capitulo = 'I'
    )                                               AS obitos_cardiovascular_2023,
    -- Homicídios via SIM/DataSUS CID X85–X99 (agressão) + Y00–Y09 (outros meios)
    -- Metodologia do Atlas da Violência (IPEA/FBSP)
    COUNT(s.id) FILTER (
        WHERE s.ano = 2023
          AND s.cid10_codigo >= 'X85'
          AND s.cid10_codigo < 'Y1'
    )                                               AS homicidios_2023,
    ROUND(
        COUNT(s.id) FILTER (
            WHERE s.ano = 2023
              AND s.cid10_codigo >= 'X85'
              AND s.cid10_codigo < 'Y1'
        ) * 100000.0 / NULLIF(m.populacao_2022, 0), 1
    )                                               AS taxa_homicidio_2023,
    ROUND(
        COUNT(s.id) FILTER (WHERE s.ano = 2023 AND s.cid10_capitulo = 'I')
        * 100000.0 / NULLIF(m.populacao_2022, 0), 1
    )                                               AS mortalidade_cardiovascular_2023,
    ROUND(
        COUNT(s.id) FILTER (WHERE s.ano = 2023 AND s.cid10_capitulo = 'C')
        * 100000.0 / NULLIF(m.populacao_2022, 0), 1
    )                                               AS mortalidade_cancer_2023,
    ROUND(
        COUNT(s.id) FILTER (WHERE s.ano = 2023 AND s.cid10_capitulo = 'J')
        * 100000.0 / NULLIF(m.populacao_2022, 0), 1
    )                                               AS mortalidade_respiratoria_2023,
    e.receita_total                                 AS receita_municipal_2022,
    e.transferencias_sus                            AS transferencias_sus_2022,
    e.pib                                           AS pib_2022,
    ROUND(e.pib / NULLIF(m.populacao_2022, 0), 2)  AS pib_per_capita_2022,
    e.despesa_saude                                 AS despesa_saude_2022,
    e.despesa_educacao                              AS despesa_educacao_2022,
    ROUND(e.despesa_saude    / NULLIF(m.populacao_2022, 0), 2) AS despesa_saude_per_capita_2022,
    ROUND(e.despesa_educacao / NULLIF(m.populacao_2022, 0), 2) AS despesa_educacao_per_capita_2022
FROM geo.municipios m
LEFT JOIN saude.sim_mortalidade s
    ON m.cod_ibge_7 / 10 = s.cod_municipio
LEFT JOIN economia.siconfi_municipios e
    ON e.cod_municipio = m.cod_ibge_7 AND e.ano = 2022
GROUP BY m.cod_ibge_7, m.cod_uf, m.nome, m.geom, m.geom_simplified,
         m.area_km2, m.populacao_2022,
         e.receita_total, e.transferencias_sus, e.pib, e.despesa_saude, e.despesa_educacao;
"""

SQL_MUN_IDX = """
CREATE UNIQUE INDEX idx_indicadores_municipio_pk   ON api.indicadores_municipio (cod_ibge_7);
CREATE INDEX idx_indicadores_municipio_geom        ON api.indicadores_municipio USING GIST (geom);
CREATE INDEX idx_indicadores_municipio_geom_s      ON api.indicadores_municipio USING GIST (geom_simplified);
"""

SQL_UF = """
CREATE MATERIALIZED VIEW api.indicadores_uf AS
SELECT
    u.cod_uf,
    u.sigla,
    u.nome,
    u.regiao,
    u.geom,
    u.geom_simplified,
    u.area_km2,
    SUM(im.populacao_2022)                               AS populacao_total,
    ROUND(AVG(im.taxa_mortalidade_2023), 1)              AS taxa_mortalidade_media,
    ROUND(AVG(im.taxa_homicidio_2023), 1)                AS taxa_homicidio_media,
    ROUND(AVG(im.mortalidade_cardiovascular_2023), 1)    AS mortalidade_cardiovascular_media,
    ROUND(AVG(im.mortalidade_cancer_2023), 1)            AS mortalidade_cancer_media,
    ROUND(AVG(im.mortalidade_respiratoria_2023), 1)      AS mortalidade_respiratoria_media,
    SUM(im.receita_municipal_2022)                       AS receita_estadual_total,
    SUM(im.transferencias_sus_2022)                      AS transferencias_sus_total,
    SUM(im.pib_2022)                                     AS pib_estadual,
    SUM(im.despesa_saude_2022)                           AS despesa_saude_estadual_2022,
    SUM(im.despesa_educacao_2022)                        AS despesa_educacao_estadual_2022
FROM geo.ufs u
LEFT JOIN api.indicadores_municipio im ON im.cod_uf = u.cod_uf
GROUP BY u.cod_uf, u.sigla, u.nome, u.regiao, u.geom, u.geom_simplified, u.area_km2;
"""

SQL_UF_IDX = """
CREATE UNIQUE INDEX idx_indicadores_uf_pk   ON api.indicadores_uf (cod_uf);
CREATE INDEX idx_indicadores_uf_geom        ON api.indicadores_uf USING GIST (geom);
"""


def recriar_views():
    print("Recriando vistas materializadas...")
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(SQL_DROP)
            cur.execute(SQL_MUN);  print("  indicadores_municipio criada")
            cur.execute(SQL_MUN_IDX)
            cur.execute(SQL_UF);   print("  indicadores_uf criada")
            cur.execute(SQL_UF_IDX)
        conn.commit()
    finally:
        conn.close()


def verificar():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT e.ano,
                       COUNT(*) AS municipios,
                       COUNT(e.pib) AS com_pib,
                       COUNT(e.receita_total) AS com_receita,
                       ROUND(AVG(e.pib / NULLIF(m.populacao_2022, 0))::NUMERIC, 0)
                           AS avg_pib_per_capita
                FROM economia.siconfi_municipios e
                JOIN geo.municipios m ON m.cod_ibge_7 = e.cod_municipio
                GROUP BY e.ano ORDER BY e.ano
            """)
            print("\n=== Dados econômicos por ano ===")
            for r in cur.fetchall():
                print(f"  {r[0]}: {r[1]} municípios | PIB={r[2]} | receita={r[3]} | avg_pib_pc=R${r[4]}")
    finally:
        conn.close()


# ─── main ─────────────────────────────────────────────────────────────────────

# Anos disponíveis:
#   PIB IBGE SIDRA: 2002–2022 (publicação com ~2 anos de atraso; 2023 pode não estar disponível)
#   Siconfi RREO:   2015–2023
ANO_PIB_INICIO     = 2010
ANO_PIB_FIM        = 2022
ANO_SICONFI_INICIO = 2015
ANO_SICONFI_FIM    = 2023


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Carrega dados econômicos multi-ano")
    parser.add_argument("--anos-pib",     nargs="+", type=int,
                        default=list(range(ANO_PIB_INICIO, ANO_PIB_FIM + 1)),
                        help=f"Anos para PIB SIDRA (padrão: {ANO_PIB_INICIO}–{ANO_PIB_FIM})")
    parser.add_argument("--anos-siconfi", nargs="+", type=int,
                        default=list(range(ANO_SICONFI_INICIO, ANO_SICONFI_FIM + 1)),
                        help=f"Anos para Siconfi RREO (padrão: {ANO_SICONFI_INICIO}–{ANO_SICONFI_FIM})")
    parser.add_argument("--workers", type=int, default=40,
                        help="Workers paralelos para Siconfi (padrão: 40)")
    args = parser.parse_args()

    if not DB_PARAMS["password"]:
        try:
            for line in open("/home/sevan/Desktop/Codes/brasil_em_dados/.env"):
                if line.startswith("POSTGRES_PASSWORD="):
                    DB_PARAMS["password"] = line.strip().split("=", 1)[1]
        except Exception:
            pass

    t0 = time.time()

    # Lista de municípios (carregada uma vez)
    conn_tmp = get_conn()
    with conn_tmp.cursor() as cur:
        cur.execute("SELECT cod_ibge_7 FROM geo.municipios ORDER BY cod_ibge_7")
        cod_list = [r[0] for r in cur.fetchall()]
    conn_tmp.close()

    # PIB: anos sobrepostos entre PIB e Siconfi → usa union dos dois conjuntos de anos
    todos_anos = sorted(set(args.anos_pib) | set(args.anos_siconfi))
    print(f"Anos com PIB: {sorted(args.anos_pib)}")
    print(f"Anos com Siconfi: {sorted(args.anos_siconfi)}")
    print(f"Total de anos a processar: {todos_anos}\n")

    for ano in todos_anos:
        print(f"─── Ano {ano} ───")
        pib_map = baixar_pib_ibge(ano) if ano in args.anos_pib else {}

        receita_map, saude_map, edu_map = {}, {}, {}
        if ano in args.anos_siconfi:
            receita_map, saude_map, edu_map = baixar_receita_siconfi(
                cod_list, ano, workers=args.workers
            )

        if pib_map or receita_map or saude_map or edu_map:
            inserir_siconfi(pib_map, receita_map, ano, saude_map=saude_map, edu_map=edu_map)
        else:
            print(f"  Nenhum dado disponível para {ano}, pulando.")
        print()

    verificar()
    print(f"\nConcluído em {time.time()-t0:.0f}s")
