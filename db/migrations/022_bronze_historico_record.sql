-- =============================================================================
-- MIGRACIÓN 022 — Bronze para historico_record (goleadores, apariciones, jugadores)
--   Amplía bronze.historico_mundiales_run con contadores de goles/apariciones/
--   jugadores y añade las tablas raw correspondientes (dataset Fjelstul World
--   Cup Database: goals.csv, player_appearances.csv, players.csv), filtradas a
--   mundiales masculinos.
-- Ejecutar en Supabase SQL Editor
-- =============================================================================

ALTER TABLE bronze.historico_mundiales_run
    ADD COLUMN num_goles        INTEGER,
    ADD COLUMN num_apariciones  INTEGER,
    ADD COLUMN num_jugadores    INTEGER;

CREATE TABLE bronze.historico_goleador_raw (
    id              BIGSERIAL       PRIMARY KEY,
    run_id          UUID            NOT NULL REFERENCES bronze.historico_mundiales_run(run_id),
    raw_json        JSONB           NOT NULL,
    scraped_en      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE TABLE bronze.historico_aparicion_raw (
    id              BIGSERIAL       PRIMARY KEY,
    run_id          UUID            NOT NULL REFERENCES bronze.historico_mundiales_run(run_id),
    raw_json        JSONB           NOT NULL,
    scraped_en      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE TABLE bronze.historico_jugador_raw (
    id              BIGSERIAL       PRIMARY KEY,
    run_id          UUID            NOT NULL REFERENCES bronze.historico_mundiales_run(run_id),
    raw_json        JSONB           NOT NULL,
    scraped_en      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX ON bronze.historico_goleador_raw(run_id);
CREATE INDEX ON bronze.historico_aparicion_raw(run_id);
CREATE INDEX ON bronze.historico_jugador_raw(run_id);
