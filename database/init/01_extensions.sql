-- =============================================================================
-- 01_extensions.sql
-- Extensões necessárias. Executado uma única vez na inicialização do container.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS btree_gist;  -- índices compostos com GiST

-- Verifica versões instaladas
DO $$
BEGIN
  RAISE NOTICE 'PostGIS version: %', PostGIS_Full_Version();
  RAISE NOTICE 'PostgreSQL version: %', version();
END $$;

-- Schema de trabalho separado do public
CREATE SCHEMA IF NOT EXISTS geo;      -- geometrias e malhas territoriais
CREATE SCHEMA IF NOT EXISTS saude;    -- dados DataSUS
CREATE SCHEMA IF NOT EXISTS seguranca; -- dados Sinesp / FBSP
CREATE SCHEMA IF NOT EXISTS economia; -- Siconfi, SGS-BCB, Ipeadata
CREATE SCHEMA IF NOT EXISTS censo;    -- IBGE Censo 2022
CREATE SCHEMA IF NOT EXISTS api;      -- views públicas para o Martin / API externa

-- Role de leitura para a API (Martin + frontend)
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'api_readonly') THEN
    CREATE ROLE api_readonly NOLOGIN;
  END IF;
END $$;

GRANT USAGE ON SCHEMA geo, api, censo TO api_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA geo TO api_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA api TO api_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA censo TO api_readonly;

-- Garante permissões em tabelas futuras
ALTER DEFAULT PRIVILEGES IN SCHEMA geo GRANT SELECT ON TABLES TO api_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA api GRANT SELECT ON TABLES TO api_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA censo GRANT SELECT ON TABLES TO api_readonly;

-- Usuário da API herda a role
GRANT api_readonly TO brasil;
