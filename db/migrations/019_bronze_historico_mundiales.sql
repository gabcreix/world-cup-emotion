-- =============================================================================
-- MIGRACIÓN 019 — Bronze para histórico de mundiales
--   Tablas crudas para la ingesta del dataset Fjelstul World Cup Database
--   (github.com/jfjelstul/worldcup), filtrado a los 22 mundiales masculinos
--   (1930-2022).
-- Ejecutar en Supabase SQL Editor
-- =============================================================================

CREATE TABLE bronze.historico_mundiales_run (
    run_id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    ejecutado_en    TIMESTAMP       NOT NULL DEFAULT NOW(),
    num_ediciones   INTEGER,
    num_partidos    INTEGER,
    notas           TEXT
);

CREATE TABLE bronze.historico_edicion_raw (
    id              BIGSERIAL       PRIMARY KEY,
    run_id          UUID            NOT NULL REFERENCES bronze.historico_mundiales_run(run_id),
    -- fila cruda de tournaments.csv (year, host_country, winner, count_teams, ...)
    raw_json        JSONB           NOT NULL,
    scraped_en      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE TABLE bronze.historico_resultado_raw (
    id              BIGSERIAL       PRIMARY KEY,
    run_id          UUID            NOT NULL REFERENCES bronze.historico_mundiales_run(run_id),
    -- fila cruda de matches.csv (stage_name, teams, score, penalties, ...)
    raw_json        JSONB           NOT NULL,
    scraped_en      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX ON bronze.historico_edicion_raw(run_id);
CREATE INDEX ON bronze.historico_resultado_raw(run_id);
