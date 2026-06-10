-- =============================================================================
-- MIGRACIÓN 006 — Esquemas bronze y silver para fbref_dts (entrenadores)
-- Ejecutar en Supabase SQL Editor
-- =============================================================================

CREATE TABLE bronze.fbref_dts_run (
    run_id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    ejecutado_en    TIMESTAMP       NOT NULL DEFAULT NOW(),
    num_equipos     INTEGER,
    notas           TEXT
);

CREATE TABLE bronze.fbref_dt_raw (
    id              BIGSERIAL       PRIMARY KEY,
    run_id          UUID            NOT NULL REFERENCES bronze.fbref_dts_run(run_id),
    team_name_fbref VARCHAR(100)    NOT NULL,
    fbref_squad_url VARCHAR(300)    NOT NULL,
    -- JSON crudo: párrafos de #meta + candidatos a "Manager"
    raw_json        JSONB           NOT NULL,
    scraped_en      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX ON bronze.fbref_dt_raw(run_id);
CREATE INDEX ON bronze.fbref_dt_raw(team_name_fbref);


CREATE TABLE silver.fbref_dt (
    id                  BIGSERIAL       PRIMARY KEY,
    bronze_id           BIGINT          NOT NULL REFERENCES bronze.fbref_dt_raw(id),
    run_id              UUID            NOT NULL,

    nombre_completo     VARCHAR(150)    NOT NULL,
    fbref_url           VARCHAR(300),

    codigo_fifa         CHAR(3)         NOT NULL,
    team_name_fbref     VARCHAR(100)    NOT NULL,

    es_valido           BOOLEAN         NOT NULL DEFAULT TRUE,
    motivo_invalido     TEXT,

    procesado_en        TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX ON silver.fbref_dt(run_id);
