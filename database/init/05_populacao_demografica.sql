-- =============================================================================
-- 05_populacao_demografica.sql
-- Tabelas auxiliares com breakdown demográfico para denominadores corretos
-- nas taxas por raça e faixa etária.
--
-- Fonte: IBGE Censo 2022, via SIDRA:
--   Tabela 9605 — População por cor ou raça × município
--   Tabela 9514 — População por idade × município
--
-- Carregadas por pipeline/load_populacao_demografica.py
-- =============================================================================

CREATE TABLE IF NOT EXISTS censo.populacao_raca_municipio (
    cod_municipio  INTEGER  NOT NULL,  -- 7 dígitos (mesmo que geo.municipios.cod_ibge_7)
    cor_raca       SMALLINT NOT NULL,  -- 1=Branca, 2=Preta, 3=Amarela, 4=Parda, 5=Indígena
    populacao      INTEGER  NOT NULL,
    PRIMARY KEY (cod_municipio, cor_raca)
);

COMMENT ON TABLE censo.populacao_raca_municipio IS
    'População por cor/raça × município (IBGE Censo 2022, SIDRA tabela 9605). '
    'Usado como denominador correto ao filtrar mortalidade por raça — '
    'evita distorção de usar população total como base para subgrupos.';

CREATE TABLE IF NOT EXISTS censo.populacao_faixa_municipio (
    cod_municipio  INTEGER  NOT NULL,
    faixa_etaria   SMALLINT NOT NULL,  -- 0=<1a, 1=1-4a, 2=5-9a, ... 17=80+  (encoding SIM)
    populacao      INTEGER  NOT NULL,
    PRIMARY KEY (cod_municipio, faixa_etaria)
);

COMMENT ON TABLE censo.populacao_faixa_municipio IS
    'População por faixa etária × município (IBGE Censo 2022, SIDRA tabela 9514). '
    'Faixas compatíveis com encoding SIM/DataSUS (0–17). '
    'Usado como denominador correto ao filtrar mortalidade por faixa etária.';
