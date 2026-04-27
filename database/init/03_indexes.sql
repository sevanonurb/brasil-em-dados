-- =============================================================================
-- 03_indexes.sql
-- Índices espaciais e tabulares. Executado após 02_schema.sql.
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- Índices GiST em polígonos (bounding box queries via operador &&)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_ufs_geom
    ON geo.ufs USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_ufs_geom_simplified
    ON geo.ufs USING GIST (geom_simplified);

CREATE INDEX IF NOT EXISTS idx_municipios_geom
    ON geo.municipios USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_municipios_geom_simplified
    ON geo.municipios USING GIST (geom_simplified);

CREATE INDEX IF NOT EXISTS idx_municipios_cod_uf
    ON geo.municipios (cod_uf);

-- Índice GiST nos setores subdivididos (mais eficiente que nos originais)
-- Para geometrias menores (max 255 vértices), GiST tem bounding boxes mais tight
CREATE INDEX IF NOT EXISTS idx_setores_subdivididos_geom
    ON geo.setores_subdivididos USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_setores_subdivididos_cod_setor
    ON geo.setores_subdivididos (cod_setor);

-- ─────────────────────────────────────────────────────────────────────────────
-- Índices SP-GiST em pontos massivos (CNEFE — 111.1M pontos)
-- SP-GiST supera GiST para conjuntos de pontos densos e não sobrepostos
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_cnefe_geom_35
    ON censo.cnefe_enderecos_35 USING SPGIST (geom);

CREATE INDEX IF NOT EXISTS idx_cnefe_geom_33
    ON censo.cnefe_enderecos_33 USING SPGIST (geom);

CREATE INDEX IF NOT EXISTS idx_cnefe_geom_outros
    ON censo.cnefe_enderecos_outros USING SPGIST (geom);

CREATE INDEX IF NOT EXISTS idx_cnefe_cod_setor
    ON censo.cnefe_enderecos (cod_setor);

-- ─────────────────────────────────────────────────────────────────────────────
-- Índices nas tabelas fato (para partition pruning + filter pushdown)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_sim_municipio_ano
    ON saude.sim_mortalidade (cod_municipio, ano);

CREATE INDEX IF NOT EXISTS idx_sim_cid10
    ON saude.sim_mortalidade (cid10_capitulo, ano);

CREATE INDEX IF NOT EXISTS idx_sim_cor_raca_faixa
    ON saude.sim_mortalidade (cor_raca, faixa_etaria, ano)
    WHERE cor_raca IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sinesp_municipio_ano
    ON seguranca.sinesp_ocorrencias (cod_municipio, ano);

CREATE INDEX IF NOT EXISTS idx_sinesp_tipo_crime
    ON seguranca.sinesp_ocorrencias (tipo_crime, ano);

-- ─────────────────────────────────────────────────────────────────────────────
-- Estatísticas agressivas para o query planner
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE geo.municipios ALTER COLUMN cod_uf SET STATISTICS 500;
ALTER TABLE geo.municipios ALTER COLUMN geom SET STATISTICS 500;
ALTER TABLE saude.sim_mortalidade ALTER COLUMN cid10_capitulo SET STATISTICS 500;
ALTER TABLE saude.sim_mortalidade ALTER COLUMN ano SET STATISTICS 500;

-- Força análise estatística inicial
ANALYZE geo.ufs;
ANALYZE geo.municipios;
