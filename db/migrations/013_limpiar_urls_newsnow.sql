-- =============================================================================
-- MIGRACIÓN 013 — Limpieza de URLs de tracking de NewsNow
--   La primera ejecución del scraper de NewsNow guardó las URLs de
--   redirección (c.newsnow.co.uk/A/...) en lugar de la URL del artículo
--   original. Se borran esas filas para que el próximo run las inserte
--   con la URL resuelta correcta.
-- Ejecutar en Supabase SQL Editor
-- =============================================================================

DELETE FROM noticia
WHERE url LIKE 'https://c.newsnow.co.uk/%';
