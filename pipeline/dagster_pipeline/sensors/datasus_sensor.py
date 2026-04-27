"""
Sensor Dagster para detecção de novos arquivos mensais no FTP do DataSUS.
Verifica 1x/dia por mudanças no índice FTP — DataSUS não tem webhooks.
Dispara o job de ingestão SIM quando detecta novo arquivo publicado.
"""

import hashlib
import re

import httpx
import structlog
from dagster import (
    RunRequest,
    SensorEvaluationContext,
    SensorResult,
    sensor,
)

log = structlog.get_logger()

DATASUS_SIM_FTP_INDEX = (
    "http://ftp.datasus.gov.br/dissemin/publicos/SIM/CID10/DORES/"
)

# Padrão de arquivo SIM: DOXX20YY.dbc (ex: DOSP2023.dbc = SP/2023)
SIM_FILE_PATTERN = re.compile(r"DO([A-Z]{2})(\d{4})\.dbc", re.IGNORECASE)


@sensor(
    minimum_interval_seconds=60 * 60 * 24,  # verifica 1x por dia
    description=(
        "Detecta novos arquivos mensais no FTP do DataSUS (SIM). "
        "Dispara ingestão quando novo arquivo é publicado."
    ),
)
def datasus_sim_sensor(context: SensorEvaluationContext) -> SensorResult:
    try:
        response = httpx.get(DATASUS_SIM_FTP_INDEX, timeout=30)
        response.raise_for_status()
    except Exception as e:
        log.warning("datasus_ftp_inaccessivel", error=str(e))
        # Não falha o sensor — DataSUS FTP é instável
        return SensorResult(run_requests=[])

    content = response.text

    # Hash do índice completo — muda quando qualquer arquivo novo é publicado
    current_hash = hashlib.md5(content.encode()).hexdigest()
    last_hash = context.cursor

    if current_hash == last_hash:
        context.log.info("Sem novos arquivos no DataSUS FTP.")
        return SensorResult(run_requests=[])

    # Identifica quais UFs/anos estão disponíveis
    arquivos = SIM_FILE_PATTERN.findall(content)
    run_requests = []

    for sigla_uf, ano_str in arquivos:
        ano = int(ano_str)
        # Processa apenas anos recentes (últimos 3 anos)
        if ano < 2021:
            continue

        run_requests.append(
            RunRequest(
                run_key=f"sim_{sigla_uf}_{ano}_{current_hash[:8]}",
                run_config={
                    "ops": {
                        "sim_mortalidade_raw": {
                            "config": {
                                "ufs": [sigla_uf],
                                "ano": ano,
                            }
                        }
                    }
                },
                tags={
                    "fonte": "datasus_sim",
                    "uf": sigla_uf,
                    "ano": str(ano),
                },
            )
        )

    context.log.info(
        f"Novos dados detectados: {len(run_requests)} arquivos. "
        f"Hash FTP: {current_hash[:8]}"
    )

    return SensorResult(
        run_requests=run_requests,
        cursor=current_hash,
    )
