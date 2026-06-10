-- =============================================================================
-- MIGRACIÓN 013 — Desactiva NewsNow
-- El feed RSS no devuelve XML (devuelve la página HTML, bot-detection),
-- pese al parámetro ?type=ts.rss.
-- Ejecutar en Supabase SQL Editor
-- =============================================================================

UPDATE fuente
SET activa = FALSE, rss_url = NULL
WHERE codigo = 'newsnow';
