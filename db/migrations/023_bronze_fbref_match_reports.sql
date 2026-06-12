-- =============================================================================
-- MIGRACIÓN 023 — Bronze fbref_match_reports + match_report_url
-- Ejecutar en Supabase SQL Editor
-- =============================================================================

-- URL del match report de FBref, resuelta en fbref_fixtures (silver/gold)
ALTER TABLE silver.fbref_fixture ADD COLUMN match_report_url VARCHAR(500);
ALTER TABLE partido ADD COLUMN match_report_url VARCHAR(500);

CREATE TABLE bronze.fbref_match_report_raw (
    id                  BIGSERIAL       PRIMARY KEY,
    partido_id          BIGINT          NOT NULL REFERENCES partido(partido_id),
    match_report_url    VARCHAR(500),
    html_raw            TEXT            NOT NULL,
    scraped_en          TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX ON bronze.fbref_match_report_raw(partido_id);
