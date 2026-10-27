#!/usr/bin/env python3
"""
load_senatran.py
Carrega frota veicular por município (SENATRAN/RENAVAM, posição de dezembro) para
api.metricas_municipio.

Indicadores (anuais, por 1000 hab. do Censo 2022, como os demais indicadores per capita do painel):
  frota_automovel_por_1k   — automóvel
  frota_moto_por_1k        — motocicleta, motoneta, ciclomotor, triciclo, quadriciclo
  frota_caminhao_por_1k    — caminhão, caminhão trator, caminhonete, camioneta
  frota_onibus_por_1k      — ônibus, micro-ônibus
  frota_total_por_1k       — coluna TOTAL da planilha (todos os tipos)

Fonte: a planilha "frota por município e tipo" de dezembro, que a SENATRAN publica na página
anual https://www.gov.br/transportes/pt-br/assuntos/transito/conteudo-Senatran/frota-de-veiculos-<ano>.
O nome do arquivo muda quase todo ano (frota_por_municipio_e_tipo-dez_15.rar,
frota_munic_dezembro_2017.xls, frota-reg-munic-tipo-modelo-07-dezembro2020.xls,
FrotapormunicipioetipoDezembro2024.xlsx…), então o link é achado na página, não fixado.
Medido em 27/10/2026: o loader antigo usava CSVs do dados.transportes.gov.br que já dão 404, e
só tinha 2020–2022. A página tem dezembro de 2015 a 2025.

O arquivo fica em pipeline/.cache/frota/. Um ano só é gravado se a planilha casou com pelo menos
5.500 municípios; então substitui as cinco métricas daquele ano.

Uso (precisa de xlrd e openpyxl — pipeline/.venv):
    .venv/bin/python load_senatran.py                 # 2015–2025
    .venv/bin/python load_senatran.py --anos 2023
"""

import argparse
import os
import pathlib
import re
import subprocess
import unicodedata
from urllib.parse import urljoin

import pandas as pd
import psycopg2
import requests
from psycopg2.extras import execute_values

DB_PARAMS = dict(
    host=os.environ.get("POSTGRES_HOST", "localhost"),
    port=int(os.environ.get("POSTGRES_PORT", 5432)),
    database=os.environ.get("POSTGRES_DB", "brasil_dados"),
    user=os.environ.get("POSTGRES_USER", "brasil"),
    password=os.environ.get("POSTGRES_PASSWORD", ""),
)

PAGINA = "https://www.gov.br/transportes/pt-br/assuntos/transito/conteudo-Senatran/frota-de-veiculos-{ano}"
CACHE = pathlib.Path(__file__).parent / ".cache" / "frota"
HDR = {"User-Agent": "Mozilla/5.0 (brasil-em-dados)"}

UF_COD = {
    "AC": 12, "AL": 27, "AP": 16, "AM": 13, "BA": 29, "CE": 23, "DF": 53, "ES": 32, "GO": 52,
    "MA": 21, "MT": 51, "MS": 50, "MG": 31, "PA": 15, "PB": 25, "PR": 41, "PE": 26, "PI": 22,
    "RJ": 33, "RN": 24, "RS": 43, "RO": 11, "RR": 14, "SC": 42, "SP": 35, "SE": 28, "TO": 17,
}
# coluna da planilha (normalizada) → categoria
CATEGORIA = {
    "AUTOMOVEL": "automovel",
    "MOTOCICLETA": "moto", "MOTONETA": "moto", "CICLOMOTOR": "moto", "TRICICLO": "moto", "QUADRICICLO": "moto",
    "CAMINHAO": "caminhao", "CAMINHAO TRATOR": "caminhao", "CAMINHONETE": "caminhao", "CAMIONETA": "caminhao",
    "ONIBUS": "onibus", "MICRO-ONIBUS": "onibus", "MICROONIBUS": "onibus",
}
# Nome na planilha → nome na malha do IBGE: grafias antigas, renomeações e erros de digitação da
# fonte. Revisado à mão em 27/10/2026 (o par mais próximo por difflib errava em 6 dos 41). Ficam de
# fora de propósito: "MUNICIPIO NAO INFORMADO", IBITIUVA/SP (distrito de Pitangueiras) e BOA
# ESPERANCA DO NORTE/MT (instalado depois da malha de 2022).
ALIAS = {
    ("LAGEDO DO TABOCAL", "BA"): "Lajedo do Tabocal", ("SANTA TERESINHA", "BA"): "Santa Terezinha",
    ("BOM JESUS", "GO"): "Bom Jesus de Goiás", ("AMPARO DA SERRA", "MG"): "Amparo do Serra",
    ("BARAO D0 MONTE ALTO", "MG"): "Barão de Monte Alto", ("BRASOPOLIS", "MG"): "Brazópolis",
    ("GOUVEA", "MG"): "Gouveia", ("QUELUZITA", "MG"): "Queluzito", ("POXOREO", "MT"): "Poxoréu",
    ("VILA BELA DA SANTISSIMA TRINDA", "MT"): "Vila Bela da Santíssima Trindade",
    ("ELDORADO DOS CARAJAS", "PA"): "Eldorado do Carajás", ("SANTA ISABEL DO PARA", "PA"): "Santa Izabel do Pará",
    ("CAMPO DE SANTANA", "PB"): "Tacima", ("SANTAREM", "PB"): "Joca Claudino",
    ("SAO DOMINGOS DE POMBAL", "PB"): "São Domingos", ("BELEM DE SAO FRANCISCO", "PE"): "Belém do São Francisco",
    ("IGUARACI", "PE"): "Iguaracy", ("LAGOA DO ITAENGA", "PE"): "Lagoa de Itaenga",
    ("SAO FRANCISCO DE ASSIS DO PIAU", "PI"): "São Francisco de Assis do Piauí",
    ("BELA VISTA DO CAROBA", "PR"): "Bela Vista da Caroba", ("MUNHOZ DE MELLO", "PR"): "Munhoz de Melo",
    ("PINHAL DO SAO BENTO", "PR"): "Pinhal de São Bento", ("SANTA CRUZ DO MONTE CASTELO", "PR"): "Santa Cruz de Monte Castelo",
    ("ARMACAO DE BUZIOS", "RJ"): "Armação dos Búzios", ("PARATI", "RJ"): "Paraty",
    ("TRAJANO DE MORAIS", "RJ"): "Trajano de Moraes", ("ASSU", "RN"): "Açu", ("BOA SAUDE", "RN"): "Januário Cicco",
    ("NOVA DO MAMORE", "RO"): "Nova Mamoré", ("BALNEARIO DE PICARRAS", "SC"): "Balneário Piçarras",
    ("LAGEADO GRANDE", "SC"): "Lajeado Grande", ("PRESIDENTE CASTELO BRANCO", "SC"): "Presidente Castello Branco",
    ("SAO LOURENCO D'OESTE", "SC"): "São Lourenço do Oeste", ("SAO MIGUEL D'OESTE", "SC"): "São Miguel do Oeste",
    ("AMPARO DE SAO FRANCISCO", "SE"): "Amparo do São Francisco", ("GRACCHO CARDOSO", "SE"): "Gracho Cardoso",
    ("EMBU", "SP"): "Embu das Artes", ("COUTO DE MAGALHAES", "TO"): "Couto Magalhães",
    ("FORTALEZA DO TABOCAO", "TO"): "Tabocão", ("SAO VALERIO DA NATIVIDADE", "TO"): "São Valério",
}
METRICA = {"automovel": "frota_automovel_por_1k", "moto": "frota_moto_por_1k", "caminhao": "frota_caminhao_por_1k",
           "onibus": "frota_onibus_por_1k", "total": "frota_total_por_1k"}


def norm(s) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().upper()


def chave_nome(s) -> str:
    """Nome de município para casar planilha × malha: sem acento, hífen, apóstrofo nem espaço."""
    return re.sub(r"[^A-Z0-9]", "", norm(s))


def achar_link(ano: int) -> str:
    html = requests.get(PAGINA.format(ano=ano), headers=HDR, timeout=60).text
    for href in re.findall(r'href="([^"]+)"', html):
        nome = href.removesuffix("/@@download/file").rsplit("/", 1)[-1]
        n = re.sub(r"[^a-z0-9]", "", nome.lower())
        if "dez" in n and any(p in n for p in ("frotapormunicipioetipo", "frotamunic", "frotaregmunic")):
            return urljoin(PAGINA.format(ano=ano), href)
    raise FileNotFoundError(f"sem planilha de dezembro por município na página de {ano}")


def baixar(ano: int) -> pathlib.Path:
    feitos = [p for p in CACHE.glob(f"{ano}.*") if p.suffix in (".xls", ".xlsx")]
    if feitos:
        return feitos[0]
    url = achar_link(ano)
    nome = url.removesuffix("/@@download/file").rsplit("/", 1)[-1]
    ext = nome.rsplit(".", 1)[-1].lower()
    bruto = CACHE / f"{ano}-bruto.{ext}"
    r = requests.get(url, headers=HDR, timeout=300)
    r.raise_for_status()
    bruto.write_bytes(r.content)
    print(f"  {ano}: baixado {nome} ({len(r.content):,} bytes)", flush=True)
    if ext in ("xls", "xlsx"):
        return bruto.rename(CACHE / f"{ano}.{ext}")
    # .rar/.zip com uma planilha dentro
    destino = CACHE / f"{ano}-x"
    destino.mkdir(exist_ok=True)
    subprocess.run(["bsdtar", "-xf", str(bruto), "-C", str(destino)], check=True)
    dentro = [p for p in destino.rglob("*") if p.suffix.lower() in (".xls", ".xlsx")]
    if len(dentro) != 1:
        raise RuntimeError(f"{nome}: {len(dentro)} planilhas dentro")
    return dentro[0].rename(CACHE / f"{ano}{dentro[0].suffix.lower()}")


def ler(arq: pathlib.Path) -> pd.DataFrame:
    """A planilha tem linhas de título antes do cabeçalho; acha a aba e a linha com UF e MUNICIPIO.
    (A de 2015 abre num glossário, e a aba de dados se chama JUL_2015 embora o arquivo seja o de
    dezembro: o total, 90.686.936, fica entre dez/2014 e dez/2016.)"""
    for aba, bruto in pd.read_excel(arq, header=None, dtype=str, sheet_name=None).items():
        for i in range(min(40, len(bruto))):
            celulas = [norm(c) for c in bruto.iloc[i].tolist()]
            if "UF" in celulas and any(c.startswith("MUNICIPIO") for c in celulas):
                df = bruto.iloc[i + 1:].copy()
                df.columns = celulas
                return df
    raise RuntimeError(f"{arq.name}: cabeçalho UF/MUNICIPIO não encontrado")


def numero(v) -> float:
    s = "" if v is None else str(v).strip()
    if s in ("", "nan", "NaN", "-"):
        return 0.0
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):        # 1.234.567 como texto
        s = s.replace(".", "")
    return float(s.replace(",", "."))


def main():
    ap = argparse.ArgumentParser(description="Carrega frota SENATRAN (dezembro) em api.metricas_municipio")
    ap.add_argument("--anos", nargs="+", type=int, default=list(range(2015, 2026)))
    ap.add_argument("--sem-gravar", action="store_true", help="só lê e mostra o resumo")
    args = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)

    conn = psycopg2.connect(**DB_PARAMS)
    with conn.cursor() as cur:
        cur.execute("""SELECT m.nome, u.sigla, m.cod_ibge_7, m.populacao_2022
                       FROM geo.municipios m JOIN geo.ufs u ON u.cod_uf = m.cod_uf""")
        malha = cur.fetchall()
        cur.execute("""CREATE TABLE IF NOT EXISTS api.metricas_frota_antes_20261027 AS
                       SELECT * FROM api.metricas_municipio WHERE metrica LIKE 'frota\\_%'""")
        conn.commit()
    indice = {(chave_nome(n), s): c for n, s, c, _ in malha}
    pop = {c: p for _, _, c, p in malha if p and p > 0}

    for ano in args.anos:
        try:
            df = ler(baixar(ano))
        except FileNotFoundError as e:
            print(f"  {ano}: {e}", flush=True)
            continue
        col_mun = next(c for c in df.columns if c.startswith("MUNICIPIO"))
        tipos = {c: CATEGORIA[c] for c in df.columns if c in CATEGORIA}
        sem_tipo = [c for c in df.columns if c not in CATEGORIA and c not in ("UF", col_mun, "TOTAL", "NAN", "")]
        soma, nao_casou = {}, []
        for _, r in df.iterrows():
            uf = norm(r["UF"])
            if uf not in UF_COD:
                continue
            nome = ALIAS.get((norm(r[col_mun]), uf), r[col_mun])
            cod = indice.get((chave_nome(nome), uf))
            if cod is None:
                nao_casou.append(f"{r[col_mun]}/{uf}")
                continue
            s = soma.setdefault(cod, dict.fromkeys(METRICA, 0.0))
            for col, cat in tipos.items():
                s[cat] += numero(r[col])
            s["total"] += numero(r["TOTAL"])
        brasil = {cat: sum(s[cat] for s in soma.values()) for cat in METRICA}
        resumo = (f"{len(soma)} municípios; frota {brasil['total']:,.0f} (automóvel {brasil['automovel']:,.0f}, "
                  f"moto {brasil['moto']:,.0f}, caminhão {brasil['caminhao']:,.0f}, ônibus {brasil['onibus']:,.0f}); "
                  f"não casaram {len(nao_casou)} {nao_casou[:6]}; colunas sem categoria: {sem_tipo}")
        if args.sem_gravar:
            print(f"  {ano}: {resumo}", flush=True)
            continue
        if len(soma) < 5500:
            print(f"  {ano}: NÃO gravado — {resumo}", flush=True)
            continue
        linhas = [(cod, METRICA[cat], ano, v / pop[cod] * 1000)
                  for cod, s in soma.items() if cod in pop for cat, v in s.items()]
        with conn.cursor() as cur:
            cur.execute("DELETE FROM api.metricas_municipio WHERE ano = %s AND metrica LIKE 'frota\\_%%'", (ano,))
            execute_values(cur, "INSERT INTO api.metricas_municipio (cod_municipio, metrica, ano, valor) VALUES %s",
                           linhas, page_size=2000)
            conn.commit()
        print(f"  {ano}: GRAVADO — {resumo}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
