-- =============================================================================
-- MIGRACIÓN 001 — Esquemas bronze y silver
-- Ejecutar en Supabase SQL Editor
-- =============================================================================

-- -----------------------------------------------------------------------------
-- BRONZE
-- -----------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS bronze;

CREATE TABLE bronze.fbref_squads_run (
    run_id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    ejecutado_en    TIMESTAMP       NOT NULL DEFAULT NOW(),
    num_equipos     INTEGER,
    num_jugadores   INTEGER,
    notas           TEXT
);

CREATE TABLE bronze.fbref_squad_raw (
    id              BIGSERIAL       PRIMARY KEY,
    run_id          UUID            NOT NULL REFERENCES bronze.fbref_squads_run(run_id),
    team_name_fbref VARCHAR(100)    NOT NULL,
    fbref_squad_url VARCHAR(300)    NOT NULL,
    -- JSON exacto del parser: nombre_completo, posicion_raw_fbref,
    -- fecha_nacimiento, nationality_raw, fbref_url, posicion_raw_fbref
    raw_json        JSONB           NOT NULL,
    scraped_en      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX ON bronze.fbref_squad_raw(run_id);
CREATE INDEX ON bronze.fbref_squad_raw(team_name_fbref);


-- -----------------------------------------------------------------------------
-- SILVER
-- -----------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS silver;

CREATE TABLE silver.fbref_player (
    id                  BIGSERIAL       PRIMARY KEY,
    bronze_id           BIGINT          NOT NULL REFERENCES bronze.fbref_squad_raw(id),
    run_id              UUID            NOT NULL,

    nombre_completo     VARCHAR(150)    NOT NULL,
    fecha_nacimiento    DATE,
    posicion            VARCHAR(20)     NOT NULL,
    posicion_especifica VARCHAR(30),
    posicion_raw_fbref  VARCHAR(20),
    nationality_raw     VARCHAR(50),

    codigo_fifa         CHAR(3)         NOT NULL,
    team_name_fbref     VARCHAR(100)    NOT NULL,
    fbref_url           VARCHAR(300),

    es_valido           BOOLEAN         NOT NULL DEFAULT TRUE,
    motivo_invalido     TEXT,

    procesado_en        TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX ON silver.fbref_player(run_id);
CREATE INDEX ON silver.fbref_player(codigo_fifa);
CREATE INDEX ON silver.fbref_player(fbref_url);
CREATE INDEX ON silver.fbref_player(nombre_completo, codigo_fifa);
