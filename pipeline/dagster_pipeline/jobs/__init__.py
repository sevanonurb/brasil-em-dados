from dagster import define_asset_job, AssetSelection

# Job diário: refresh das vistas materializadas após ingestão
refresh_indicadores_job = define_asset_job(
    name="refresh_indicadores_job",
    selection=AssetSelection.keys("postgis_municipios", "postgis_setores_subdivididos"),
    description="Regenera vistas materializadas de indicadores após ingestão de novos dados.",
    tags={"schedule": "diario"},
)
