-- =============================================================================
-- MIGRACIÓN 012 — Fix: 90min seguía activo (la 010 no se había aplicado)
-- Idempotente: cubre 90min tanto si quedó como '90min' o como 'sports_illustrated'
-- Ejecutar en Supabase SQL Editor
-- =============================================================================

UPDATE fuente
SET activa = FALSE, rss_url = NULL
WHERE codigo IN ('90min', 'sports_illustrated', 'as', 'fifa', 'goal');
