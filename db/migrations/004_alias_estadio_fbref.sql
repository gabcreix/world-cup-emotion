-- =============================================================================
-- MIGRACIÓN 004 — Alias de estadios usados por FBref
-- Ejecutar en Supabase SQL Editor
--
-- FBref usa nombres distintos a los canónicos para algunos estadios:
--   - Estadio Azteca (1)  -> "Estadio Banorte" (naming rights actual)
--   - Estadio BBVA (3)    -> "Estadio BBVA Bancomer"
--   - BC Place (16)       -> "BC Place Stadium"
--   - NRG Stadium (11)    -> "Reliant Stadium" (nombre histórico usado por FBref)
-- =============================================================================

INSERT INTO alias_entidad (entidad_tipo, entidad_id, alias, fuente, idioma, es_canonico)
VALUES
    ('estadio',  1, 'Estadio Banorte',         'fbref', 'es', FALSE),
    ('estadio',  3, 'Estadio BBVA Bancomer',   'fbref', 'es', FALSE),
    ('estadio', 16, 'BC Place Stadium',        'fbref', 'en', FALSE),
    ('estadio', 11, 'Reliant Stadium',         'fbref', 'en', FALSE);
