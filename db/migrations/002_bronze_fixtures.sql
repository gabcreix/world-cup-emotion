-- =============================================================================
-- MIGRACIÓN 002 — Bronze fbref_fixtures
-- Ejecutar en Supabase SQL Editor
-- =============================================================================

CREATE TABLE bronze.fbref_fixtures_run (
    run_id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    ejecutado_en    TIMESTAMP       NOT NULL DEFAULT NOW(),
    num_partidos    INTEGER,
    notas           TEXT
);

CREATE TABLE bronze.fbref_fixture_raw (
    id              BIGSERIAL       PRIMARY KEY,
    run_id          UUID            NOT NULL REFERENCES bronze.fbref_fixtures_run(run_id),
    -- JSON crudo: todas las celdas data-stat de la fila del calendario
    -- (round, dayofweek, date, start_time, home_team, score, away_team,
    --  venue, attendance, referee, match_report_url, ...)
    raw_json        JSONB           NOT NULL,
    scraped_en      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX ON bronze.fbref_fixture_raw(run_id);
