"""Leitura do SIDRA com a convenção de sinais do IBGE aplicada num lugar só.

No SIDRA, "-" é ZERO ABSOLUTO (não resultante de arredondamento); "X" é valor inibido para não
identificar o informante; "..." e ".." são não aplicável / não disponível. Os loaders descartavam
os quatro igualmente, e o município sem cabras, sem favela ou sem divórcio no ano virava "sem dado"
(rebanho caprino 2023: 5.021 de 5.570). get() devolve a resposta com "-" já trocado por "0" nas
séries; X, ... e .. continuam como estão e seguem descartados pelos loaders.
Fonte da convenção: https://sidra.ibge.gov.br (Sinais convencionais), notas de rodapé das tabelas.
"""
import time

import requests

HOSTS_IBGE = ("servicodados.ibge.gov.br", "apisidra.ibge.gov.br")


def _zerar(obj):
    if isinstance(obj, dict):
        return {k: ("0" if v == "-" and k.isdigit() else _zerar(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_zerar(v) for v in obj]
    return obj


def get(url, *args, tentativas: int = 4, **kwargs):
    # o IBGE às vezes demora mais que o timeout (medido 23/10/2026: um ReadTimeout em 2017 derrubou o
    # loader inteiro e tudo depois dele ficou sem carregar); nova tentativa com espera crescente
    kwargs["timeout"] = max(kwargs.get("timeout", 60), 120)
    for t in range(tentativas):
        try:
            r = requests.get(url, *args, **kwargs)
            break
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if t == tentativas - 1:
                raise
            time.sleep(15 * (t + 1))
    if any(h in url for h in HOSTS_IBGE):
        original = r.json
        r.json = lambda *a, **k: _zerar(original(*a, **k))
    return r
