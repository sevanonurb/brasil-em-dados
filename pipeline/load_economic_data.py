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
import pathlib
import threading
import time
import urllib.error
import urllib.parse
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
# CORREÇÃO (23/10/2026) — medida, não suposta:
#   1. Município com menos de 50 mil habitantes pode entregar o "RREO Simplificado" (LRF art. 63).
#      Pedir só co_tipo_demonstrativo=RREO devolvia 0 itens para eles: em 2023 só 3.253 de 5.570
#      municípios tinham receita. Numa amostra de 20 dos faltantes, 20/20 tinham o Simplificado.
#   2. Saúde e educação liam a linha de "mínimo constitucional" (anexos 12/8 e 14), que deixou de
#      vir no RREO e, onde vinha, era diferença ou percentual: 321 valores < R$ 1.000 (vários
#      negativos) e 193 acima de 60% da receita. Agora: despesa LIQUIDADA por FUNÇÃO no Anexo 02
#      (função 10 Saúde, 12 Educação), exceto intra-orçamentárias — presente nos dois tipos e em
#      todos os anos testados (2015, 2019, 2023).
#   3. Erro de rede/limite virava "sem dado" em silêncio (except: return None). Agora há nova
#      tentativa com espera, e o resultado distingue "vazio na fonte" de "erro".
#
# Receita: Anexo 01, cod_conta "ReceitasExcetoIntraOrcamentarias", coluna "Até o Bimestre (c)".

SICONFI_BASE = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo"
TIPOS_RREO = ("RREO", "RREO Simplificado")

COD_CONTA_ALVO = "ReceitasExcetoIntraOrcamentarias"
COLUNA_ALVO    = "Até o Bimestre (c)"
CONTA_FUNCAO   = "RREO2TotalDespesas"                       # exceto intra-orçamentárias
COLUNA_FUNCAO  = "DESPESAS LIQUIDADAS ATÉ O BIMESTRE (d)"


class _Ritmo:
    """Limite de requisições COMPARTILHADO entre threads. Medido em 23/10/2026: em sequência, 2 req/s
    passam sem erro; 10 threads livres levam HTTP 429 em 54 de 60 — o loader antigo usava 40 e
    transformava o 429 em "sem dado". No 429 a pausa vale para todas as threads."""
    def __init__(self, por_segundo: float = 1.8):
        self.intervalo, self.proximo, self.trava = 1 / por_segundo, 0.0, threading.Lock()

    def esperar(self):
        with self.trava:
            agora = time.monotonic()
            vez = max(agora, self.proximo)
            self.proximo = vez + self.intervalo
        time.sleep(max(0.0, vez - agora))

    def punir(self, segundos: float):
        with self.trava:
            self.proximo = max(self.proximo, time.monotonic() + segundos)


RITMO = _Ritmo()


def _anexo(cod_ibge: int, ano: int, tipo: str, anexo: str, tentativas: int = 8) -> list:
    q = urllib.parse.urlencode({"an_exercicio": ano, "nr_periodo": 6, "co_tipo_demonstrativo": tipo,
                                "no_anexo": anexo, "id_ente": cod_ibge})
    for t in range(tentativas):
        RITMO.esperar()
        try:
            req = urllib.request.Request(f"{SICONFI_BASE}?{q}", headers={"User-Agent": "brasil-em-dados/1.0"})
            return json.loads(urllib.request.urlopen(req, timeout=90).read()).get("items", [])
        except urllib.error.HTTPError as e:
            if t == tentativas - 1:
                raise
            if e.code == 429:
                RITMO.punir(30 * (t + 1))
            else:
                time.sleep(2 ** t)
        except Exception:
            if t == tentativas - 1:
                raise
            time.sleep(2 ** t)


def _fetch_receita_municipio(cod_ibge: int, ano: int, tipo_primeiro: str = "RREO"):
    """Retorna (cod_ibge, receita, saude, educacao, tipo_usado | None, erro | None)."""
    tipos = (tipo_primeiro,) + tuple(t for t in TIPOS_RREO if t != tipo_primeiro)
    try:
        for tipo in tipos:
            a1 = _anexo(cod_ibge, ano, tipo, "RREO-Anexo 01")
            if not a1:
                continue
            a2 = _anexo(cod_ibge, ano, tipo, "RREO-Anexo 02")
            receita = next((float(i["valor"]) for i in a1
                            if i.get("cod_conta") == COD_CONTA_ALVO and i.get("coluna") == COLUNA_ALVO
                            and i.get("valor") is not None), None)
            funcao = {i["conta"]: float(i["valor"]) for i in a2
                      if i.get("cod_conta") == CONTA_FUNCAO and i.get("coluna") == COLUNA_FUNCAO
                      and i.get("conta") in ("Saúde", "Educação") and i.get("valor") is not None}
            return cod_ibge, receita, funcao.get("Saúde"), funcao.get("Educação"), tipo, None
        return cod_ibge, None, None, None, None, None          # vazio nos dois tipos: lacuna da fonte
    except Exception as e:
        return cod_ibge, None, None, None, None, f"{type(e).__name__}: {e}"[:120]


def baixar_receita_siconfi(cod_ibge_list: list[int], ano: int, workers: int = 4,
                           tipo_primeiro: dict[int, str] | None = None, ao_receber=None):
    """Retorna (receita_map, saude_map, educacao_map, erros). tipo_primeiro: palpite por município
    (o tipo que ele entregou antes), só para economizar uma requisição."""
    print(f"  Siconfi RREO {ano}: {len(cod_ibge_list)} municípios...", flush=True)
    receita_map, saude_map, edu_map, erros = {}, {}, {}, {}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_fetch_receita_municipio, c, ano, (tipo_primeiro or {}).get(c, "RREO"))
                for c in cod_ibge_list]
        for n, fut in enumerate(as_completed(futs), 1):
            cod, receita, saude, edu, _tipo, erro = fut.result()
            if ao_receber:
                ao_receber(cod, receita, saude, edu, erro)
            if receita is not None: receita_map[cod] = receita
            if saude is not None:   saude_map[cod] = saude
            if edu is not None:     edu_map[cod] = edu
            if erro:                erros[cod] = erro
            if n % 500 == 0:
                print(f"    {n}/{len(cod_ibge_list)} ({time.time()-t0:.0f}s) receita={len(receita_map)} "
                      f"saude={len(saude_map)} edu={len(edu_map)} erros={len(erros)}", flush=True)
    print(f"    → receita={len(receita_map)} saude={len(saude_map)} edu={len(edu_map)} erros={len(erros)}"
          f" / {len(cod_ibge_list)} ({time.time()-t0:.0f}s)", flush=True)
    return receita_map, saude_map, edu_map, erros


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
                    pib                = COALESCE(EXCLUDED.pib, economia.siconfi_municipios.pib),
                    despesa_saude      = EXCLUDED.despesa_saude,
                    despesa_educacao   = EXCLUDED.despesa_educacao,
                    -- este loader não baixa transferências nem (em todo ano) PIB: NULL não pode apagar o que há
                    transferencias_sus = COALESCE(EXCLUDED.transferencias_sus, economia.siconfi_municipios.transferencias_sus)
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
            env = pathlib.Path(__file__).resolve().parent.parent / ".env"
            for line in open(env):
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
            receita_map, saude_map, edu_map, erros = baixar_receita_siconfi(
                cod_list, ano, workers=args.workers
            )
            if erros:
                print(f"  ⚠ {len(erros)} municípios com erro de rede (não é lacuna da fonte): rode de novo")

        if pib_map or receita_map or saude_map or edu_map:
            inserir_siconfi(pib_map, receita_map, ano, saude_map=saude_map, edu_map=edu_map)
        else:
            print(f"  Nenhum dado disponível para {ano}, pulando.")
        print()

    verificar()
    print(f"\nConcluído em {time.time()-t0:.0f}s")
