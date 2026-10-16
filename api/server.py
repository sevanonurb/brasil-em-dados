#!/usr/bin/env python3
"""
Metadata API — Brasil em Dados
Expõe os anos disponíveis no banco para cada métrica do frontend.
GET /anos → {"taxa_mortalidade": [2023, 2022, ...], ...}
"""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
    "densidade_domiciliar":        [2022],
    "populacao_absoluta":          [2022],
    "domicilios_absoluto":         [2022],
    "area_territorial":            [2022],
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
    # Mortalidade Infantil — Registro Civil IBGE (anual)
    "mortalidade_infantil":        [2023],
    # Censo 2022 Amostra — Trabalho (estático)
    "taxa_ocupacao":               [2022],
    # Censo 2022 Amostra — Educação (estático)
    "media_anos_estudo":           [2022],
    "pct_superior_completo":       [2022],
    "taxa_deficiencia":            [2022],
    # Censo 2022 — Demográficos adicionais (estático)
    "idade_mediana":               [2022],
    # PIB setorial — T5938 (anual, defasagem ~2 anos)
    "pct_pib_agropecuaria":        [2021],
    "pct_pib_industria":           [2021],
    "pct_pib_servicos":            [2021],
    # Produção Agrícola Municipal (PAM — anual)
    "vbp_agricola_per_capita":     [2023],
    # Pecuária Municipal (T74 — anual)
    "vbp_pecuaria_per_capita":     [2023],
    # Fiscal — Siconfi RGF (anual)
    "divida_rcl":                  [2022],
    "despesa_pessoal_rcl":         [2022],
    # Censo 2022 — Raça/Etnia (estático)
    "pct_indigena":                [2022],
    "pct_quilombola":              [2022],
    # Censo Agropecuário 2017 (estático)
    "pct_agrofamiliar":            [2017],
    "pct_mecanizado":              [2017],
    "pct_financiamento":           [2017],
    # CEMPRE — empresas por mil hab. (anual)
    "empresas_por_1k":             [2023],
    # Censo 2022 — Migração e Escolarização (estático)
    "taxa_migracao":               [2022],
    "taxa_escolarizacao_1517":     [2022],
    # Censo 2022 — Mercado de Trabalho (estático)
    "taxa_desemprego":             [2022],
    "taxa_pendular":               [2022],
    "taxa_informalidade":          [2022],
    # Censo 2022 — Renda e Pobreza (estático)
    "pct_baixa_renda":             [2022],
    "pct_renda_trabalho":          [2022],
    # Censo 2022 — Domicílios e Habitação (estático)
    "pct_chefia_feminina":         [2022],
    "domicilios_maquina_lavar":    [2022],
    "superlotacao_domiciliar":     [2022],
    "domicilios_alugados":         [2022],
    "domicilios_monoparentais":    [2022],
    # Censo 2022 — Fecundidade (estático)
    "media_filhos_mulher":         [2022],
    # Censo 2022 — Urbanização e Qualidade Habitacional (estático)
    "pct_urbano":                  [2022],
    "pct_alvenaria":               [2022],
    "pct_banheiro_exclusivo":      [2022],
    # Registro Civil — Nupcialidade e Divorcialidade (dados carregados: 2023)
    "taxa_nupcialidade":           [2023],
    "taxa_divorcialidade":         [2023],
    # PPM — Rebanhos (anual)
    "rebanho_bovino_por_km2":      [2023, 2022, 2021, 2020, 2019],
    "rebanho_bovino_por_hab":      [2023, 2022, 2021, 2020, 2019],
    "rebanho_equino_por_hab":      [2023, 2022, 2021, 2020, 2019],
    "rebanho_suino_por_hab":       [2023, 2022, 2021, 2020, 2019],
    "rebanho_ovino_por_hab":       [2023, 2022, 2021, 2020, 2019],
    "rebanho_caprino_por_hab":     [2023, 2022, 2021, 2020, 2019],
    "rebanho_galinaceos_por_hab":  [2023, 2022, 2021, 2020, 2019],
    # SINAN — Epidemiologia (anual)
    "incidencia_dengue":           [2023, 2022, 2021, 2020, 2019],
    "incidencia_tuberculose":      [2023, 2022, 2021, 2020, 2019],
    "incidencia_hanseniase":       [2023, 2022, 2021, 2020, 2019],
    "incidencia_leishmaniose":     [2023, 2022, 2021, 2020, 2019],
    # SIH — Internações SUS (anual)
    "taxa_internacao_sus":              [2023, 2022, 2021, 2020, 2019],
    "taxa_internacao_cardiovascular":   [2023, 2022, 2021, 2020, 2019],
    "taxa_internacao_respiratoria":     [2023, 2022, 2021, 2020, 2019],
    "taxa_internacao_mental":           [2023, 2022, 2021, 2020, 2019],
    "media_permanencia_sus":            [2023, 2022, 2021, 2020, 2019],
    # Censo Escolar INEP — Rendimento (anual)
    "taxa_aprovacao_ef":           [2024, 2023, 2022, 2021, 2020],
    "taxa_reprovacao_ef":          [2024, 2023, 2022, 2021, 2020],
    "taxa_abandono_ef":            [2024, 2023, 2022, 2021, 2020],
    "taxa_aprovacao_em":           [2024, 2023, 2022, 2021, 2020],
    "taxa_abandono_em":            [2024, 2023, 2022, 2021, 2020],
    "distorcao_idade_serie_ef":    [2024, 2023, 2022, 2021, 2020],
    "distorcao_idade_serie_em":    [2024, 2023, 2022, 2021, 2020],
    # SENATRAN — Frota Veicular (dados carregados: 2020-2022)
    "frota_automovel_por_1k":      [2022, 2021, 2020],
    "frota_moto_por_1k":           [2022, 2021, 2020],
    "frota_caminhao_por_1k":       [2022, 2021, 2020],
    "frota_onibus_por_1k":         [2022, 2021, 2020],
    "frota_total_por_1k":          [2022, 2021, 2020],
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
        "densidade_domiciliar":        [2022],
        "populacao_absoluta":          [2022],
        "domicilios_absoluto":         [2022],
        "area_territorial":            [2022],
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
        # Mortalidade Infantil — Registro Civil IBGE (anual)
        "mortalidade_infantil":        anos_metricas.get("mortalidade_infantil", [2023]),
        # Censo 2022 Amostra — Trabalho (estático)
        "taxa_ocupacao":               anos_metricas.get("taxa_ocupacao", [2022]),
        # Censo 2022 Amostra — Educação (estático)
        "media_anos_estudo":           [2022],
        "pct_superior_completo":       [2022],
        "taxa_deficiencia":            [2022],
        # Censo 2022 — Demográficos adicionais (estático)
        "idade_mediana":               anos_metricas.get("idade_mediana", [2022]),
        # PIB setorial — T5938 (anual, defasagem ~2 anos)
        "pct_pib_agropecuaria":        anos_metricas.get("pct_pib_agropecuaria", [2021]),
        "pct_pib_industria":           anos_metricas.get("pct_pib_industria", [2021]),
        "pct_pib_servicos":            anos_metricas.get("pct_pib_servicos", [2021]),
        # Produção Agrícola Municipal (PAM — anual, carregado via load_metricas_ibge.py)
        "vbp_agricola_per_capita":     anos_metricas.get("vbp_agricola_per_capita", [2023]),
        # Pecuária Municipal (T74 — anual)
        "vbp_pecuaria_per_capita":     anos_metricas.get("vbp_pecuaria_per_capita", [2023]),
        # Fiscal — Siconfi RGF (anual, carregado via load_metricas_rgf.py)
        "divida_rcl":                  anos_metricas.get("divida_rcl", [2022]),
        "despesa_pessoal_rcl":         anos_metricas.get("despesa_pessoal_rcl", [2022]),
        # Censo 2022 — Raça/Etnia (estático)
        "pct_indigena":                [2022],
        "pct_quilombola":              [2022],
        # Censo Agropecuário 2017 (estático)
        "pct_agrofamiliar":            [2017],
        "pct_mecanizado":              [2017],
        "pct_financiamento":           [2017],
        # CEMPRE — Cadastro Central de Empresas (anual)
        "empresas_por_1k":             anos_metricas.get("empresas_por_1k", [2023]),
        # Censo 2022 — Migração e Escolarização (estático)
        "taxa_migracao":               [2022],
        "taxa_escolarizacao_1517":     [2022],
        # Censo 2022 — Mercado de Trabalho (estático)
        "taxa_desemprego":             [2022],
        "taxa_pendular":               [2022],
        "taxa_informalidade":          [2022],
        # Censo 2022 — Renda e Pobreza (estático)
        "pct_baixa_renda":             [2022],
        "pct_renda_trabalho":          [2022],
        # Censo 2022 — Domicílios e Habitação (estático)
        "pct_chefia_feminina":         [2022],
        "domicilios_maquina_lavar":    [2022],
        "superlotacao_domiciliar":     [2022],
        "domicilios_alugados":         [2022],
        "domicilios_monoparentais":    [2022],
        # Censo 2022 — Fecundidade (estático)
        "media_filhos_mulher":         [2022],
        # Censo 2022 — Urbanização e Qualidade Habitacional (estático)
        "pct_urbano":                  [2022],
        "pct_alvenaria":               [2022],
        "pct_banheiro_exclusivo":      [2022],
        # Registro Civil — Nupcialidade e Divorcialidade (dados carregados: 2023)
        "taxa_nupcialidade":           anos_metricas.get("taxa_nupcialidade",   [2023]),
        "taxa_divorcialidade":         anos_metricas.get("taxa_divorcialidade", [2023]),
        # PPM — Rebanhos (anual)
        "rebanho_bovino_por_km2":      anos_metricas.get("rebanho_bovino_por_km2",     [2023, 2022, 2021]),
        "rebanho_bovino_por_hab":      anos_metricas.get("rebanho_bovino_por_hab",     [2023, 2022, 2021]),
        "rebanho_equino_por_hab":      anos_metricas.get("rebanho_equino_por_hab",     [2023, 2022, 2021]),
        "rebanho_suino_por_hab":       anos_metricas.get("rebanho_suino_por_hab",      [2023, 2022, 2021]),
        "rebanho_ovino_por_hab":       anos_metricas.get("rebanho_ovino_por_hab",      [2023, 2022, 2021]),
        "rebanho_caprino_por_hab":     anos_metricas.get("rebanho_caprino_por_hab",    [2023, 2022, 2021]),
        "rebanho_galinaceos_por_hab":  anos_metricas.get("rebanho_galinaceos_por_hab", [2023, 2022, 2021]),
        # PPM — Produção Pecuária: dados pendentes (T74 SIDRA intermitente)
        # SINAN — Epidemiologia (anual)
        "incidencia_dengue":           anos_metricas.get("incidencia_dengue",          [2023, 2022, 2021]),
        "incidencia_tuberculose":      anos_metricas.get("incidencia_tuberculose",     [2023, 2022, 2021]),
        "incidencia_hanseniase":       anos_metricas.get("incidencia_hanseniase",      [2023, 2022, 2021]),
        "incidencia_leishmaniose":     anos_metricas.get("incidencia_leishmaniose",    [2023, 2022, 2021]),
        # SIH — Internações SUS (anual)
        "taxa_internacao_sus":              anos_metricas.get("taxa_internacao_sus",              [2023, 2022, 2021]),
        "taxa_internacao_cardiovascular":   anos_metricas.get("taxa_internacao_cardiovascular",   [2023, 2022, 2021]),
        "taxa_internacao_respiratoria":     anos_metricas.get("taxa_internacao_respiratoria",     [2023, 2022, 2021]),
        "taxa_internacao_mental":           anos_metricas.get("taxa_internacao_mental",           [2023, 2022, 2021]),
        "media_permanencia_sus":            anos_metricas.get("media_permanencia_sus",            [2023, 2022, 2021]),
        # Censo Escolar INEP — Rendimento (anual)
        "taxa_aprovacao_ef":           anos_metricas.get("taxa_aprovacao_ef",          [2024, 2023, 2022]),
        "taxa_reprovacao_ef":          anos_metricas.get("taxa_reprovacao_ef",         [2024, 2023, 2022]),
        "taxa_abandono_ef":            anos_metricas.get("taxa_abandono_ef",           [2024, 2023, 2022]),
        "taxa_aprovacao_em":           anos_metricas.get("taxa_aprovacao_em",          [2024, 2023, 2022]),
        "taxa_abandono_em":            anos_metricas.get("taxa_abandono_em",           [2024, 2023, 2022]),
        "distorcao_idade_serie_ef":    anos_metricas.get("distorcao_idade_serie_ef",   [2024, 2023, 2022]),
        "distorcao_idade_serie_em":    anos_metricas.get("distorcao_idade_serie_em",   [2024, 2023, 2022]),
        # SENATRAN — Frota Veicular (dados carregados: 2020-2022)
        "frota_automovel_por_1k":      anos_metricas.get("frota_automovel_por_1k",    [2022, 2021, 2020]),
        "frota_moto_por_1k":           anos_metricas.get("frota_moto_por_1k",         [2022, 2021, 2020]),
        "frota_caminhao_por_1k":       anos_metricas.get("frota_caminhao_por_1k",     [2022, 2021, 2020]),
        "frota_onibus_por_1k":         anos_metricas.get("frota_onibus_por_1k",       [2022, 2021, 2020]),
        "frota_total_por_1k":          anos_metricas.get("frota_total_por_1k",        [2022, 2021, 2020]),
    }


# Cache TTL para /anos: evita 6 queries sequenciais no PostGIS a cada hit.
# 60s é suficiente — anos novos só aparecem após rodar pipeline + refresh.
_ANOS_TTL = 60.0
_anos_cache: dict | None = None
_anos_cache_ts: float = 0.0
_anos_lock = threading.Lock()


def query_anos_cached():
    global _anos_cache, _anos_cache_ts
    with _anos_lock:
        if _anos_cache is not None and (time.monotonic() - _anos_cache_ts) < _ANOS_TTL:
            return _anos_cache
        _anos_cache = query_anos()
        _anos_cache_ts = time.monotonic()
        return _anos_cache


_municipios_cache: list | None = None
_municipios_lock = threading.Lock()


def query_municipios() -> list:
    """Retorna lista de municípios com nome, UF e centróide (lon, lat)."""
    global _municipios_cache
    with _municipios_lock:
        if _municipios_cache is not None:
            return _municipios_cache
        return _query_municipios_db()


def _query_municipios_db() -> list:
    global _municipios_cache
    conn = psycopg2.connect(**DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    m.cod_ibge_7,
                    m.nome,
                    u.sigla,
                    ROUND(ST_X(ST_Centroid(m.geom))::NUMERIC, 5) AS lon,
                    ROUND(ST_Y(ST_Centroid(m.geom))::NUMERIC, 5) AS lat
                FROM geo.municipios m
                JOIN geo.ufs u ON u.cod_uf = m.cod_uf
                ORDER BY m.nome
            """)
            rows = cur.fetchall()
    finally:
        conn.close()
    _municipios_cache = [
        {"cod": r[0], "nome": r[1], "uf": r[2], "lon": float(r[3]), "lat": float(r[4])}
        for r in rows
    ]
    return _municipios_cache


class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/anos", "/anos/"):
            try:
                data = query_anos_cached()
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                import traceback; traceback.print_exc()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "internal server error"}).encode())
        elif self.path in ("/municipios", "/municipios/"):
            try:
                data = query_municipios()
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                import traceback; traceback.print_exc()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "internal server error"}).encode())
        elif self.path in ("/health", "/health/"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "not found"}).encode())

    def log_message(self, fmt, *args):  # noqa: suppress access log
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    print(f"[brasil-api] listening on :{port}", flush=True)
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.daemon_threads = True
    server.serve_forever()
