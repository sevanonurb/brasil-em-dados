#!/usr/bin/env python3
"""
Metadata API — Brasil em Dados
Expõe os anos disponíveis no banco para cada métrica do frontend.
GET /anos → {"taxa_mortalidade": [2023, 2022, ...], ...}
"""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

import psycopg2

DB = dict(
    host=os.environ.get("POSTGRES_HOST", "postgis"),
    port=int(os.environ.get("POSTGRES_PORT", 5432)),
    database=os.environ.get("POSTGRES_DB", "brasil_dados"),
    user=os.environ.get("POSTGRES_USER", "brasil"),
    password=os.environ.get("POSTGRES_PASSWORD", ""),
)

FALLBACK = {
    "taxa_mortalidade":            [2023],
    "taxa_homicidio":              [2023],
    "pib_per_capita":              [2022],
    "receita_per_capita":          [2022],
    "despesa_saude_per_capita":    [2022],
    "despesa_educacao_per_capita": [2022],
    "densidade_pop":               [2022],
    # Saneamento — Censo 2022 (estático)
    "acesso_agua":                 [2022],
    "acesso_esgoto":               [2022],
    "coleta_lixo":                 [2022],
    # Saúde — SINASC e CNES
    "taxa_natalidade":             [2023],
    "leitos_sus_por_1k":           [2023],
    "medicos_por_10k":             [2023],
    # Educação — IDEB (bienal)
    "ideb_anos_iniciais":          [2023],
    "ideb_anos_finais":            [2023],
    # Censo 2022 — Indicadores demográficos (estático)
    "taxa_envelhecimento":         [2022],
    "razao_sexo":                  [2022],
    "taxa_alfabetizacao":          [2022],
    "domicilios_internet":         [2022],
    "media_moradores":             [2022],
    "pop_favelas_pct":             [2022],
    # Censo 2022 Amostra — Renda e Trabalho (estático)
    "renda_domiciliar_per_capita": [2022],
    "renda_domiciliar_mediana_pc": [2022],
    "renda_media_trabalho":        [2022],
    "renda_mediana_trabalho":      [2022],
    # Censo 2022 Amostra — Educação (estático)
    "media_anos_estudo":           [2022],
    # Produção Agrícola Municipal (PAM — anual)
    "vbp_agricola_per_capita":     [2022],
    # Fiscal — Siconfi RGF (anual)
    "divida_rcl":                  [2022],
    "despesa_pessoal_rcl":         [2022],
}


def query_anos():
    conn = psycopg2.connect(**DB)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT ano FROM saude.sim_mortalidade ORDER BY ano DESC"
            )
            anos_sim = [r[0] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT ano FROM economia.siconfi_municipios ORDER BY ano DESC"
            )
            anos_ec = [r[0] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT ano FROM saude.sinasc_municipios ORDER BY ano DESC"
            )
            anos_sinasc = [r[0] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT ano FROM saude.cnes_municipios ORDER BY ano DESC"
            )
            anos_cnes = [r[0] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT ano FROM educacao.ideb_municipios ORDER BY ano DESC"
            )
            anos_ideb = [r[0] for r in cur.fetchall()]

            # Métricas adicionais: anos disponíveis por metrica em api.metricas_municipio
            cur.execute(
                "SELECT metrica, ARRAY_AGG(ano ORDER BY ano DESC) FROM ("
                "  SELECT DISTINCT metrica, ano FROM api.metricas_municipio"
                ") t GROUP BY metrica"
            )
            anos_metricas = {r[0]: r[1] for r in cur.fetchall()}
    finally:
        conn.close()

    return {
        "taxa_mortalidade":            anos_sim    or FALLBACK["taxa_mortalidade"],
        "taxa_homicidio":              anos_sim    or FALLBACK["taxa_homicidio"],
        "pib_per_capita":              anos_ec     or FALLBACK["pib_per_capita"],
        "receita_per_capita":          anos_ec     or FALLBACK["receita_per_capita"],
        "despesa_saude_per_capita":    anos_ec     or FALLBACK["despesa_saude_per_capita"],
        "despesa_educacao_per_capita": anos_ec     or FALLBACK["despesa_educacao_per_capita"],
        "densidade_pop":               [2022],
        # Saneamento — Censo 2022 (estático)
        "acesso_agua":                 [2022],
        "acesso_esgoto":               [2022],
        "coleta_lixo":                 [2022],
        # Saúde — SINASC e CNES
        "taxa_natalidade":             anos_sinasc or FALLBACK["taxa_natalidade"],
        "leitos_sus_por_1k":           anos_cnes   or FALLBACK["leitos_sus_por_1k"],
        "medicos_por_10k":             anos_cnes   or FALLBACK["medicos_por_10k"],
        # Educação — IDEB (bienal)
        "ideb_anos_iniciais":          anos_ideb   or FALLBACK["ideb_anos_iniciais"],
        "ideb_anos_finais":            anos_ideb   or FALLBACK["ideb_anos_finais"],
        # Censo 2022 — Indicadores demográficos (estático)
        "taxa_envelhecimento":         [2022],
        "razao_sexo":                  [2022],
        "taxa_alfabetizacao":          [2022],
        "domicilios_internet":         [2022],
        "media_moradores":             [2022],
        "pop_favelas_pct":             [2022],
        # Censo 2022 Amostra — Renda e Trabalho (estático)
        "renda_domiciliar_per_capita": [2022],
        "renda_domiciliar_mediana_pc": [2022],
        "renda_media_trabalho":        [2022],
        "renda_mediana_trabalho":      [2022],
        # Censo 2022 Amostra — Educação (estático)
        "media_anos_estudo":           [2022],
        # Produção Agrícola Municipal (PAM — anual, carregado via load_metricas_ibge.py)
        "vbp_agricola_per_capita":     anos_metricas.get("vbp_agricola_per_capita", [2022]),
        # Fiscal — Siconfi RGF (anual, carregado via load_metricas_rgf.py)
        "divida_rcl":                  anos_metricas.get("divida_rcl", [2022]),
        "despesa_pessoal_rcl":         anos_metricas.get("despesa_pessoal_rcl", [2022]),
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/anos", "/anos/"):
            try:
                data = query_anos()
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(exc)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):  # noqa: suppress access log
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    print(f"[brasil-api] listening on :{port}", flush=True)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
