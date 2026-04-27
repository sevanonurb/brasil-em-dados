from .ibge import ibge_ufs, ibge_municipios, postgis_ufs, postgis_municipios, postgis_setores_subdivididos
from .datasus import sim_mortalidade_raw

__all__ = [
    "ibge_ufs",
    "ibge_municipios",
    "postgis_municipios",
    "postgis_setores_subdivididos",
    "sim_mortalidade_raw",
]
