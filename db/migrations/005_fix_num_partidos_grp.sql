-- =============================================================================
-- MIGRACIÓN 005 — Corrige fase.num_partidos para fase de grupos
-- Ejecutar en Supabase SQL Editor
--
-- El Mundial 2026 tiene 12 grupos de 4 equipos: cada grupo juega 6 partidos
-- (todos contra todos), por lo que la fase de grupos tiene 12 * 6 = 72
-- partidos, no 48 (valor heredado del formato de 32 equipos / 8 grupos).
-- =============================================================================

UPDATE fase
SET num_partidos = 72
WHERE codigo = 'GRP';
