-- =============================================================================
-- MIGRACIÓN 015 — Eliminar índice ivfflat de embedding (dataset pequeño)
--   Con ~172 filas y lists=100, la mayoría de listas quedan vacías y el
--   sondeo por defecto (ivfflat.probes=1) puede devolver 0 resultados
--   para consultas que caen en una lista vacía/irrelevante.
--   Sin índice, la búsqueda por similitud hace sequential scan exacto,
--   instantáneo a este volumen. Recrear el índice (con lists ajustado,
--   ej. lists ~ sqrt(num_filas)) cuando el volumen crezca a miles de filas.
-- Ejecutar en Supabase SQL Editor
-- =============================================================================

DROP INDEX IF EXISTS idx_embedding_vector;
