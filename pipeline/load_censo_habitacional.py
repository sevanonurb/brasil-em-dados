"""
load_censo_habitacional.py
Carrega indicadores de saneamento básico do Censo IBGE 2022 via SIDRA API v3.

Tabelas consultadas:
  6803 — Domicílios particulares permanentes por abastecimento de água (V381)
          classificação 1821: 72129=total, 72153=rede geral ausente
  6805 — Domicílios por tipo de esgotamento sanitário (V381)
          classificação 11558: 46290=rede geral de esgoto/pluvial (adequado)
  6892 — Domicílios por destino do lixo (V381)
          classificação 67: 2520=Coletado (limpeza + caçamba)

Resultado: censo.domicilios_municipio (cod_municipio 7 dígitos IBGE)
"""

import os
import time
import requests
import psycopg2
from psycopg2.extras import execute_values

DB_PARAMS = dict(
    host=os.environ.get("POSTGRES_HOST", "localhost"),
    port=int(os.environ.get("POSTGRES_PORT", 5432)),
    database=os.environ.get("POSTGRES_DB", "brasil_dados"),
    user=os.environ.get("POSTGRES_USER", "brasil"),
    password=os.environ.get("POSTGRES_PASSWORD", ""),
)

SIDRA_BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"


def sidra_get(tabela: int, classif: str, periodo: str = "2022") -> dict:
    """Retorna dicionário cod_municipio → valor (int) para todos os municípios."""
    url = (
        f"{SIDRA_BASE}/{tabela}/periodos/{periodo}/variaveis/381"
        f"?localidades=N6[all]&classificacao={classif}"
    )
    print(f"  GET {url}")
    for tentativa in range(3):
        r = requests.get(url, timeout=60)
        if r.status_code == 200:
            break
        print(f"  HTTP {r.status_code} — aguardando 10s...")
        time.sleep(10)
    else:
        print(f"  ERRO: tabela {tabela} / classif {classif} falhou após 3 tentativas")
        return {}

    resultado = {}
    for bloco in r.json():
        for resultado_item in bloco.get("resultados", []):
            for serie in resultado_item.get("series", []):
                cod = int(serie["localidade"]["id"])
                val_str = serie["serie"].get(periodo, "-")
                if val_str and val_str != "-":
                    try:
                        resultado[cod] = int(val_str)
                    except ValueError:
                        pass
    return resultado


def main():
    print("Carregando saneamento básico — Censo IBGE 2022...")

    # Tabela 6803: total de domicílios particulares permanentes
    print("6803 — total de domicílios...")
    total_dom = sidra_get(6803, "1821[72129]")  # 72129 = total

    # Tabela 6803: domicílios SEM ligação à rede geral de água
    # classificação 1821: 72153 = "Não tinham rede geral de distribuição"
    print("6803 — sem rede de água...")
    sem_agua = sidra_get(6803, "1821[72153]")
    com_agua = {cod: total_dom.get(cod, 0) - sem_agua.get(cod, 0)
                for cod in total_dom}

    # Tabela 6805: domicílios COM rede geral de esgoto (adequado)
    # classificação 11558: 46290 = "Rede geral ou pluvial"
    print("6805 — com rede de esgoto...")
    com_esgoto = sidra_get(6805, "11558[46290]")

    # Tabela 6892: domicílios COM lixo coletado (classificação 67, categoria 2520=Coletado)
    # classificação 67 = "Destino do lixo"; categoria 2520 engloba coleta domiciliar + caçamba
    print("6892 — com coleta de lixo...")
    com_lixo = sidra_get(6892, "67[2520]")

    municipios = set(total_dom) | set(com_agua) | set(com_esgoto) | set(com_lixo)
    print(f"Municípios encontrados: {len(municipios)}")

    rows = [
        (
            cod,
            total_dom.get(cod),
            com_agua.get(cod),
            com_esgoto.get(cod),
            com_lixo.get(cod),
        )
        for cod in sorted(municipios)
    ]

    conn = psycopg2.connect(**DB_PARAMS)
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE censo.domicilios_municipio")
            execute_values(
                cur,
                """
                INSERT INTO censo.domicilios_municipio
                    (cod_municipio, total_domicilios, com_agua_rede,
                     com_esgoto_rede, com_coleta_lixo)
                VALUES %s
                """,
                rows,
                page_size=1000,
            )
            print(f"Inseridos: {len(rows):,} municípios")
        conn.commit()
    finally:
        conn.close()

    print("Concluído.")


if __name__ == "__main__":
    main()
