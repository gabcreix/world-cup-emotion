-- Deduplicación de noticias por título normalizado: distintas fuentes RSS
-- pueden cubrir el mismo evento con URLs distintas pero títulos equivalentes.
ALTER TABLE noticia ADD COLUMN titulo_hash CHAR(64);

CREATE UNIQUE INDEX uq_noticia_titulo_hash ON noticia(titulo_hash)
    WHERE titulo_hash IS NOT NULL;
