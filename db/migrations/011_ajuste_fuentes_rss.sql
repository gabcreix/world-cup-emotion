-- =============================================================================
-- MIGRACIÓN 011 — Ajuste de fuentes RSS
--   - Desactiva fuentes sin feed funcional (as, fifa, goal, sports_illustrated)
--   - Añade NewsNow (feed agregado del Mundial 2026)
-- Ejecutar en Supabase SQL Editor
-- =============================================================================

UPDATE fuente
SET activa = FALSE, rss_url = NULL
WHERE codigo IN ('as', 'fifa', 'goal', 'sports_illustrated');

INSERT INTO fuente (codigo, nombre, url_base, idioma, activa, rss_url)
VALUES (
    'newsnow',
    'NewsNow Football',
    'https://www.newsnow.co.uk/h/Sport/Football',
    'en',
    TRUE,
    'https://www.newsnow.co.uk/h/Sport/Football/International/2026+FIFA+World+Cup?type=ts.rss'
);
