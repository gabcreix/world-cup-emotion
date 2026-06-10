-- =============================================================================
-- MIGRACIÓN 009 — Esquemas bronze y silver para news_rss
-- Ejecutar en Supabase SQL Editor
-- =============================================================================

CREATE TABLE bronze.news_rss_run (
    run_id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    ejecutado_en    TIMESTAMP       NOT NULL DEFAULT NOW(),
    num_items       INTEGER,
    notas           TEXT
);

CREATE TABLE bronze.news_rss_raw (
    id              BIGSERIAL       PRIMARY KEY,
    run_id          UUID            NOT NULL REFERENCES bronze.news_rss_run(run_id),
    fuente_id       BIGINT          NOT NULL REFERENCES fuente(fuente_id),
    -- JSON crudo: title, link, summary, published, etc. (tal cual feedparser)
    raw_json        JSONB           NOT NULL,
    scraped_en      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX ON bronze.news_rss_raw(run_id);
CREATE INDEX ON bronze.news_rss_raw(fuente_id);


CREATE TABLE silver.news_item (
    id                  BIGSERIAL       PRIMARY KEY,
    bronze_id           BIGINT          NOT NULL REFERENCES bronze.news_rss_raw(id),
    run_id              UUID            NOT NULL,

    fuente_id           BIGINT          NOT NULL REFERENCES fuente(fuente_id),
    titulo              VARCHAR(300)    NOT NULL,
    url                 VARCHAR(500)    NOT NULL,
    idioma              CHAR(2),
    resumen             TEXT,
    fecha_publicacion   TIMESTAMPTZ,

    es_valido           BOOLEAN         NOT NULL DEFAULT TRUE,
    motivo_invalido     TEXT,

    procesado_en        TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX ON silver.news_item(run_id);
CREATE INDEX ON silver.news_item(url);
