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
    finally:
        conn.close()

    return {
        "taxa_mortalidade":            anos_sim or FALLBACK["taxa_mortalidade"],
        "taxa_homicidio":              anos_sim or FALLBACK["taxa_homicidio"],
        "pib_per_capita":              anos_ec  or FALLBACK["pib_per_capita"],
        "receita_per_capita":          anos_ec  or FALLBACK["receita_per_capita"],
        "despesa_saude_per_capita":    anos_ec  or FALLBACK["despesa_saude_per_capita"],
        "despesa_educacao_per_capita": anos_ec  or FALLBACK["despesa_educacao_per_capita"],
        "densidade_pop":               [2022],
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
