-- =============================================================================
-- MIGRACIÓN 021 — Identificador externo en historico_resultado
--   Añade match_id_externo (id de partido del dataset Fjelstul World Cup
--   Database, p.ej. "M-1930-01") con UNIQUE para permitir upserts
--   idempotentes desde el pipeline historico_mundiales.
-- Ejecutar en Supabase SQL Editor
-- =============================================================================

ALTER TABLE historico_resultado
    ADD COLUMN match_id_externo VARCHAR(20) UNIQUE;
