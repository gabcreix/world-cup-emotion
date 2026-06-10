-- =============================================================================
-- MIGRACIÓN 014 — Idempotencia para mencion
--   Permite re-ejecutar el pipeline de menciones sin duplicar filas.
-- Ejecutar en Supabase SQL Editor
-- =============================================================================

ALTER TABLE mencion
    ADD CONSTRAINT uq_mencion_entidad UNIQUE (noticia_id, entidad_tipo, entidad_id);
