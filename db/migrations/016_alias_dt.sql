-- =============================================================================
-- MIGRACIÓN 016 — Alias de DTs para detección de menciones
--   Siembra alias_entidad con el nombre completo de cada DT (tabla dt,
--   poblada por el pipeline fbref_dts) como alias canónico.
-- Ejecutar en Supabase SQL Editor
-- =============================================================================

INSERT INTO alias_entidad (entidad_tipo, entidad_id, alias, fuente, idioma, es_canonico)
SELECT 'dt', dt_id, nombre_completo, 'fbref', NULL, TRUE
FROM dt
ON CONFLICT (entidad_tipo, entidad_id, alias) DO NOTHING;
