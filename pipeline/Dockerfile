FROM python:3.11-slim

# Dependências do sistema para geopandas + psycopg2 + fiona
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin libgdal-dev libgeos-dev libproj-dev \
    gcc g++ libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/dagster/app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

COPY . .

ENV DAGSTER_HOME=/opt/dagster/dagster_home
RUN mkdir -p $DAGSTER_HOME

EXPOSE 3001
