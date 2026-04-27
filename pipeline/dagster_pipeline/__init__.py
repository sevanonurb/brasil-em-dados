from dagster import Definitions, load_assets_from_modules
from . import assets
from .jobs import refresh_indicadores_job
from .sensors import datasus_sim_sensor

all_assets = load_assets_from_modules([assets])

defs = Definitions(
    assets=all_assets,
    jobs=[refresh_indicadores_job],
    sensors=[datasus_sim_sensor],
)
