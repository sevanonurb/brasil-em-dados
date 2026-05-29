-- =============================================================================
-- 04_tile_functions.sql
-- Funções PL/pgSQL para Martin v1.7 (assinatura obrigatória: z,x,y,query_params JSON).
-- Martin passa os query params da URL como JSON no 4º argumento.
-- Validação de domínio com tipos extraídos do JSON — sem concatenação de string.
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- Nível 1-2: Tiles de UFs (zoom 0-6)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION api.tiles_ufs(
    z            INT,
    x            INT,
    y            INT,
    query_params JSON DEFAULT '{}'
)
RETURNS bytea AS $$
DECLARE
    result      bytea;
    bbox_4674   geometry := ST_Transform(ST_TileEnvelope(z, x, y), 4674);
    bbox_3857   geometry := ST_TileEnvelope(z, x, y);
    v_metrica   TEXT     := COALESCE(query_params->>'metrica', 'taxa_mortalidade');
    v_ano       INTEGER  := COALESCE((query_params->>'ano')::INTEGER, 2023);
    v_cid10     TEXT     := NULLIF(query_params->>'cid10_capitulo', '');
    v_cor_raca  SMALLINT := (query_params->>'cor_raca')::SMALLINT;
    v_sexo      CHAR(1)  := NULLIF(query_params->>'sexo', '');
    v_faixa_min SMALLINT := COALESCE((query_params->>'faixa_etaria_min')::SMALLINT, 0);
    v_faixa_max SMALLINT := COALESCE((query_params->>'faixa_etaria_max')::SMALLINT, 17);
BEGIN
    SELECT ST_AsMVT(tile, 'ufs', 4096, 'geom_mvt')
    INTO result
    FROM (
        WITH mortalidade_agg AS (
            -- Agrega óbitos por UF com todos os filtros ativos.
            SELECT s.cod_uf, COUNT(*)::FLOAT8 AS contagem
            FROM saude.sim_mortalidade s
            WHERE s.ano = v_ano
              AND v_metrica IN ('taxa_mortalidade', 'taxa_homicidio')
              AND (
                  (v_metrica = 'taxa_mortalidade' AND (
                      v_cid10 IS NULL
                      OR (v_cid10 = 'suicidio' AND s.cid10_codigo >= 'X60' AND s.cid10_codigo < 'X85')
                      OR (v_cid10 <> 'suicidio' AND s.cid10_capitulo = v_cid10)
                  ))
                  OR
                  (v_metrica = 'taxa_homicidio' AND s.cid10_codigo >= 'X85' AND s.cid10_codigo < 'Y1')
              )
              AND (v_sexo IS NULL OR (v_sexo = 'M' AND s.sexo = '1') OR (v_sexo = 'F' AND s.sexo = '2'))
              AND (v_cor_raca IS NULL OR s.cor_raca = v_cor_raca)
              AND (v_faixa_min = 0 AND v_faixa_max = 17 OR s.faixa_etaria BETWEEN v_faixa_min AND v_faixa_max)
            GROUP BY s.cod_uf
        ),
        -- Denominador racial: soma das populações da raça selecionada em todos os
        -- municípios da UF. Vazio quando v_cor_raca IS NULL (COALESCE → -1).
        pop_raca AS (
            SELECT gm.cod_uf, SUM(pr.populacao)::FLOAT8 AS populacao
            FROM censo.populacao_raca_municipio pr
            JOIN geo.municipios gm ON gm.cod_ibge_7 = pr.cod_municipio
            WHERE pr.cor_raca = COALESCE(v_cor_raca, -1)
            GROUP BY gm.cod_uf
        ),
        -- Denominador etário: soma das faixas selecionadas por UF.
        -- Vazio quando intervalo padrão (0-17) — condição booleana é FALSE.
        pop_faixa AS (
            SELECT gm.cod_uf, SUM(pf.populacao)::FLOAT8 AS populacao
            FROM censo.populacao_faixa_municipio pf
            JOIN geo.municipios gm ON gm.cod_ibge_7 = pf.cod_municipio
            WHERE pf.faixa_etaria BETWEEN v_faixa_min AND v_faixa_max
              AND (v_faixa_min <> 0 OR v_faixa_max <> 17)
            GROUP BY gm.cod_uf
        )
        SELECT
            u.cod_uf,
            u.sigla,
            u.nome,
            u.regiao,
            u.populacao_2022                        AS populacao_total,
            econ.transferencias_sus_total,
            econ.pib_estadual,
            econ.receita_estadual_total,
            CASE
                WHEN v_metrica IN ('taxa_mortalidade', 'taxa_homicidio') THEN
                    ROUND((COALESCE(ma.contagem, 0) * 100000.0 / NULLIF(
                        CASE
                            -- Ambos os filtros: estimativa proporcional (raça × faixa / total)
                            WHEN v_cor_raca IS NOT NULL AND (v_faixa_min <> 0 OR v_faixa_max <> 17) THEN
                                COALESCE(pr.populacao, 0.0) * COALESCE(pf.populacao, 0.0)
                                / NULLIF(u.populacao_2022::FLOAT8, 0.0)
                            -- Só raça: usa população da raça na UF
                            WHEN v_cor_raca IS NOT NULL THEN
                                COALESCE(pr.populacao, u.populacao_2022::FLOAT8)
                            -- Só faixa etária: usa soma das faixas na UF
                            WHEN v_faixa_min <> 0 OR v_faixa_max <> 17 THEN
                                COALESCE(pf.populacao, u.populacao_2022::FLOAT8)
                            -- Sem filtro demográfico: população total da UF
                            ELSE u.populacao_2022::FLOAT8
                        END
                    , 0.0))::NUMERIC, 1)::FLOAT8
                WHEN v_metrica = 'pib_per_capita' THEN
                    econ.pib_estadual / NULLIF(u.populacao_2022::FLOAT8, 0)
                WHEN v_metrica = 'receita_per_capita' THEN
                    econ.receita_estadual_total / NULLIF(u.populacao_2022::FLOAT8, 0)
                WHEN v_metrica = 'despesa_saude_per_capita' THEN
                    econ.despesa_saude_estadual / NULLIF(u.populacao_2022::FLOAT8, 0)
                WHEN v_metrica = 'despesa_educacao_per_capita' THEN
                    econ.despesa_educacao_estadual / NULLIF(u.populacao_2022::FLOAT8, 0)
                WHEN v_metrica = 'densidade_pop' THEN
                    u.populacao_2022::FLOAT8 / NULLIF(u.area_km2::FLOAT8, 0)
                WHEN v_metrica = 'acesso_agua' THEN
                    san.com_agua_rede_total / NULLIF(san.total_domicilios_total, 0) * 100
                WHEN v_metrica = 'acesso_esgoto' THEN
                    san.com_esgoto_rede_total / NULLIF(san.total_domicilios_total, 0) * 100
                WHEN v_metrica = 'coleta_lixo' THEN
                    san.com_coleta_lixo_total / NULLIF(san.total_domicilios_total, 0) * 100
                WHEN v_metrica = 'taxa_natalidade' THEN
                    sinasc_uf.nascidos_vivos_total / NULLIF(u.populacao_2022::FLOAT8, 0) * 1000
                WHEN v_metrica = 'leitos_sus_por_1k' THEN
                    cnes_uf.leitos_sus_total / NULLIF(u.populacao_2022::FLOAT8, 0) * 1000
                WHEN v_metrica = 'medicos_por_10k' THEN
                    cnes_uf.medicos_total / NULLIF(u.populacao_2022::FLOAT8, 0) * 10000
                WHEN v_metrica = 'ideb_anos_iniciais' THEN
                    ideb_uf.ideb_anos_iniciais_media
                WHEN v_metrica = 'ideb_anos_finais' THEN
                    ideb_uf.ideb_anos_finais_media
                ELSE (
                    -- Métricas adicionais: lê de api.metricas_municipio (agregação UF = média)
                    SELECT AVG(mm.valor)::FLOAT8
                    FROM api.metricas_municipio mm
                    JOIN geo.municipios gm ON gm.cod_ibge_7 = mm.cod_municipio
                    WHERE mm.metrica = v_metrica
                      AND mm.ano = v_ano
                      AND gm.cod_uf = u.cod_uf
                )
            END AS valor_metrica,
            ST_AsMVTGeom(
                ST_Transform(
                    CASE WHEN z < 4 THEN
                        COALESCE(u.geom_simplified, u.geom)
                    ELSE u.geom END,
                    3857
                ),
                bbox_3857, 4096, 64, true
            ) AS geom_mvt
        FROM geo.ufs u
        LEFT JOIN (
            -- Agrega dados econômicos por UF para o ano selecionado
            SELECT gm.cod_uf,
                   SUM(e.pib)::FLOAT8                 AS pib_estadual,
                   SUM(e.receita_total)::FLOAT8        AS receita_estadual_total,
                   SUM(e.transferencias_sus)::FLOAT8   AS transferencias_sus_total,
                   SUM(e.despesa_saude)::FLOAT8        AS despesa_saude_estadual,
                   SUM(e.despesa_educacao)::FLOAT8     AS despesa_educacao_estadual
            FROM economia.siconfi_municipios e
            JOIN geo.municipios gm ON gm.cod_ibge_7 = e.cod_municipio
            WHERE e.ano = v_ano
            GROUP BY gm.cod_uf
        ) econ ON econ.cod_uf = u.cod_uf
        LEFT JOIN (
            -- Saneamento: Censo IBGE 2022 (estático — sem filtro de ano)
            SELECT gm.cod_uf,
                   SUM(dm.com_agua_rede)::FLOAT8    AS com_agua_rede_total,
                   SUM(dm.com_esgoto_rede)::FLOAT8  AS com_esgoto_rede_total,
                   SUM(dm.com_coleta_lixo)::FLOAT8  AS com_coleta_lixo_total,
                   SUM(dm.total_domicilios)::FLOAT8 AS total_domicilios_total
            FROM censo.domicilios_municipio dm
            JOIN geo.municipios gm ON gm.cod_ibge_7 = dm.cod_municipio
            GROUP BY gm.cod_uf
        ) san ON san.cod_uf = u.cod_uf
        LEFT JOIN (
            -- SINASC: nascidos vivos por UF para o ano selecionado
            SELECT gm.cod_uf, SUM(sn.nascidos_vivos)::FLOAT8 AS nascidos_vivos_total
            FROM saude.sinasc_municipios sn
            JOIN geo.municipios gm ON gm.cod_ibge_7 / 10 = sn.cod_municipio
            WHERE sn.ano = v_ano
            GROUP BY gm.cod_uf
        ) sinasc_uf ON sinasc_uf.cod_uf = u.cod_uf
        LEFT JOIN (
            -- CNES: leitos e médicos por UF para o ano selecionado
            SELECT gm.cod_uf,
                   SUM(cn.leitos_sus)::FLOAT8 AS leitos_sus_total,
                   SUM(cn.medicos)::FLOAT8    AS medicos_total
            FROM saude.cnes_municipios cn
            JOIN geo.municipios gm ON gm.cod_ibge_7 / 10 = cn.cod_municipio
            WHERE cn.ano = v_ano
            GROUP BY gm.cod_uf
        ) cnes_uf ON cnes_uf.cod_uf = u.cod_uf
        LEFT JOIN (
            -- IDEB: média municipal por UF para o ano selecionado
            SELECT gm.cod_uf,
                   AVG(ideb.ideb_anos_iniciais)::FLOAT8 AS ideb_anos_iniciais_media,
                   AVG(ideb.ideb_anos_finais)::FLOAT8   AS ideb_anos_finais_media
            FROM educacao.ideb_municipios ideb
            JOIN geo.municipios gm ON gm.cod_ibge_7 = ideb.cod_municipio
            WHERE ideb.ano = v_ano
            GROUP BY gm.cod_uf
        ) ideb_uf ON ideb_uf.cod_uf = u.cod_uf
        LEFT JOIN mortalidade_agg ma ON ma.cod_uf = u.cod_uf
        LEFT JOIN pop_raca pr        ON pr.cod_uf = u.cod_uf
        LEFT JOIN pop_faixa pf       ON pf.cod_uf = u.cod_uf
        WHERE u.geom && bbox_4674
    ) tile
    WHERE geom_mvt IS NOT NULL;

    RETURN COALESCE(result, ''::bytea);
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE;

-- ─────────────────────────────────────────────────────────────────────────────
-- Nível 2-3: Tiles de municípios com cross-filter (zoom 5-12)
-- Parâmetros via JSON: {"ano":2023,"cid10":"I","cor_raca":2,"metrica":"taxa_mortalidade"}
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION api.tiles_municipios(
    z            INT,
    x            INT,
    y            INT,
    query_params JSON DEFAULT '{}'
)
RETURNS bytea AS $$
DECLARE
    result      bytea;
    bbox_4674   geometry := ST_Transform(ST_TileEnvelope(z, x, y), 4674);
    bbox_3857   geometry := ST_TileEnvelope(z, x, y);
    v_ano       SMALLINT := COALESCE((query_params->>'ano')::SMALLINT, 2023);
    v_cod_uf    SMALLINT := (query_params->>'cod_uf')::SMALLINT;
    v_cid10     TEXT     := NULLIF(query_params->>'cid10_capitulo', '');
    v_cor_raca  SMALLINT := (query_params->>'cor_raca')::SMALLINT;
    v_metrica   TEXT     := COALESCE(query_params->>'metrica', 'taxa_mortalidade');
    v_faixa_min SMALLINT := COALESCE((query_params->>'faixa_etaria_min')::SMALLINT, 0);
    v_faixa_max SMALLINT := COALESCE((query_params->>'faixa_etaria_max')::SMALLINT, 17);
    v_sexo      CHAR(1)  := NULLIF(query_params->>'sexo', '');
BEGIN
    -- Validações de domínio
    IF v_cod_uf IS NOT NULL AND v_cod_uf NOT BETWEEN 11 AND 53 THEN
        RAISE EXCEPTION 'cod_uf inválido: %', v_cod_uf;
    END IF;
    IF v_cid10 IS NOT NULL AND v_cid10 !~ '^([A-Z]|suicidio)$' THEN
        RAISE EXCEPTION 'cid10_capitulo inválido: %', v_cid10;
    END IF;
    IF v_cor_raca IS NOT NULL AND v_cor_raca NOT BETWEEN 1 AND 5 THEN
        RAISE EXCEPTION 'cor_raca inválido: %', v_cor_raca;
    END IF;

    SELECT ST_AsMVT(tile, 'municipios', 4096, 'geom_mvt')
    INTO result
    FROM (
        WITH mortalidade_agg AS (
            SELECT s.cod_municipio, COUNT(*)::FLOAT8 AS contagem
            FROM saude.sim_mortalidade s
            WHERE s.ano = v_ano
              AND v_metrica IN ('taxa_mortalidade', 'taxa_homicidio')
              AND (
                  (v_metrica = 'taxa_mortalidade' AND (
                      v_cid10 IS NULL
                      OR (v_cid10 = 'suicidio' AND s.cid10_codigo >= 'X60' AND s.cid10_codigo < 'X85')
                      OR (v_cid10 <> 'suicidio' AND s.cid10_capitulo = v_cid10)
                  ))
                  OR
                  (v_metrica = 'taxa_homicidio' AND s.cid10_codigo >= 'X85' AND s.cid10_codigo < 'Y1')
              )
              AND (v_sexo IS NULL OR (v_sexo = 'M' AND s.sexo = '1') OR (v_sexo = 'F' AND s.sexo = '2'))
              AND (v_cor_raca IS NULL OR s.cor_raca = v_cor_raca)
              AND (v_faixa_min = 0 AND v_faixa_max = 17 OR s.faixa_etaria BETWEEN v_faixa_min AND v_faixa_max)
            GROUP BY s.cod_municipio
        ),
        -- Denominador racial por município (vazio quando v_cor_raca IS NULL)
        pop_raca AS (
            SELECT pr.cod_municipio, pr.populacao::FLOAT8 AS populacao
            FROM censo.populacao_raca_municipio pr
            WHERE pr.cor_raca = COALESCE(v_cor_raca, -1)
        ),
        -- Denominador etário por município (vazio quando intervalo padrão 0-17)
        pop_faixa AS (
            SELECT pf.cod_municipio, SUM(pf.populacao)::FLOAT8 AS populacao
            FROM censo.populacao_faixa_municipio pf
            WHERE pf.faixa_etaria BETWEEN v_faixa_min AND v_faixa_max
              AND (v_faixa_min <> 0 OR v_faixa_max <> 17)
            GROUP BY pf.cod_municipio
        )
        SELECT
            m.cod_ibge_7,
            m.cod_uf,
            m.nome                              AS nome_municipio,
            m.populacao_2022,
            e.transferencias_sus::FLOAT8        AS transferencias_sus,
            e.despesa_saude::FLOAT8             AS despesa_saude,
            e.despesa_educacao::FLOAT8          AS despesa_educacao,
            CASE
                WHEN v_metrica IN ('taxa_mortalidade', 'taxa_homicidio') THEN
                    ROUND((COALESCE(ma.contagem, 0) * 100000.0 / NULLIF(
                        CASE
                            WHEN v_cor_raca IS NOT NULL AND (v_faixa_min <> 0 OR v_faixa_max <> 17) THEN
                                -- Ambos: estimativa proporcional raça × faixa / total
                                COALESCE(pr.populacao, 0.0) * COALESCE(pf.populacao, 0.0)
                                / NULLIF(m.populacao_2022::FLOAT8, 0.0)
                            WHEN v_cor_raca IS NOT NULL THEN
                                -- Só raça: usa população da raça neste município
                                COALESCE(pr.populacao, m.populacao_2022::FLOAT8)
                            WHEN v_faixa_min <> 0 OR v_faixa_max <> 17 THEN
                                -- Só faixa etária: usa soma das faixas neste município
                                COALESCE(pf.populacao, m.populacao_2022::FLOAT8)
                            ELSE
                                -- Sem filtro demográfico: população total
                                m.populacao_2022::FLOAT8
                        END
                    , 0.0))::NUMERIC, 1)::FLOAT8
                WHEN v_metrica = 'pib_per_capita' THEN
                    e.pib::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0)
                WHEN v_metrica = 'receita_per_capita' THEN
                    e.receita_total::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0)
                WHEN v_metrica = 'despesa_saude_per_capita' THEN
                    e.despesa_saude::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0)
                WHEN v_metrica = 'despesa_educacao_per_capita' THEN
                    e.despesa_educacao::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0)
                WHEN v_metrica = 'densidade_pop' THEN
                    m.populacao_2022::FLOAT8 / NULLIF(m.area_km2::FLOAT8, 0)
                WHEN v_metrica = 'acesso_agua' THEN
                    dm.com_agua_rede::FLOAT8 / NULLIF(dm.total_domicilios::FLOAT8, 0) * 100
                WHEN v_metrica = 'acesso_esgoto' THEN
                    dm.com_esgoto_rede::FLOAT8 / NULLIF(dm.total_domicilios::FLOAT8, 0) * 100
                WHEN v_metrica = 'coleta_lixo' THEN
                    dm.com_coleta_lixo::FLOAT8 / NULLIF(dm.total_domicilios::FLOAT8, 0) * 100
                WHEN v_metrica = 'taxa_natalidade' THEN
                    sn.nascidos_vivos::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0) * 1000
                WHEN v_metrica = 'leitos_sus_por_1k' THEN
                    cn.leitos_sus::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0) * 1000
                WHEN v_metrica = 'medicos_por_10k' THEN
                    cn.medicos::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0) * 10000
                WHEN v_metrica = 'ideb_anos_iniciais' THEN
                    ideb.ideb_anos_iniciais::FLOAT8
                WHEN v_metrica = 'ideb_anos_finais' THEN
                    ideb.ideb_anos_finais::FLOAT8
                ELSE (
                    -- Métricas adicionais: lê de api.metricas_municipio
                    SELECT mm.valor FROM api.metricas_municipio mm
                    WHERE mm.cod_municipio = m.cod_ibge_7
                      AND mm.metrica = v_metrica
                      AND mm.ano = v_ano
                    LIMIT 1
                )
            END AS valor_metrica,
            ST_AsMVTGeom(
                ST_Transform(
                    CASE WHEN z < 8 THEN
                        COALESCE(m.geom_simplified, m.geom)
                    ELSE m.geom END,
                    3857
                ),
                bbox_3857, 4096, 64, true
            ) AS geom_mvt
        FROM geo.municipios m
        LEFT JOIN economia.siconfi_municipios e
            ON e.cod_municipio = m.cod_ibge_7 AND e.ano = v_ano
        LEFT JOIN censo.domicilios_municipio dm ON dm.cod_municipio = m.cod_ibge_7
        LEFT JOIN saude.sinasc_municipios sn
            ON sn.cod_municipio = m.cod_ibge_7 / 10 AND sn.ano = v_ano
        LEFT JOIN saude.cnes_municipios cn
            ON cn.cod_municipio = m.cod_ibge_7 / 10 AND cn.ano = v_ano
        LEFT JOIN educacao.ideb_municipios ideb
            ON ideb.cod_municipio = m.cod_ibge_7 AND ideb.ano = v_ano
        LEFT JOIN mortalidade_agg ma ON ma.cod_municipio = m.cod_ibge_7 / 10
        LEFT JOIN pop_raca pr        ON pr.cod_municipio = m.cod_ibge_7
        LEFT JOIN pop_faixa pf       ON pf.cod_municipio = m.cod_ibge_7
        WHERE m.geom && bbox_4674
          AND (v_cod_uf IS NULL OR m.cod_uf = v_cod_uf)
    ) tile
    WHERE geom_mvt IS NOT NULL;

    RETURN COALESCE(result, ''::bytea);
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE;

-- ─────────────────────────────────────────────────────────────────────────────
-- Nível 3-4: Tiles de Setores Censitários (zoom 9-15)
-- densidade_pop usa dados próprios do setor (Censo 2022 por setor).
-- Outras métricas herdam o valor do município (dados SIM/IBGE só existem em nível municipal).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION api.tiles_setores(
    z            INT,
    x            INT,
    y            INT,
    query_params JSON DEFAULT '{}'
)
RETURNS bytea AS $$
DECLARE
    result        bytea;
    bbox_4674     geometry := ST_Transform(ST_TileEnvelope(z, x, y), 4674);
    bbox_3857     geometry := ST_TileEnvelope(z, x, y);
    v_cod_mun     INTEGER  := (query_params->>'cod_municipio')::INTEGER;
    v_ano         SMALLINT := COALESCE((query_params->>'ano')::SMALLINT, 2023);
    v_cid10       TEXT     := NULLIF(query_params->>'cid10_capitulo', '');
    v_cor_raca    SMALLINT := (query_params->>'cor_raca')::SMALLINT;
    v_metrica     TEXT     := COALESCE(query_params->>'metrica', 'taxa_mortalidade');
    v_faixa_min   SMALLINT := COALESCE((query_params->>'faixa_etaria_min')::SMALLINT, 0);
    v_faixa_max   SMALLINT := COALESCE((query_params->>'faixa_etaria_max')::SMALLINT, 17);
    v_sexo        CHAR(1)  := NULLIF(query_params->>'sexo', '');
BEGIN
    -- z < 6: centroides (dots) — todos os setores como pontos coloridos.
    -- Usa fontes primárias com v_ano dinâmico (sem materialized view hardcoded).
    IF z < 6 THEN
        SELECT ST_AsMVT(tile, 'setores', 4096, 'geom_mvt')
        INTO result
        FROM (
            WITH mortalidade_mun AS (
                SELECT s.cod_municipio, COUNT(*)::FLOAT8 AS contagem
                FROM saude.sim_mortalidade s
                WHERE s.ano = v_ano
                  AND v_metrica IN ('taxa_mortalidade', 'taxa_homicidio')
                  AND (
                      (v_metrica = 'taxa_mortalidade' AND (
                          v_cid10 IS NULL
                          OR (v_cid10 = 'suicidio' AND s.cid10_codigo >= 'X60' AND s.cid10_codigo < 'X85')
                          OR (v_cid10 <> 'suicidio' AND s.cid10_capitulo = v_cid10)
                      ))
                      OR (v_metrica = 'taxa_homicidio' AND s.cid10_codigo >= 'X85' AND s.cid10_codigo < 'Y1')
                  )
                GROUP BY s.cod_municipio
            )
            SELECT
                sc.cod_setor,
                sc.cod_municipio,
                sc.populacao_total,
                CASE
                    WHEN v_metrica IN ('taxa_mortalidade', 'taxa_homicidio') THEN
                        ROUND((COALESCE(ma.contagem, 0) * 100000.0
                               / NULLIF(m.populacao_2022::FLOAT8, 0))::NUMERIC, 1)::FLOAT8
                    WHEN v_metrica = 'pib_per_capita' THEN
                        e.pib::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0)
                    WHEN v_metrica = 'receita_per_capita' THEN
                        e.receita_total::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0)
                    WHEN v_metrica = 'despesa_saude_per_capita' THEN
                        e.despesa_saude::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0)
                    WHEN v_metrica = 'despesa_educacao_per_capita' THEN
                        e.despesa_educacao::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0)
                    WHEN v_metrica = 'densidade_pop' THEN
                        sc.populacao_total::FLOAT8 / NULLIF(sc.area_km2, 0)
                    ELSE (
                        SELECT mm.valor FROM api.metricas_municipio mm
                        WHERE mm.cod_municipio = sc.cod_municipio
                          AND mm.metrica = v_metrica
                          AND mm.ano = v_ano
                        LIMIT 1
                    )
                END AS valor_metrica,
                ST_AsMVTGeom(ST_Centroid(sc.geom_3857), bbox_3857, 4096, 4, true) AS geom_mvt
            FROM geo.setores_censitarios sc
            JOIN geo.municipios m ON m.cod_ibge_7 = sc.cod_municipio
            LEFT JOIN economia.siconfi_municipios e
                ON e.cod_municipio = sc.cod_municipio AND e.ano = v_ano
            LEFT JOIN mortalidade_mun ma ON ma.cod_municipio = sc.cod_municipio / 10
            WHERE sc.geom_3857 && bbox_3857
              AND (v_cod_mun IS NULL OR sc.cod_municipio = v_cod_mun)
        ) tile
        WHERE geom_mvt IS NOT NULL;
        RETURN COALESCE(result, ''::bytea);
    END IF;

    -- 6 <= z < 9: polígonos territoriais completos.
    -- Usa fontes primárias com v_ano dinâmico (sem materialized view hardcoded).
    IF z < 9 THEN
        SELECT ST_AsMVT(tile, 'setores', 4096, 'geom_mvt')
        INTO result
        FROM (
            WITH mortalidade_mun AS (
                SELECT s.cod_municipio, COUNT(*)::FLOAT8 AS contagem
                FROM saude.sim_mortalidade s
                WHERE s.ano = v_ano
                  AND v_metrica IN ('taxa_mortalidade', 'taxa_homicidio')
                  AND (
                      (v_metrica = 'taxa_mortalidade' AND (
                          v_cid10 IS NULL
                          OR (v_cid10 = 'suicidio' AND s.cid10_codigo >= 'X60' AND s.cid10_codigo < 'X85')
                          OR (v_cid10 <> 'suicidio' AND s.cid10_capitulo = v_cid10)
                      ))
                      OR (v_metrica = 'taxa_homicidio' AND s.cid10_codigo >= 'X85' AND s.cid10_codigo < 'Y1')
                  )
                GROUP BY s.cod_municipio
            )
            SELECT
                sc.cod_setor,
                sc.cod_municipio,
                sc.populacao_total,
                CASE
                    WHEN v_metrica IN ('taxa_mortalidade', 'taxa_homicidio') THEN
                        ROUND((COALESCE(ma.contagem, 0) * 100000.0
                               / NULLIF(m.populacao_2022::FLOAT8, 0))::NUMERIC, 1)::FLOAT8
                    WHEN v_metrica = 'pib_per_capita' THEN
                        e.pib::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0)
                    WHEN v_metrica = 'receita_per_capita' THEN
                        e.receita_total::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0)
                    WHEN v_metrica = 'despesa_saude_per_capita' THEN
                        e.despesa_saude::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0)
                    WHEN v_metrica = 'despesa_educacao_per_capita' THEN
                        e.despesa_educacao::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0)
                    WHEN v_metrica = 'densidade_pop' THEN
                        sc.populacao_total::FLOAT8 / NULLIF(sc.area_km2, 0)
                    ELSE (
                        SELECT mm.valor FROM api.metricas_municipio mm
                        WHERE mm.cod_municipio = sc.cod_municipio
                          AND mm.metrica = v_metrica
                          AND mm.ano = v_ano
                        LIMIT 1
                    )
                END AS valor_metrica,
                ST_AsMVTGeom(sc.geom_3857, bbox_3857, 4096, 4, true) AS geom_mvt
            FROM geo.setores_censitarios sc
            JOIN geo.municipios m ON m.cod_ibge_7 = sc.cod_municipio
            LEFT JOIN economia.siconfi_municipios e
                ON e.cod_municipio = sc.cod_municipio AND e.ano = v_ano
            LEFT JOIN mortalidade_mun ma ON ma.cod_municipio = sc.cod_municipio / 10
            WHERE sc.geom_3857 && bbox_3857
              AND (v_cod_mun IS NULL OR sc.cod_municipio = v_cod_mun)
        ) tile
        WHERE geom_mvt IS NOT NULL;
        RETURN COALESCE(result, ''::bytea);
    END IF;

    SELECT ST_AsMVT(tile, 'setores', 4096, 'geom_mvt')
    INTO result
    FROM (
        WITH setores_no_tile AS (
            -- Lookup rápido via tabela subdividida com índice GIST
            SELECT DISTINCT ss.cod_setor, ss.cod_municipio
            FROM geo.setores_subdivididos ss
            WHERE ss.geom && bbox_4674
              AND (v_cod_mun IS NULL OR ss.cod_municipio = v_cod_mun)
        ),
        -- Municípios presentes no tile: filtra CTEs pesados ao subset relevante
        muns_no_tile AS (
            SELECT DISTINCT cod_municipio FROM setores_no_tile
        ),
        mortalidade_agg AS (
            SELECT s.cod_municipio, COUNT(*)::FLOAT8 AS contagem
            FROM saude.sim_mortalidade s
            WHERE s.ano = v_ano
              AND s.cod_municipio IN (SELECT mt.cod_municipio / 10 FROM muns_no_tile mt)
              AND v_metrica IN ('taxa_mortalidade', 'taxa_homicidio')
              AND (
                  (v_metrica = 'taxa_mortalidade' AND (
                      v_cid10 IS NULL
                      OR (v_cid10 = 'suicidio' AND s.cid10_codigo >= 'X60' AND s.cid10_codigo < 'X85')
                      OR (v_cid10 <> 'suicidio' AND s.cid10_capitulo = v_cid10)
                  ))
                  OR
                  (v_metrica = 'taxa_homicidio' AND s.cid10_codigo >= 'X85' AND s.cid10_codigo < 'Y1')
              )
              AND (v_sexo IS NULL OR (v_sexo = 'M' AND s.sexo = '1') OR (v_sexo = 'F' AND s.sexo = '2'))
              AND (v_cor_raca IS NULL OR s.cor_raca = v_cor_raca)
              AND (v_faixa_min = 0 AND v_faixa_max = 17 OR s.faixa_etaria BETWEEN v_faixa_min AND v_faixa_max)
            GROUP BY s.cod_municipio
        ),
        pop_raca AS (
            SELECT pr.cod_municipio, pr.populacao::FLOAT8 AS populacao
            FROM censo.populacao_raca_municipio pr
            WHERE pr.cor_raca = COALESCE(v_cor_raca, -1)
              AND pr.cod_municipio IN (SELECT mt.cod_municipio FROM muns_no_tile mt)
        ),
        pop_faixa AS (
            SELECT pf.cod_municipio, SUM(pf.populacao)::FLOAT8 AS populacao
            FROM censo.populacao_faixa_municipio pf
            WHERE pf.faixa_etaria BETWEEN v_faixa_min AND v_faixa_max
              AND (v_faixa_min <> 0 OR v_faixa_max <> 17)
              AND pf.cod_municipio IN (SELECT mt.cod_municipio FROM muns_no_tile mt)
            GROUP BY pf.cod_municipio
        )
        SELECT
            sc.cod_setor,
            sc.cod_municipio,
            sc.tipo_setor,
            sc.domicilios_total,
            sc.populacao_total,
            CASE
                WHEN v_metrica IN ('taxa_mortalidade', 'taxa_homicidio') THEN
                    ROUND((COALESCE(ma.contagem, 0) * 100000.0 / NULLIF(
                        CASE
                            WHEN v_cor_raca IS NOT NULL AND (v_faixa_min <> 0 OR v_faixa_max <> 17) THEN
                                COALESCE(pr.populacao, 0.0) * COALESCE(pf.populacao, 0.0)
                                / NULLIF(m.populacao_2022::FLOAT8, 0.0)
                            WHEN v_cor_raca IS NOT NULL THEN
                                COALESCE(pr.populacao, m.populacao_2022::FLOAT8)
                            WHEN v_faixa_min <> 0 OR v_faixa_max <> 17 THEN
                                COALESCE(pf.populacao, m.populacao_2022::FLOAT8)
                            ELSE
                                m.populacao_2022::FLOAT8
                        END
                    , 0.0))::NUMERIC, 1)::FLOAT8
                WHEN v_metrica = 'pib_per_capita' THEN
                    e.pib::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0)
                WHEN v_metrica = 'receita_per_capita' THEN
                    e.receita_total::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0)
                WHEN v_metrica = 'despesa_saude_per_capita' THEN
                    e.despesa_saude::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0)
                WHEN v_metrica = 'despesa_educacao_per_capita' THEN
                    e.despesa_educacao::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0)
                -- densidade_pop: dado genuíno por setor censitário (Censo 2022)
                WHEN v_metrica = 'densidade_pop' THEN
                    (sc.populacao_total::FLOAT8 / NULLIF(sc.area_km2, 0))
                WHEN v_metrica = 'acesso_agua' THEN
                    dm.com_agua_rede::FLOAT8 / NULLIF(dm.total_domicilios::FLOAT8, 0) * 100
                WHEN v_metrica = 'acesso_esgoto' THEN
                    dm.com_esgoto_rede::FLOAT8 / NULLIF(dm.total_domicilios::FLOAT8, 0) * 100
                WHEN v_metrica = 'coleta_lixo' THEN
                    dm.com_coleta_lixo::FLOAT8 / NULLIF(dm.total_domicilios::FLOAT8, 0) * 100
                WHEN v_metrica = 'taxa_natalidade' THEN
                    sn.nascidos_vivos::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0) * 1000
                WHEN v_metrica = 'leitos_sus_por_1k' THEN
                    cn.leitos_sus::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0) * 1000
                WHEN v_metrica = 'medicos_por_10k' THEN
                    cn.medicos::FLOAT8 / NULLIF(m.populacao_2022::FLOAT8, 0) * 10000
                WHEN v_metrica = 'ideb_anos_iniciais' THEN
                    ideb.ideb_anos_iniciais::FLOAT8
                WHEN v_metrica = 'ideb_anos_finais' THEN
                    ideb.ideb_anos_finais::FLOAT8
                ELSE (
                    -- Métricas adicionais: herda valor do município
                    SELECT mm.valor FROM api.metricas_municipio mm
                    WHERE mm.cod_municipio = sc.cod_municipio
                      AND mm.metrica = v_metrica
                      AND mm.ano = v_ano
                    LIMIT 1
                )
            END AS valor_metrica,
            -- geom_3857_simplified: pré-projetada e simplificada (~30m) para zoom 9-12
            ST_AsMVTGeom(sc.geom_3857_simplified, bbox_3857, 4096, 16, true) AS geom_mvt
        FROM geo.setores_censitarios sc
        INNER JOIN setores_no_tile snt ON snt.cod_setor = sc.cod_setor
        -- Município: join 7-dígitos (setores) com 7-dígitos (municipios)
        JOIN geo.municipios m ON m.cod_ibge_7 = sc.cod_municipio
        LEFT JOIN economia.siconfi_municipios e
            ON e.cod_municipio = sc.cod_municipio AND e.ano = v_ano
        LEFT JOIN censo.domicilios_municipio dm ON dm.cod_municipio = sc.cod_municipio
        LEFT JOIN saude.sinasc_municipios sn
            ON sn.cod_municipio = sc.cod_municipio / 10 AND sn.ano = v_ano
        LEFT JOIN saude.cnes_municipios cn
            ON cn.cod_municipio = sc.cod_municipio / 10 AND cn.ano = v_ano
        LEFT JOIN educacao.ideb_municipios ideb
            ON ideb.cod_municipio = sc.cod_municipio AND ideb.ano = v_ano
        -- Mortalidade: 6-dígitos (sim) ← 7-dígitos (setor) / 10
        LEFT JOIN mortalidade_agg ma ON ma.cod_municipio = sc.cod_municipio / 10
        LEFT JOIN pop_raca pr        ON pr.cod_municipio = sc.cod_municipio
        LEFT JOIN pop_faixa pf       ON pf.cod_municipio = sc.cod_municipio
    ) tile
    WHERE geom_mvt IS NOT NULL;

    RETURN COALESCE(result, ''::bytea);
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE;

-- ─────────────────────────────────────────────────────────────────────────────
-- Nível 4: Pontos CNEFE (zoom 13+) — LOD dinâmico por zoom
-- z13-14: pontos esparsados (baixo limite) para visão de bairro
-- z15:    densidade média
-- z16+:   todos os pontos (até 10k por tile)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION api.tiles_cnefe(
    z            INT,
    x            INT,
    y            INT,
    query_params JSON DEFAULT '{}'
)
RETURNS bytea AS $$
DECLARE
    result    bytea;
    bbox_4674 geometry := ST_Transform(ST_TileEnvelope(z, x, y), 4674);
    bbox_3857 geometry := ST_TileEnvelope(z, x, y);
    v_cod_mun INTEGER  := (query_params->>'cod_municipio')::INTEGER;
    v_especie SMALLINT := (query_params->>'especie')::SMALLINT;
    v_limit   INTEGER;
BEGIN
    -- Zooms baixos (< 13): centroids de setores como proxy de densidade de endereços.
    -- Amostragem agressiva para manter tiles < 200KB.
    IF z < 13 THEN
        SELECT ST_AsMVT(tile, 'cnefe', 4096, 'geom_mvt')
        INTO result
        FROM (
            SELECT
                sc.cod_setor,
                sc.cod_municipio,
                ST_AsMVTGeom(ST_Centroid(sc.geom_3857), bbox_3857, 4096, 0, true) AS geom_mvt
            FROM geo.setores_censitarios sc
            WHERE sc.geom_3857 && bbox_3857
              AND (v_cod_mun IS NULL OR sc.cod_municipio = v_cod_mun)
              AND CASE
                  WHEN z <= 4 THEN sc.cod_setor % 16 = 0
                  WHEN z  = 5 THEN sc.cod_setor % 8  = 0
                  WHEN z <= 7 THEN sc.cod_setor % 4  = 0
                  WHEN z <= 9 THEN sc.cod_setor % 2  = 0
                  ELSE TRUE
              END
        ) tile
        WHERE geom_mvt IS NOT NULL;
        RETURN COALESCE(result, ''::bytea);
    END IF;

    -- Limite dinâmico: menos pontos em zooms baixos (dot density overview)
    v_limit := CASE
        WHEN z < 14 THEN 800
        WHEN z < 15 THEN 2000
        WHEN z < 16 THEN 5000
        ELSE 10000
    END;

    SELECT ST_AsMVT(tile, 'cnefe', 4096, 'geom_mvt')
    INTO result
    FROM (
        SELECT
            c.cod_setor,
            c.tipo_logradouro,
            c.especie,
            ST_AsMVTGeom(ST_Transform(c.geom, 3857), bbox_3857, 4096, 0, true) AS geom_mvt
        FROM censo.cnefe_enderecos c
        WHERE c.geom && bbox_4674
          AND (v_cod_mun IS NULL OR c.cod_municipio = v_cod_mun)
          AND (v_especie IS NULL OR c.especie = v_especie)
        LIMIT v_limit
    ) tile
    WHERE geom_mvt IS NOT NULL;

    RETURN COALESCE(result, ''::bytea);
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE;

-- ─────────────────────────────────────────────────────────────────────────────
-- Rótulos de municípios brasileiros (centroids + nomes)
-- Filtragem progressiva por população conforme zoom para evitar clutter.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION api.tiles_labels_municipios(
    z            INT,
    x            INT,
    y            INT,
    query_params JSON DEFAULT '{}'
)
RETURNS bytea AS $$
DECLARE
    result    bytea;
    bbox_3857 geometry := ST_TileEnvelope(z, x, y);
    pop_min   INT;
BEGIN
    -- Filtro de população por zoom: zooms baixos → só cidades grandes
    pop_min := CASE
        WHEN z <= 3 THEN 500000
        WHEN z <= 5 THEN 100000
        WHEN z <= 7 THEN 50000
        WHEN z <= 9 THEN 10000
        ELSE 0
    END;

    SELECT ST_AsMVT(t, 'labels_municipios', 4096, 'geom_mvt')
    INTO result
    FROM (
        SELECT
            m.nome,
            m.populacao_2022::FLOAT8 AS populacao,
            ST_AsMVTGeom(
                ST_Transform(ST_Centroid(m.geom), 3857),
                bbox_3857, 4096, 64, true
            ) AS geom_mvt
        FROM geo.municipios m
        WHERE m.populacao_2022 >= pop_min
          AND ST_Intersects(
              ST_Transform(m.geom, 3857),
              bbox_3857
          )
    ) t;

    RETURN COALESCE(result, ''::bytea);
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE;

-- ─────────────────────────────────────────────────────────────────────────────
-- Utilitários
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION api.notify_cache_invalidation(
    camada TEXT,
    cod_uf SMALLINT DEFAULT NULL
) RETURNS void AS $$
BEGIN
    PERFORM pg_notify('cache_invalidation',
        json_build_object('camada', camada, 'cod_uf', cod_uf, 'ts', now())::text);
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION api.refresh_indicadores() RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY api.indicadores_municipio;
    REFRESH MATERIALIZED VIEW CONCURRENTLY api.indicadores_uf;
    PERFORM api.notify_cache_invalidation('indicadores_municipio');
    PERFORM api.notify_cache_invalidation('indicadores_uf');
    RAISE NOTICE 'Vistas atualizadas em %', now();
END;
$$ LANGUAGE plpgsql;
