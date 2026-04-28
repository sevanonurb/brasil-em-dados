-- =============================================================================
-- 02_schema.sql
-- Star schema espacial: dimensões territoriais + tabelas fato temáticas.
-- Geometrias armazenadas APENAS em EPSG:4674 (equivalente a WGS84 para web).
-- ST_Subdivide aplicado em modelos dbt, não aqui — mantemos geometria original
-- para cálculos analíticos corretos de área e distância.
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- DIMENSÃO ESPACIAL: Hierarquia territorial IBGE
-- ─────────────────────────────────────────────────────────────────────────────

-- Nível 1: Unidades da Federação (27 polígonos)
CREATE TABLE IF NOT EXISTS geo.ufs (
    gid            SERIAL PRIMARY KEY,
    cod_uf         SMALLINT    NOT NULL UNIQUE,  -- ex: 35 (SP)
    sigla          CHAR(2)     NOT NULL UNIQUE,
    nome           VARCHAR(50) NOT NULL,
    regiao         VARCHAR(20) NOT NULL,
    geom           geometry(MultiPolygon, 4674) NOT NULL,
    geom_simplified geometry(MultiPolygon, 4674),  -- para zoom baixo (tolerância ~1km)
    area_km2       NUMERIC(12, 2),
    populacao_2022 INTEGER,
    updated_at     TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Nível 2: Municípios (5.570)
CREATE TABLE IF NOT EXISTS geo.municipios (
    gid            SERIAL PRIMARY KEY,
    cod_ibge_7     INTEGER     NOT NULL UNIQUE,  -- 7 dígitos (ex: 3550308 = SP)
    cod_uf         SMALLINT    NOT NULL REFERENCES geo.ufs(cod_uf),
    nome           VARCHAR(100) NOT NULL,
    capital        BOOLEAN     DEFAULT FALSE,
    geom           geometry(MultiPolygon, 4674) NOT NULL,
    geom_simplified geometry(MultiPolygon, 4674),
    area_km2       NUMERIC(12, 2),
    populacao_2022 INTEGER,
    pib_per_capita NUMERIC(12, 2),
    updated_at     TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Nível 3: Setores Censitários IBGE 2022 (~215k setores)
-- Nota: PRIMARY KEY em tabela particionada DEVE incluir a coluna de partição (cod_uf)
CREATE TABLE IF NOT EXISTS geo.setores_censitarios (
    gid            SERIAL,
    cod_setor      BIGINT      NOT NULL,  -- 15 dígitos; índice único criado em 03_indexes.sql
    cod_municipio  INTEGER     NOT NULL,
    cod_uf         SMALLINT    NOT NULL,
    tipo_setor     SMALLINT,   -- 1=urbano, 2=rural, 3=aglomerado subnormal
    geom           geometry(MultiPolygon, 4674) NOT NULL,
    area_km2       NUMERIC(10, 4),
    domicilios_total INTEGER,
    populacao_total  INTEGER,
    updated_at     TIMESTAMP WITH TIME ZONE DEFAULT now(),
    PRIMARY KEY (gid, cod_uf)  -- inclui cod_uf (coluna de partição)
) PARTITION BY LIST (cod_uf);

-- Partições por UF (criadas dinamicamente pelo pipeline, exemplo para SP e RJ)
CREATE TABLE IF NOT EXISTS geo.setores_censitarios_35
    PARTITION OF geo.setores_censitarios FOR VALUES IN (35);
CREATE TABLE IF NOT EXISTS geo.setores_censitarios_33
    PARTITION OF geo.setores_censitarios FOR VALUES IN (33);
CREATE TABLE IF NOT EXISTS geo.setores_censitarios_outros
    PARTITION OF geo.setores_censitarios DEFAULT;

-- Tabela auxiliar: geometrias subdivididas para queries espaciais rápidas
-- Gerada pelo dbt a partir de geo.setores_censitarios via ST_Subdivide
CREATE TABLE IF NOT EXISTS geo.setores_subdivididos (
    gid            SERIAL,
    cod_setor      BIGINT      NOT NULL,
    cod_municipio  INTEGER     NOT NULL,
    cod_uf         SMALLINT    NOT NULL,
    geom           geometry(Polygon, 4674) NOT NULL,  -- ST_Subdivide → simples Polygon
    PRIMARY KEY (gid, cod_uf)
) PARTITION BY LIST (cod_uf);

CREATE TABLE IF NOT EXISTS geo.setores_subdivididos_35
    PARTITION OF geo.setores_subdivididos FOR VALUES IN (35);
CREATE TABLE IF NOT EXISTS geo.setores_subdivididos_33
    PARTITION OF geo.setores_subdivididos FOR VALUES IN (33);
CREATE TABLE IF NOT EXISTS geo.setores_subdivididos_outros
    PARTITION OF geo.setores_subdivididos DEFAULT;

-- ─────────────────────────────────────────────────────────────────────────────
-- DIMENSÃO ESPACIAL: Endereços CNEFE (111.1M pontos)
-- Particionado por UF para partition pruning eficiente
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS censo.cnefe_enderecos (
    id             BIGSERIAL,
    cod_setor      BIGINT,
    cod_municipio  INTEGER     NOT NULL,
    cod_uf         SMALLINT    NOT NULL,
    tipo_logradouro SMALLINT,  -- 1=rua, 2=avenida, etc.
    especie        SMALLINT,   -- 1=domicílio particular, 2=coletivo
    geom           geometry(Point, 4674) NOT NULL,
    PRIMARY KEY (id, cod_uf)
) PARTITION BY LIST (cod_uf);

-- Partições criadas automaticamente pelo pipeline para cada UF
-- Exemplo:
CREATE TABLE IF NOT EXISTS censo.cnefe_enderecos_35
    PARTITION OF censo.cnefe_enderecos FOR VALUES IN (35);
CREATE TABLE IF NOT EXISTS censo.cnefe_enderecos_33
    PARTITION OF censo.cnefe_enderecos FOR VALUES IN (33);
CREATE TABLE IF NOT EXISTS censo.cnefe_enderecos_outros
    PARTITION OF censo.cnefe_enderecos DEFAULT;

-- ─────────────────────────────────────────────────────────────────────────────
-- TABELA FATO: Saúde — SIM/DataSUS
-- Particionada por UF + ano para partition pruning agressivo
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS saude.sim_mortalidade (
    id             BIGSERIAL,
    cod_municipio  INTEGER     NOT NULL,
    cod_uf         SMALLINT    NOT NULL,
    cod_setor      BIGINT,
    ano            SMALLINT    NOT NULL,
    mes            SMALLINT,
    cid10_capitulo CHAR(1)     NOT NULL,  -- ex: 'I' = Doenças cardiovasculares
    cid10_codigo   CHAR(5),               -- ex: 'I219' = Infarto agudo do miocárdio
    faixa_etaria   SMALLINT,  -- 0=<1ano, 1=1-4, 2=5-9, ... 17=80+
    sexo           CHAR(1),   -- 'M', 'F', 'I'
    cor_raca       SMALLINT,  -- 1=Branca, 2=Preta, 3=Amarela, 4=Parda, 5=Indígena
    escolaridade   SMALLINT,
    PRIMARY KEY (id, cod_uf, ano)
) PARTITION BY LIST (cod_uf);

CREATE TABLE IF NOT EXISTS saude.sim_mortalidade_35
    PARTITION OF saude.sim_mortalidade FOR VALUES IN (35);
CREATE TABLE IF NOT EXISTS saude.sim_mortalidade_outros
    PARTITION OF saude.sim_mortalidade DEFAULT;

-- ─────────────────────────────────────────────────────────────────────────────
-- TABELA FATO: Segurança — Sinesp
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS seguranca.sinesp_ocorrencias (
    id             BIGSERIAL,
    cod_municipio  INTEGER     NOT NULL,
    cod_uf         SMALLINT    NOT NULL,
    ano            SMALLINT    NOT NULL,
    mes            SMALLINT,
    tipo_crime     VARCHAR(100) NOT NULL,
    vitimas        SMALLINT    DEFAULT 1,
    PRIMARY KEY (id, cod_uf, ano)
) PARTITION BY LIST (cod_uf);

CREATE TABLE IF NOT EXISTS seguranca.sinesp_ocorrencias_35
    PARTITION OF seguranca.sinesp_ocorrencias FOR VALUES IN (35);
CREATE TABLE IF NOT EXISTS seguranca.sinesp_ocorrencias_outros
    PARTITION OF seguranca.sinesp_ocorrencias DEFAULT;

-- ─────────────────────────────────────────────────────────────────────────────
-- TABELA FATO: Economia — Siconfi + SGS-BCB
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS economia.siconfi_municipios (
    id             BIGSERIAL PRIMARY KEY,
    cod_municipio  INTEGER     NOT NULL,
    cod_uf         SMALLINT    NOT NULL,
    ano            SMALLINT    NOT NULL,
    receita_total  NUMERIC(18, 2),
    despesa_saude  NUMERIC(18, 2),
    despesa_educacao NUMERIC(18, 2),
    transferencias_sus NUMERIC(18, 2),
    pib            NUMERIC(18, 2),
    UNIQUE (cod_municipio, ano)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- VISTA MATERIALIZADA: Indicadores consolidados por município × ano
-- Atualizada diariamente pelo Dagster após ingestão de novos dados.
-- Esta é a tabela que o Martin consulta para tiles de zoom 0-12.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS api.indicadores_municipio AS
SELECT
    m.cod_ibge_7,
    m.cod_uf,
    m.nome                                          AS nome_municipio,
    m.geom,
    m.geom_simplified,
    m.area_km2,
    m.populacao_2022,
    -- Saúde (último ano disponível)
    COUNT(s.id) FILTER (WHERE s.ano = 2023)         AS obitos_2023,
    ROUND(
        COUNT(s.id) FILTER (WHERE s.ano = 2023)
        * 100000.0 / NULLIF(m.populacao_2022, 0), 1
    )                                               AS taxa_mortalidade_2023,
    COUNT(s.id) FILTER (
        WHERE s.ano = 2023
        AND s.cid10_capitulo = 'I'
    )                                               AS obitos_cardiovascular_2023,
    -- Segurança: homicídios derivados do SIM/DataSUS (CID X85–X99 agressões; Y00–Y09 outros meios)
    -- Metodologia equivalente ao Atlas da Violência (IPEA/FBSP).
    -- Quando SINESP for carregado, substituir por: SUM(cr.vitimas) FILTER (tipo_crime ILIKE '%homicídio%')
    COUNT(s.id) FILTER (
        WHERE s.ano = 2023
          AND s.cid10_codigo >= 'X85'
          AND s.cid10_codigo < 'Y1'
    )                                               AS homicidios_2023,
    ROUND(
        COUNT(s.id) FILTER (
            WHERE s.ano = 2023
              AND s.cid10_codigo >= 'X85'
              AND s.cid10_codigo < 'Y1'
        ) * 100000.0 / NULLIF(m.populacao_2022, 0), 1
    )                                               AS taxa_homicidio_2023,
    -- Saúde — mortalidade por causa específica 2023
    ROUND(
        COUNT(s.id) FILTER (WHERE s.ano = 2023 AND s.cid10_capitulo = 'I')
        * 100000.0 / NULLIF(m.populacao_2022, 0), 1
    )                                               AS mortalidade_cardiovascular_2023,
    ROUND(
        COUNT(s.id) FILTER (WHERE s.ano = 2023 AND s.cid10_capitulo = 'C')
        * 100000.0 / NULLIF(m.populacao_2022, 0), 1
    )                                               AS mortalidade_cancer_2023,
    ROUND(
        COUNT(s.id) FILTER (WHERE s.ano = 2023 AND s.cid10_capitulo = 'J')
        * 100000.0 / NULLIF(m.populacao_2022, 0), 1
    )                                               AS mortalidade_respiratoria_2023,
    -- Economia (Siconfi/FINBRA 2022)
    e.receita_total                                 AS receita_municipal_2022,
    e.transferencias_sus                            AS transferencias_sus_2022,
    e.pib                                           AS pib_2022,
    ROUND(e.pib / NULLIF(m.populacao_2022, 0), 2)  AS pib_per_capita_2022,
    e.despesa_saude                                 AS despesa_saude_2022,
    e.despesa_educacao                              AS despesa_educacao_2022,
    ROUND(e.despesa_saude    / NULLIF(m.populacao_2022, 0), 2) AS despesa_saude_per_capita_2022,
    ROUND(e.despesa_educacao / NULLIF(m.populacao_2022, 0), 2) AS despesa_educacao_per_capita_2022
FROM geo.municipios m
LEFT JOIN saude.sim_mortalidade s
    ON m.cod_ibge_7 / 10 = s.cod_municipio   -- SIM usa código IBGE 6 dígitos; geo usa 7 dígitos
LEFT JOIN economia.siconfi_municipios e
    ON e.cod_municipio = m.cod_ibge_7 AND e.ano = 2022
GROUP BY m.cod_ibge_7, m.cod_uf, m.nome, m.geom, m.geom_simplified,
         m.area_km2, m.populacao_2022, e.receita_total,
         e.transferencias_sus, e.pib, e.despesa_saude, e.despesa_educacao;

-- Índice espacial na vista materializada (recriado no REFRESH CONCURRENTLY)
CREATE UNIQUE INDEX IF NOT EXISTS idx_indicadores_municipio_pk
    ON api.indicadores_municipio (cod_ibge_7);
CREATE INDEX IF NOT EXISTS idx_indicadores_municipio_geom
    ON api.indicadores_municipio USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_indicadores_municipio_geom_simplified
    ON api.indicadores_municipio USING GIST (geom_simplified);

-- Vista UF com indicadores estaduais agregados
CREATE MATERIALIZED VIEW IF NOT EXISTS api.indicadores_uf AS
SELECT
    u.cod_uf,
    u.sigla,
    u.nome,
    u.regiao,
    u.geom,
    u.geom_simplified,
    u.area_km2,
    SUM(im.populacao_2022)               AS populacao_total,
    ROUND(AVG(im.taxa_mortalidade_2023), 1)              AS taxa_mortalidade_media,
    ROUND(AVG(im.taxa_homicidio_2023), 1)               AS taxa_homicidio_media,
    ROUND(AVG(im.mortalidade_cardiovascular_2023), 1)   AS mortalidade_cardiovascular_media,
    ROUND(AVG(im.mortalidade_cancer_2023), 1)           AS mortalidade_cancer_media,
    ROUND(AVG(im.mortalidade_respiratoria_2023), 1)     AS mortalidade_respiratoria_media,
    SUM(im.receita_municipal_2022)                      AS receita_estadual_total,
    SUM(im.transferencias_sus_2022)                     AS transferencias_sus_total,
    SUM(im.pib_2022)                                    AS pib_estadual,
    SUM(im.despesa_saude_2022)                          AS despesa_saude_estadual_2022,
    SUM(im.despesa_educacao_2022)                       AS despesa_educacao_estadual_2022
FROM geo.ufs u
LEFT JOIN api.indicadores_municipio im ON im.cod_uf = u.cod_uf
GROUP BY u.cod_uf, u.sigla, u.nome, u.regiao, u.geom, u.geom_simplified,
         u.area_km2;

CREATE UNIQUE INDEX IF NOT EXISTS idx_indicadores_uf_pk
    ON api.indicadores_uf (cod_uf);
CREATE INDEX IF NOT EXISTS idx_indicadores_uf_geom
    ON api.indicadores_uf USING GIST (geom);

-- ─────────────────────────────────────────────────────────────────────────────
-- SCHEMA: Educação
-- ─────────────────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS educacao;

-- ─────────────────────────────────────────────────────────────────────────────
-- TABELA: Saneamento básico — Censo IBGE 2022 (estático, sem filtro de ano)
-- Fonte: IBGE SIDRA tabelas 6803 (água), 6805 (esgoto), 6892 (lixo)
-- Código IBGE 7 dígitos (N6 = município)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS censo.domicilios_municipio (
    cod_municipio    INTEGER PRIMARY KEY,  -- 7 dígitos IBGE
    total_domicilios INTEGER,
    com_agua_rede    INTEGER,   -- ligados à rede geral de abastecimento
    com_esgoto_rede  INTEGER,   -- com esgotamento sanitário por rede geral
    com_coleta_lixo  INTEGER    -- com coleta de lixo por serviço de limpeza
);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABELA: Nascidos vivos — SINASC/DataSUS (por município-ano)
-- Fonte: PySUS SINASC grupo "DN"
-- CODMUNRES: 6 dígitos DataSUS — join com geo.municipios via cod_ibge_7 / 10
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS saude.sinasc_municipios (
    cod_municipio  INTEGER  NOT NULL,  -- 6 dígitos DataSUS
    cod_uf         SMALLINT NOT NULL,
    ano            SMALLINT NOT NULL,
    nascidos_vivos INTEGER,
    PRIMARY KEY (cod_municipio, ano)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABELA: Infraestrutura de saúde — CNES/DataSUS (por município-ano)
-- Fonte: PySUS CNES LT (leitos) + PF (profissionais)
-- CODUFMUN: 6 dígitos DataSUS — join com geo.municipios via cod_ibge_7 / 10
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS saude.cnes_municipios (
    cod_municipio  INTEGER  NOT NULL,  -- 6 dígitos DataSUS
    cod_uf         SMALLINT NOT NULL,
    ano            SMALLINT NOT NULL,
    leitos_sus     INTEGER,  -- leitos SUS (QT_SUS do grupo LT)
    leitos_total   INTEGER,  -- leitos totais (QT_EXIST do grupo LT)
    medicos        INTEGER,  -- médicos (CBO 22xx) do grupo PF
    PRIMARY KEY (cod_municipio, ano)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABELA: IDEB — INEP (por município-ano, anos ímpares)
-- Fonte: planilhas INEP download
-- Código IBGE 7 dígitos
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS educacao.ideb_municipios (
    cod_municipio       INTEGER NOT NULL,  -- 7 dígitos IBGE
    ano                 SMALLINT NOT NULL,
    ideb_anos_iniciais  FLOAT,  -- IDEB anos iniciais do ensino fundamental (0-10)
    ideb_anos_finais    FLOAT,  -- IDEB anos finais do ensino fundamental (0-10)
    PRIMARY KEY (cod_municipio, ano)
);
