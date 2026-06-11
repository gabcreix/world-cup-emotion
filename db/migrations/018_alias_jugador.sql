-- =============================================================================
-- MIGRACIÓN 018 — Alias de jugadores para detección de menciones
--   Siembra alias_entidad con el nombre completo de cada jugador (tabla
--   jugador, poblada por el pipeline fbref_squads) como alias canónico.
-- Ejecutar en Supabase SQL Editor
-- =============================================================================

INSERT INTO alias_entidad (entidad_tipo, entidad_id, alias, fuente, idioma, es_canonico)
SELECT 'jugador', jugador_id, nombre_completo, 'fbref', NULL, TRUE
FROM jugador
ON CONFLICT (entidad_tipo, entidad_id, alias) DO NOTHING;
