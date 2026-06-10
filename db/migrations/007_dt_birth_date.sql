-- =============================================================================
-- MIGRACIÓN 007 — Fecha de nacimiento de los DTs
-- Ejecutar en Supabase SQL Editor
--
-- Añade fecha_nacimiento a silver.fbref_dt (rellenada desde la página
-- individual del entrenador en FBref) y una tabla bronze para el HTML
-- crudo de esas páginas.
-- =============================================================================

ALTER TABLE silver.fbref_dt ADD COLUMN fecha_nacimiento DATE;

CREATE TABLE bronze.fbref_dt_profile_raw (
    id              BIGSERIAL       PRIMARY KEY,
    run_id          UUID            NOT NULL REFERENCES bronze.fbref_dts_run(run_id),
    fbref_dt_id     BIGINT          NOT NULL REFERENCES silver.fbref_dt(id),
    fbref_url       VARCHAR(300)    NOT NULL,
    raw_json        JSONB           NOT NULL,
    scraped_en      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX ON bronze.fbref_dt_profile_raw(run_id);
