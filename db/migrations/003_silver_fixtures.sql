-- =============================================================================
-- MIGRACIÓN 003 — Silver fbref_fixtures
-- Ejecutar en Supabase SQL Editor
-- =============================================================================

CREATE TABLE silver.fbref_fixture (
    id                      BIGSERIAL       PRIMARY KEY,
    bronze_id               BIGINT          NOT NULL REFERENCES bronze.fbref_fixture_raw(id),
    run_id                  UUID            NOT NULL,

    fecha                   DATE            NOT NULL,
    hora_local              TIME,
    jornada                 INTEGER,

    fase_raw                VARCHAR(50),
    fase_codigo             VARCHAR(10),

    equipo_local_fifa       CHAR(3),
    equipo_visitante_fifa   CHAR(3),

    venue_raw               VARCHAR(150),

    goles_local             INTEGER,
    goles_visitante         INTEGER,

    es_valido               BOOLEAN         NOT NULL DEFAULT TRUE,
    motivo_invalido         TEXT,

    procesado_en            TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX ON silver.fbref_fixture(run_id);
CREATE INDEX ON silver.fbref_fixture(fecha);
CREATE INDEX ON silver.fbref_fixture(equipo_local_fifa, equipo_visitante_fifa);
