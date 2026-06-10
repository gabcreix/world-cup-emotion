-- =============================================================================
-- MIGRACIÓN 010 — 90min desapareció, sustituido por Sports Illustrated Soccer
-- Ejecutar en Supabase SQL Editor
-- =============================================================================

UPDATE fuente
SET codigo   = 'sports_illustrated',
    nombre   = 'Sports Illustrated Soccer',
    url_base = 'https://www.si.com/soccer',
    rss_url  = 'https://www.si.com/.rss/full/soccer'
WHERE codigo = '90min';
