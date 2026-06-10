-- =============================================================================
-- MIGRACIÓN 008 — Fuentes RSS para ingesta de noticias
-- Ejecutar en Supabase SQL Editor
-- =============================================================================

ALTER TABLE fuente ADD COLUMN rss_url VARCHAR(500);

-- Fuentes ya existentes con feed RSS confirmado
UPDATE fuente SET rss_url = 'https://e00-marca.uecdn.es/rss/futbol/seleccion.xml' WHERE codigo = 'marca';
UPDATE fuente SET rss_url = 'https://as.com/rss/tags/copa_del_mundo.xml'          WHERE codigo = 'as';
UPDATE fuente SET rss_url = 'https://feeds.bbci.co.uk/sport/football/rss.xml'     WHERE codigo = 'bbc_sport';
UPDATE fuente SET rss_url = 'https://www.theguardian.com/football/worldcup/rss'  WHERE codigo = 'guardian';
UPDATE fuente SET rss_url = 'https://www.fifa.com/rss-feeds'                      WHERE codigo = 'fifa';

-- Nuevas fuentes con RSS confirmado
INSERT INTO fuente (codigo, nombre, url_base, idioma, activa, rss_url)
VALUES
    ('goal',  'Goal.com', 'https://www.goal.com',  'en', TRUE, 'https://www.goal.com/feeds/en/news'),
    ('90min', '90min',    'https://www.90min.com', 'en', TRUE, 'https://www.90min.com/rss');
