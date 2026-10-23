-- =============================================================================
-- 06_populacao_raca_sexo_idade.sql
-- População do Censo 2022 por cor/raça × sexo × faixa etária × município
-- (SIDRA tabela 9606). Denominador exato das taxas de mortalidade filtradas.
-- Carregada por pipeline/load_populacao_raca_sexo_idade.py
-- =============================================================================

CREATE TABLE IF NOT EXISTS censo.populacao_rsi_municipio (
    cod_municipio  INTEGER  NOT NULL,  -- 7 dígitos
    cor_raca       SMALLINT NOT NULL,  -- 0 = total, 1=Branca 2=Preta 3=Amarela 4=Parda 5=Indígena
    sexo           CHAR(1)  NOT NULL,  -- 'M' | 'F'
    faixa_etaria   SMALLINT NOT NULL,  -- 0..17, encoding SIM
    populacao      INTEGER  NOT NULL,
    PRIMARY KEY (cod_municipio, cor_raca, sexo, faixa_etaria)
);

COMMENT ON TABLE censo.populacao_rsi_municipio IS
    'População por cor/raça × sexo × faixa etária × município (IBGE Censo 2022, SIDRA 9606). '
    'Denominador do mesmo subgrupo que o numerador nas taxas de mortalidade filtradas.';
