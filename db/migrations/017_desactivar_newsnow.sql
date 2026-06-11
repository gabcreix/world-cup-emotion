-- =============================================================================
-- MIGRACIÓN 017 — Desactivar NewsNow como fuente
--   NewsNow es un agregador (no fuente original); se desactiva y se
--   mantienen las fuentes RSS directas que funcionan bien
--   (bbc_sport, guardian, marca).
-- Ejecutar en Supabase SQL Editor
-- =============================================================================

UPDATE fuente
SET activa = FALSE
WHERE codigo = 'newsnow';
