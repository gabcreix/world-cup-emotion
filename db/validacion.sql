-- =============================================================================
-- MUNDIAL 2026 — QUERIES DE VALIDACIÓN
-- Ejecutar tras los seeds para verificar integridad y conteos
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1. CONTEOS GENERALES — deben coincidir exactamente
-- -----------------------------------------------------------------------------

SELECT 'torneo'         AS tabla, COUNT(*) AS filas, 1  AS esperado FROM torneo
UNION ALL
SELECT 'edicion',                 COUNT(*),           1             FROM edicion
UNION ALL
SELECT 'fase',                    COUNT(*),           7             FROM fase
UNION ALL
SELECT 'grupo',                   COUNT(*),           12            FROM grupo
UNION ALL
SELECT 'pais',                    COUNT(*),           48            FROM pais
UNION ALL
SELECT 'ciudad_sede',             COUNT(*),           16            FROM ciudad_sede
UNION ALL
SELECT 'estadio',                 COUNT(*),           16            FROM estadio
UNION ALL
SELECT 'estadio_edicion',         COUNT(*),           16            FROM estadio_edicion
UNION ALL
SELECT 'seleccion',               COUNT(*),           48            FROM seleccion
UNION ALL
SELECT 'participacion',           COUNT(*),           48            FROM participacion
UNION ALL
SELECT 'fuente',                  COUNT(*),           13            FROM fuente
ORDER BY tabla;


-- -----------------------------------------------------------------------------
-- 2. EQUIPOS POR CONFEDERACIÓN — debe coincidir con reparto oficial
-- -----------------------------------------------------------------------------

SELECT
    p.confederacion,
    COUNT(*) AS equipos
FROM participacion pa
JOIN seleccion s  ON s.seleccion_id  = pa.seleccion_id
JOIN pais p       ON p.pais_id       = s.pais_id
GROUP BY p.confederacion
ORDER BY equipos DESC;

-- Resultado esperado:
-- UEFA      16
-- CAF       10
-- AFC        9
-- CONCACAF   6
-- CONMEBOL   6
-- OFC        1


-- -----------------------------------------------------------------------------
-- 3. EQUIPOS POR GRUPO — todos deben tener exactamente 4
-- -----------------------------------------------------------------------------

SELECT
    g.letra                 AS grupo,
    COUNT(*)                AS equipos
FROM participacion pa
JOIN grupo g ON g.grupo_id = pa.grupo_id
GROUP BY g.letra
ORDER BY g.letra;


-- -----------------------------------------------------------------------------
-- 4. COMPOSICIÓN DETALLADA DE GRUPOS — para revisión visual
-- -----------------------------------------------------------------------------

SELECT
    g.letra                                     AS grupo,
    p.nombre                                    AS pais,
    s.codigo_fifa                               AS fifa,
    pc.confederacion                            AS conf,
    pa.posicion_fifa_previa                     AS ranking_fifa,
    pa.clasificacion_via                        AS via
FROM participacion pa
JOIN seleccion s    ON s.seleccion_id   = pa.seleccion_id
JOIN pais p         ON p.pais_id        = s.pais_id
JOIN pais pc        ON pc.pais_id       = s.pais_id
JOIN grupo g        ON g.grupo_id       = pa.grupo_id
ORDER BY g.letra, pa.posicion_fifa_previa;


-- -----------------------------------------------------------------------------
-- 5. ANFITRIONES — deben ser exactamente 3
-- -----------------------------------------------------------------------------

SELECT
    p.nombre,
    p.codigo_fifa,
    pa.clasificacion_via
FROM participacion pa
JOIN seleccion s ON s.seleccion_id = pa.seleccion_id
JOIN pais p      ON p.pais_id      = s.pais_id
WHERE pa.clasificacion_via IN ('anfitrion', 'campeon_defensor')
ORDER BY pa.clasificacion_via, p.nombre;


-- -----------------------------------------------------------------------------
-- 6. ESTADIOS — verificar nombres, capacidades y países
-- -----------------------------------------------------------------------------

SELECT
    e.estadio_id,
    ae.alias                AS nombre_oficial,
    e.ciudad,
    p.nombre                AS pais,
    e.capacidad,
    e.superficie,
    e.techo,
    cs.nombre               AS ciudad_sede
FROM estadio e
JOIN pais p             ON p.pais_id            = e.pais_id
JOIN estadio_edicion ee ON ee.estadio_id        = e.estadio_id
JOIN ciudad_sede cs     ON cs.ciudad_sede_id    = ee.ciudad_sede_id
LEFT JOIN alias_entidad ae ON ae.entidad_tipo   = 'estadio'
                           AND ae.entidad_id    = e.estadio_id
                           AND ae.es_canonico   = TRUE
ORDER BY p.nombre, e.capacidad DESC;


-- -----------------------------------------------------------------------------
-- 7. ALIAS — verificar canónicos por tipo de entidad
-- -----------------------------------------------------------------------------

SELECT
    entidad_tipo,
    COUNT(*)                        AS total_alias,
    COUNT(*) FILTER (WHERE es_canonico = TRUE)  AS canonicos,
    COUNT(*) FILTER (WHERE es_canonico = FALSE) AS alternativos
FROM alias_entidad
GROUP BY entidad_tipo
ORDER BY entidad_tipo;

-- Los canónicos deben ser exactamente:
-- estadio   → 16
-- seleccion → 48


-- -----------------------------------------------------------------------------
-- 8. SELECCIONES SIN ALIAS CANÓNICO — debe devolver 0 filas
-- -----------------------------------------------------------------------------

SELECT s.seleccion_id, s.codigo_fifa
FROM seleccion s
WHERE NOT EXISTS (
    SELECT 1 FROM alias_entidad ae
    WHERE ae.entidad_tipo = 'seleccion'
    AND ae.entidad_id     = s.seleccion_id
    AND ae.es_canonico    = TRUE
);


-- -----------------------------------------------------------------------------
-- 9. ESTADIOS SIN ALIAS CANÓNICO — debe devolver 0 filas
-- -----------------------------------------------------------------------------

SELECT e.estadio_id, e.ciudad
FROM estadio e
WHERE NOT EXISTS (
    SELECT 1 FROM alias_entidad ae
    WHERE ae.entidad_tipo = 'estadio'
    AND ae.entidad_id     = e.estadio_id
    AND ae.es_canonico    = TRUE
);


-- -----------------------------------------------------------------------------
-- 10. FUENTES ACTIVAS — para confirmar pipeline de ingestión
-- -----------------------------------------------------------------------------

SELECT
    codigo,
    nombre,
    idioma,
    activa
FROM fuente
ORDER BY activa DESC, idioma, codigo;


-- -----------------------------------------------------------------------------
-- 11. CHECKS DE INTEGRIDAD — FKs críticas
-- -----------------------------------------------------------------------------

-- Participaciones sin grupo asignado (no debe haber ninguna)
SELECT COUNT(*) AS participaciones_sin_grupo
FROM participacion
WHERE grupo_id IS NULL;

-- Selecciones sin país (no debe haber ninguna)
SELECT COUNT(*) AS selecciones_sin_pais
FROM seleccion
WHERE pais_id IS NULL;

-- Estadios sin ciudad sede en 2026 (no debe haber ninguno)
SELECT COUNT(*) AS estadios_sin_sede
FROM estadio e
WHERE NOT EXISTS (
    SELECT 1 FROM estadio_edicion ee
    WHERE ee.estadio_id = e.estadio_id
    AND ee.edicion_id   = 1
);


-- -----------------------------------------------------------------------------
-- 12. RANKING FIFA — top 10 y bottom 5 del torneo
-- -----------------------------------------------------------------------------

SELECT
    pa.posicion_fifa_previa     AS ranking,
    p.nombre                    AS seleccion,
    g.letra                     AS grupo,
    pc.confederacion            AS conf
FROM participacion pa
JOIN seleccion s ON s.seleccion_id = pa.seleccion_id
JOIN pais p      ON p.pais_id      = s.pais_id
JOIN pais pc     ON pc.pais_id     = s.pais_id
JOIN grupo g     ON g.grupo_id     = pa.grupo_id
ORDER BY pa.posicion_fifa_previa
LIMIT 10;
