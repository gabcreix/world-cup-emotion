-- =============================================================================
-- MUNDIAL 2026 — MODELO DE DATOS
-- =============================================================================
-- Orden de creación respeta dependencias entre tablas.
-- Convenciones:
--   · PKs: BIGSERIAL
--   · Auditoría: creado_en / actualizado_en en todas las tablas
--   · FKs polimórficas (ALIAS_ENTIDAD, MENCION): sin constraint, integridad
--     garantizada por el pipeline
-- =============================================================================

-- Extensión necesaria para embeddings vectoriales
CREATE EXTENSION IF NOT EXISTS vector;


-- =============================================================================
-- DOMINIO 1 — TORNEO
-- =============================================================================

CREATE TABLE torneo (
    torneo_id       BIGSERIAL       PRIMARY KEY,
    nombre          VARCHAR(100)    NOT NULL,
    nombre_corto    VARCHAR(50),
    organizador     VARCHAR(100),
    creado_en       TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en  TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE TABLE edicion (
    edicion_id      BIGSERIAL       PRIMARY KEY,
    torneo_id       BIGINT          NOT NULL REFERENCES torneo(torneo_id),
    anyo            INTEGER         NOT NULL,
    nombre_oficial  VARCHAR(150)    NOT NULL,
    num_equipos     INTEGER         NOT NULL,
    num_grupos      INTEGER         NOT NULL,
    formato_json    JSONB,
    fecha_inicio    DATE,
    fecha_fin       DATE,
    creado_en       TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en  TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_edicion_anyo UNIQUE (torneo_id, anyo)
);

CREATE TABLE fase (
    fase_id         BIGSERIAL       PRIMARY KEY,
    edicion_id      BIGINT          NOT NULL REFERENCES edicion(edicion_id),
    nombre          VARCHAR(100)    NOT NULL,
    codigo          VARCHAR(10)     NOT NULL,   -- 'GRP' | 'R32' | 'R16' | 'QF' | 'SF' | 'F'
    orden           INTEGER         NOT NULL,
    num_partidos    INTEGER,
    eliminatoria    BOOLEAN         NOT NULL DEFAULT FALSE,
    creado_en       TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en  TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_fase_codigo UNIQUE (edicion_id, codigo)
);

CREATE TABLE grupo (
    grupo_id        BIGSERIAL       PRIMARY KEY,
    edicion_id      BIGINT          NOT NULL REFERENCES edicion(edicion_id),
    fase_id         BIGINT          NOT NULL REFERENCES fase(fase_id),
    letra           CHAR(1)         NOT NULL,   -- 'A' … 'L'
    creado_en       TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en  TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_grupo_letra UNIQUE (edicion_id, letra)
);


-- =============================================================================
-- DOMINIO 2 — GEOGRAFÍA
-- =============================================================================

CREATE TABLE pais (
    pais_id             BIGSERIAL       PRIMARY KEY,
    nombre              VARCHAR(100)    NOT NULL,
    nombre_en           VARCHAR(100),
    codigo_fifa         CHAR(3)         NOT NULL UNIQUE,
    codigo_iso2         CHAR(2),
    confederacion       VARCHAR(20)     NOT NULL
                            CHECK (confederacion IN ('UEFA','CONMEBOL','CONCACAF','CAF','AFC','OFC')),
    anfitrion_2026      BOOLEAN         NOT NULL DEFAULT FALSE,
    creado_en           TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE TABLE ciudad_sede (
    ciudad_sede_id  BIGSERIAL       PRIMARY KEY,
    edicion_id      BIGINT          NOT NULL REFERENCES edicion(edicion_id),
    pais_id         BIGINT          NOT NULL REFERENCES pais(pais_id),
    nombre          VARCHAR(100)    NOT NULL,
    nombre_en       VARCHAR(100),
    num_partidos    INTEGER,
    creado_en       TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en  TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE TABLE estadio (
    estadio_id      BIGSERIAL       PRIMARY KEY,
    pais_id         BIGINT          NOT NULL REFERENCES pais(pais_id),
    ciudad          VARCHAR(100)    NOT NULL,
    capacidad       INTEGER,
    superficie      VARCHAR(30)
                        CHECK (superficie IN ('cesped_natural','cesped_artificial','hibrido')),
    techo           BOOLEAN         NOT NULL DEFAULT FALSE,
    latitud         NUMERIC(9,6),
    longitud        NUMERIC(9,6),
    creado_en       TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en  TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE TABLE estadio_edicion (
    estadio_edicion_id  BIGSERIAL   PRIMARY KEY,
    estadio_id          BIGINT      NOT NULL REFERENCES estadio(estadio_id),
    edicion_id          BIGINT      NOT NULL REFERENCES edicion(edicion_id),
    ciudad_sede_id      BIGINT      NOT NULL REFERENCES ciudad_sede(ciudad_sede_id),
    num_partidos        INTEGER,
    creado_en           TIMESTAMP   NOT NULL DEFAULT NOW(),
    actualizado_en      TIMESTAMP   NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_estadio_edicion UNIQUE (estadio_id, edicion_id)
);


-- =============================================================================
-- DOMINIO 3 — SELECCIONES Y PLANTILLAS
-- =============================================================================

CREATE TABLE seleccion (
    seleccion_id        BIGSERIAL       PRIMARY KEY,
    pais_id             BIGINT          NOT NULL REFERENCES pais(pais_id) UNIQUE,
    codigo_fifa         CHAR(3)         NOT NULL UNIQUE,
    confederacion       VARCHAR(20)     NOT NULL
                            CHECK (confederacion IN ('UEFA','CONMEBOL','CONCACAF','CAF','AFC','OFC')),
    color_principal     CHAR(7),        -- hex '#FF0000'
    color_secundario    CHAR(7),
    creado_en           TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE TABLE dt (
    dt_id               BIGSERIAL       PRIMARY KEY,
    nombre_completo     VARCHAR(150)    NOT NULL,
    fecha_nacimiento    DATE,
    pais_id             BIGINT          REFERENCES pais(pais_id),
    creado_en           TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE TABLE jugador (
    jugador_id              BIGSERIAL       PRIMARY KEY,
    nombre_completo         VARCHAR(150)    NOT NULL,
    fecha_nacimiento        DATE,
    pais_id                 BIGINT          REFERENCES pais(pais_id),
    posicion                VARCHAR(20)     NOT NULL
                                CHECK (posicion IN ('portero','defensa','centrocampista','delantero')),
    posicion_especifica     VARCHAR(30)
                                CHECK (posicion_especifica IN (
                                    'portero',
                                    'defensa_central',
                                    'lateral_derecho',
                                    'lateral_izquierdo',
                                    'pivote',
                                    'mediocentro',
                                    'mediocentro_ofensivo',
                                    'carrilero_derecho',
                                    'carrilero_izquierdo',
                                    'extremo_derecho',
                                    'extremo_izquierdo',
                                    'segunda_punta',
                                    'delantero_centro'
                                )),
    pie_dominante           VARCHAR(15)
                                CHECK (pie_dominante IN ('derecho','izquierdo','ambidiestro')),
    creado_en               TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en          TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE TABLE participacion (
    participacion_id        BIGSERIAL       PRIMARY KEY,
    seleccion_id            BIGINT          NOT NULL REFERENCES seleccion(seleccion_id),
    edicion_id              BIGINT          NOT NULL REFERENCES edicion(edicion_id),
    grupo_id                BIGINT          REFERENCES grupo(grupo_id),
    dt_id                   BIGINT          REFERENCES dt(dt_id),
    clasificacion_via       VARCHAR(25)
                                CHECK (clasificacion_via IN ('clasificatorio','anfitrion','campeon_defensor')),
    resultado_final         VARCHAR(20)
                                CHECK (resultado_final IN (
                                    'campeon','subcampeon','tercero','cuarto',
                                    'cuartos','octavos','r32','grupos'
                                )),
    posicion_fifa_previa    INTEGER,
    creado_en               TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en          TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_participacion UNIQUE (seleccion_id, edicion_id)
);

CREATE TABLE convocatoria (
    convocatoria_id     BIGSERIAL       PRIMARY KEY,
    jugador_id          BIGINT          NOT NULL REFERENCES jugador(jugador_id),
    participacion_id    BIGINT          NOT NULL REFERENCES participacion(participacion_id),
    dorsal              INTEGER         CHECK (dorsal BETWEEN 1 AND 99),
    posicion_convocado  VARCHAR(20)
                            CHECK (posicion_convocado IN ('portero','defensa','centrocampista','delantero')),
    estado              VARCHAR(20)     NOT NULL DEFAULT 'disponible'
                            CHECK (estado IN ('disponible','lesionado','sancionado','baja')),
    capitan             BOOLEAN         NOT NULL DEFAULT FALSE,
    creado_en           TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en      TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_convocatoria UNIQUE (jugador_id, participacion_id)
);


-- =============================================================================
-- DOMINIO 4 — PARTIDOS Y ESTADÍSTICAS
-- =============================================================================

CREATE TABLE arbitro (
    arbitro_id          BIGSERIAL       PRIMARY KEY,
    nombre_completo     VARCHAR(150)    NOT NULL,
    fecha_nacimiento    DATE,
    pais_id             BIGINT          REFERENCES pais(pais_id),
    creado_en           TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE TABLE partido (
    partido_id                  BIGSERIAL       PRIMARY KEY,
    edicion_id                  BIGINT          NOT NULL REFERENCES edicion(edicion_id),
    fase_id                     BIGINT          NOT NULL REFERENCES fase(fase_id),
    grupo_id                    BIGINT          REFERENCES grupo(grupo_id),
    estadio_id                  BIGINT          REFERENCES estadio(estadio_id),
    arbitro_id                  BIGINT          REFERENCES arbitro(arbitro_id),
    participacion_local_id      BIGINT          NOT NULL REFERENCES participacion(participacion_id),
    participacion_visit_id      BIGINT          NOT NULL REFERENCES participacion(participacion_id),
    fecha_hora                  TIMESTAMPTZ,
    estado                      VARCHAR(20)     NOT NULL DEFAULT 'programado'
                                    CHECK (estado IN ('programado','en_curso','finalizado','suspendido')),
    goles_local                 INTEGER,
    goles_visitante             INTEGER,
    goles_local_prorroga        INTEGER,
    goles_visit_prorroga        INTEGER,
    penaltis_local              INTEGER,
    penaltis_visitante          INTEGER,
    creado_en                   TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en              TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE TABLE evento_partido (
    evento_id           BIGSERIAL       PRIMARY KEY,
    partido_id          BIGINT          NOT NULL REFERENCES partido(partido_id),
    jugador_id          BIGINT          REFERENCES jugador(jugador_id),
    jugador_rel_id      BIGINT          REFERENCES jugador(jugador_id),
    participacion_id    BIGINT          NOT NULL REFERENCES participacion(participacion_id),
    tipo                VARCHAR(20)     NOT NULL
                            CHECK (tipo IN (
                                'gol','gol_penalti','gol_propia',
                                'tarjeta_amarilla','tarjeta_roja','doble_amarilla',
                                'sustitucion','var'
                            )),
    minuto              INTEGER         CHECK (minuto BETWEEN 0 AND 130),
    minuto_adicional    INTEGER,
    descripcion         VARCHAR(300),
    creado_en           TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE TABLE stats_equipo (
    stats_equipo_id     BIGSERIAL       PRIMARY KEY,
    partido_id          BIGINT          NOT NULL REFERENCES partido(partido_id),
    participacion_id    BIGINT          NOT NULL REFERENCES participacion(participacion_id),
    xg                  NUMERIC(4,2),
    posesion            NUMERIC(4,1),
    tiros_totales       INTEGER,
    tiros_a_puerta      INTEGER,
    tiros_bloqueados    INTEGER,
    pases_totales       INTEGER,
    pases_completados   INTEGER,
    pases_clave         INTEGER,
    corners             INTEGER,
    fueras_de_juego     INTEGER,
    faltas_cometidas    INTEGER,
    despejes            INTEGER,
    creado_en           TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en      TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_stats_equipo UNIQUE (partido_id, participacion_id)
);

CREATE TABLE stats_jugador (
    stats_jugador_id        BIGSERIAL       PRIMARY KEY,
    partido_id              BIGINT          NOT NULL REFERENCES partido(partido_id),
    jugador_id              BIGINT          NOT NULL REFERENCES jugador(jugador_id),
    participacion_id        BIGINT          NOT NULL REFERENCES participacion(participacion_id),

    -- Tiempo
    minutos_jugados         INTEGER,
    titular                 BOOLEAN         NOT NULL DEFAULT FALSE,

    -- Ataque
    goles                   INTEGER         NOT NULL DEFAULT 0,
    asistencias             INTEGER         NOT NULL DEFAULT 0,
    xg                      NUMERIC(4,2),
    xag                     NUMERIC(4,2),
    tiros                   INTEGER,
    tiros_a_puerta          INTEGER,

    -- Pases y creación
    pases_completados       INTEGER,
    pases_intentados        INTEGER,
    pases_clave             INTEGER,

    -- Conducción
    regates_exitosos        INTEGER,
    regates_intentados      INTEGER,
    conducciones            INTEGER,

    -- Presión y recuperación
    presiones               INTEGER,
    presiones_exitosas      INTEGER,
    recuperaciones          INTEGER,
    perdidas_balon          INTEGER,

    -- Duelos
    duelos_ganados          INTEGER,
    duelos_totales          INTEGER,
    duelos_aereos_ganados   INTEGER,

    -- Defensa
    intercepciones          INTEGER,
    despejes                INTEGER,
    entradas_exitosas       INTEGER,
    tarjetas_amarillas      INTEGER         NOT NULL DEFAULT 0,
    tarjetas_rojas          INTEGER         NOT NULL DEFAULT 0,

    -- Valoración
    nota                    NUMERIC(3,1)    CHECK (nota BETWEEN 0 AND 10),

    -- Stats específicas de portero
    stats_extra_json        JSONB,

    creado_en               TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en          TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_stats_jugador UNIQUE (partido_id, jugador_id)
);


-- =============================================================================
-- DOMINIO 5 — HISTÓRICO
-- =============================================================================

CREATE TABLE historico_edicion (
    historico_edicion_id    BIGSERIAL       PRIMARY KEY,
    anyo                    INTEGER         NOT NULL UNIQUE,
    sede                    VARCHAR(150)    NOT NULL,
    num_equipos             INTEGER,
    campeon_pais_id         BIGINT          REFERENCES pais(pais_id),
    subcampeon_pais_id      BIGINT          REFERENCES pais(pais_id),
    tercero_pais_id         BIGINT          REFERENCES pais(pais_id),
    cuarto_pais_id          BIGINT          REFERENCES pais(pais_id),
    goles_totales           INTEGER,
    partidos_totales        INTEGER,
    promedio_goles          NUMERIC(3,2),
    asistencia_total        INTEGER,
    creado_en               TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en          TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE TABLE historico_resultado (
    historico_resultado_id  BIGSERIAL       PRIMARY KEY,
    historico_edicion_id    BIGINT          NOT NULL REFERENCES historico_edicion(historico_edicion_id),
    fase                    VARCHAR(50)     NOT NULL,
    pais_local_id           BIGINT          NOT NULL REFERENCES pais(pais_id),
    pais_visitante_id       BIGINT          NOT NULL REFERENCES pais(pais_id),
    goles_local             INTEGER         NOT NULL,
    goles_visitante         INTEGER         NOT NULL,
    goles_local_prorroga    INTEGER,
    goles_visit_prorroga    INTEGER,
    penaltis_local          INTEGER,
    penaltis_visitante      INTEGER,
    fecha                   DATE,
    creado_en               TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en          TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE TABLE historico_record (
    historico_record_id     BIGSERIAL       PRIMARY KEY,
    historico_edicion_id    BIGINT          REFERENCES historico_edicion(historico_edicion_id),
    pais_id                 BIGINT          REFERENCES pais(pais_id),
    jugador_ref             VARCHAR(150),
    tipo                    VARCHAR(30)     NOT NULL
                                CHECK (tipo IN (
                                    'goleador_torneo','goleador_historico',
                                    'portero_valla_invicta','mas_partidos',
                                    'mas_joven','mas_veterano',
                                    'racha_victorias','racha_invicto','otro'
                                )),
    valor                   VARCHAR(100),
    descripcion             VARCHAR(500),
    creado_en               TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en          TIMESTAMP       NOT NULL DEFAULT NOW()
);


-- =============================================================================
-- DOMINIO 6 — CONTENIDO Y NARRATIVAS
-- =============================================================================

CREATE TABLE fuente (
    fuente_id       BIGSERIAL       PRIMARY KEY,
    codigo          VARCHAR(30)     NOT NULL UNIQUE,
    nombre          VARCHAR(100)    NOT NULL,
    url_base        VARCHAR(300),
    idioma          CHAR(2)         CHECK (idioma IN ('es','en','fr','pt')),
    activa          BOOLEAN         NOT NULL DEFAULT TRUE,
    creado_en       TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en  TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE TABLE noticia (
    noticia_id          BIGSERIAL       PRIMARY KEY,
    fuente_id           BIGINT          NOT NULL REFERENCES fuente(fuente_id),
    titulo              VARCHAR(300)    NOT NULL,
    url                 VARCHAR(500)    NOT NULL UNIQUE,
    idioma              CHAR(2)         CHECK (idioma IN ('es','en','fr','pt')),
    texto_completo      TEXT,
    resumen             TEXT,
    fecha_publicacion   TIMESTAMPTZ,
    fecha_ingestion     TIMESTAMP       NOT NULL DEFAULT NOW(),
    relevancia          NUMERIC(3,2)    CHECK (relevancia BETWEEN 0 AND 1),
    creado_en           TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE TABLE embedding (
    embedding_id    BIGSERIAL       PRIMARY KEY,
    noticia_id      BIGINT          NOT NULL REFERENCES noticia(noticia_id),
    chunk_texto     TEXT            NOT NULL,
    chunk_orden     INTEGER         NOT NULL,
    vector          VECTOR(1536),
    modelo          VARCHAR(50)     NOT NULL
                        CHECK (modelo IN ('text-embedding-3-small','text-embedding-3-large')),
    creado_en       TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en  TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_embedding_chunk UNIQUE (noticia_id, chunk_orden)
);

CREATE TABLE mencion (
    mencion_id      BIGSERIAL       PRIMARY KEY,
    noticia_id      BIGINT          NOT NULL REFERENCES noticia(noticia_id),
    entidad_tipo    VARCHAR(20)     NOT NULL
                        CHECK (entidad_tipo IN ('jugador','seleccion','partido','estadio','dt','arbitro')),
    entidad_id      BIGINT          NOT NULL,
    contexto        VARCHAR(500),
    sentimiento     VARCHAR(10)
                        CHECK (sentimiento IN ('positivo','negativo','neutro')),
    creado_en       TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en  TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE TABLE narrativa (
    narrativa_id        BIGSERIAL       PRIMARY KEY,
    edicion_id          BIGINT          NOT NULL REFERENCES edicion(edicion_id),
    titulo              VARCHAR(300)    NOT NULL,
    tipo                VARCHAR(20)     NOT NULL
                            CHECK (tipo IN ('estadistica','racha','comparativa','hito','curiosidad')),
    descripcion         TEXT,
    score_relevancia    NUMERIC(3,2)    CHECK (score_relevancia BETWEEN 0 AND 1),
    score_editorial     NUMERIC(3,2)    CHECK (score_editorial BETWEEN 0 AND 1),
    publicada           BOOLEAN         NOT NULL DEFAULT FALSE,
    entidades_json      JSONB,
    fuente_datos        VARCHAR(20)
                            CHECK (fuente_datos IN ('historico','torneo_actual','mixta')),
    creado_en           TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en      TIMESTAMP       NOT NULL DEFAULT NOW()
);


-- =============================================================================
-- ENTIDAD TRANSVERSAL — ALIAS_ENTIDAD
-- =============================================================================

CREATE TABLE alias_entidad (
    alias_id        BIGSERIAL       PRIMARY KEY,
    entidad_tipo    VARCHAR(20)     NOT NULL
                        CHECK (entidad_tipo IN ('jugador','seleccion','estadio','dt','arbitro','pais')),
    entidad_id      BIGINT          NOT NULL,
    alias           VARCHAR(200)    NOT NULL,
    fuente          VARCHAR(20)     NOT NULL
                        CHECK (fuente IN ('transfermarkt','fbref','football_data','odds_api','prensa','manual')),
    idioma          CHAR(2)         CHECK (idioma IN ('es','en','fr','pt')),
    es_canonico     BOOLEAN         NOT NULL DEFAULT FALSE,
    creado_en       TIMESTAMP       NOT NULL DEFAULT NOW(),
    actualizado_en  TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_alias UNIQUE (entidad_tipo, entidad_id, alias)
);


-- =============================================================================
-- ÍNDICES
-- =============================================================================

-- Torneo
CREATE INDEX idx_edicion_torneo        ON edicion(torneo_id);
CREATE INDEX idx_fase_edicion          ON fase(edicion_id);
CREATE INDEX idx_grupo_edicion         ON grupo(edicion_id);

-- Geografía
CREATE INDEX idx_ciudad_sede_pais      ON ciudad_sede(pais_id);
CREATE INDEX idx_estadio_pais          ON estadio(pais_id);
CREATE INDEX idx_estadio_edicion_est   ON estadio_edicion(estadio_id);
CREATE INDEX idx_estadio_edicion_edi   ON estadio_edicion(edicion_id);

-- Selecciones
CREATE INDEX idx_participacion_sel     ON participacion(seleccion_id);
CREATE INDEX idx_participacion_edi     ON participacion(edicion_id);
CREATE INDEX idx_convocatoria_jug      ON convocatoria(jugador_id);
CREATE INDEX idx_convocatoria_par      ON convocatoria(participacion_id);

-- Partidos
CREATE INDEX idx_partido_edicion       ON partido(edicion_id);
CREATE INDEX idx_partido_fase          ON partido(fase_id);
CREATE INDEX idx_partido_fecha         ON partido(fecha_hora);
CREATE INDEX idx_evento_partido        ON evento_partido(partido_id);
CREATE INDEX idx_evento_jugador        ON evento_partido(jugador_id);
CREATE INDEX idx_stats_equipo_partido  ON stats_equipo(partido_id);
CREATE INDEX idx_stats_jugador_partido ON stats_jugador(partido_id);
CREATE INDEX idx_stats_jugador_jug     ON stats_jugador(jugador_id);

-- Histórico
CREATE INDEX idx_hist_resultado_edi    ON historico_resultado(historico_edicion_id);
CREATE INDEX idx_hist_resultado_local  ON historico_resultado(pais_local_id);
CREATE INDEX idx_hist_resultado_visit  ON historico_resultado(pais_visitante_id);

-- Contenido
CREATE INDEX idx_noticia_fuente        ON noticia(fuente_id);
CREATE INDEX idx_noticia_fecha         ON noticia(fecha_publicacion);
CREATE INDEX idx_embedding_noticia     ON embedding(noticia_id);
CREATE INDEX idx_embedding_vector      ON embedding USING ivfflat (vector vector_cosine_ops)
                                       WITH (lists = 100);
CREATE INDEX idx_mencion_noticia       ON mencion(noticia_id);
CREATE INDEX idx_mencion_entidad       ON mencion(entidad_tipo, entidad_id);
CREATE INDEX idx_narrativa_edicion     ON narrativa(edicion_id);
CREATE INDEX idx_narrativa_publicada   ON narrativa(publicada);

-- Alias
CREATE INDEX idx_alias_entidad         ON alias_entidad(entidad_tipo, entidad_id);
CREATE INDEX idx_alias_busqueda        ON alias_entidad(alias);
CREATE INDEX idx_alias_canonico        ON alias_entidad(entidad_tipo, entidad_id, es_canonico);
-- =============================================================================
-- SEED 01 — TORNEO, EDICION, FASE, GRUPO
-- Mundial 2026
-- =============================================================================


-- -----------------------------------------------------------------------------
-- TORNEO
-- -----------------------------------------------------------------------------

INSERT INTO torneo (torneo_id, nombre, nombre_corto, organizador)
VALUES (1, 'Copa Mundial FIFA', 'Mundial', 'FIFA');


-- -----------------------------------------------------------------------------
-- EDICION
-- Formato 2026: 48 equipos, 12 grupos de 4, nueva fase R32
-- -----------------------------------------------------------------------------

INSERT INTO edicion (
    edicion_id, torneo_id, anyo, nombre_oficial,
    num_equipos, num_grupos,
    formato_json,
    fecha_inicio, fecha_fin
)
VALUES (
    1, 1, 2026, 'FIFA World Cup 2026',
    48, 12,
    '{
        "equipos_por_grupo": 4,
        "clasifican_por_grupo": 2,
        "mejores_terceros": 8,
        "total_partidos": 104,
        "nueva_fase": "Round of 32",
        "paises_sede": ["USA", "MEX", "CAN"]
    }'::jsonb,
    '2026-06-11',
    '2026-07-19'
);


-- -----------------------------------------------------------------------------
-- FASE
-- Orden cronológico: GRP(1) → R32(2) → R16(3) → QF(4) → SF(5) → TP(6) → F(7)
-- -----------------------------------------------------------------------------

INSERT INTO fase (fase_id, edicion_id, nombre, codigo, orden, num_partidos, eliminatoria)
VALUES
    (1, 1, 'Fase de grupos',       'GRP', 1, 48,  FALSE),
    (2, 1, 'Round of 32',          'R32', 2, 16,  TRUE),
    (3, 1, 'Octavos de final',     'R16', 3,  8,  TRUE),
    (4, 1, 'Cuartos de final',     'QF',  4,  4,  TRUE),
    (5, 1, 'Semifinales',          'SF',  5,  2,  TRUE),
    (6, 1, 'Tercer y cuarto puesto','TP', 6,  1,  TRUE),
    (7, 1, 'Final',                'F',   7,  1,  TRUE);


-- -----------------------------------------------------------------------------
-- GRUPO
-- 12 grupos (A–L), todos vinculados a la fase de grupos (fase_id = 1)
-- -----------------------------------------------------------------------------

INSERT INTO grupo (grupo_id, edicion_id, fase_id, letra)
VALUES
    ( 1, 1, 1, 'A'),
    ( 2, 1, 1, 'B'),
    ( 3, 1, 1, 'C'),
    ( 4, 1, 1, 'D'),
    ( 5, 1, 1, 'E'),
    ( 6, 1, 1, 'F'),
    ( 7, 1, 1, 'G'),
    ( 8, 1, 1, 'H'),
    ( 9, 1, 1, 'I'),
    (10, 1, 1, 'J'),
    (11, 1, 1, 'K'),
    (12, 1, 1, 'L');


-- -----------------------------------------------------------------------------
-- Ajustar secuencias para evitar colisiones en inserts posteriores
-- -----------------------------------------------------------------------------

SELECT setval('torneo_torneo_id_seq', (SELECT MAX(torneo_id) FROM torneo));
SELECT setval('edicion_edicion_id_seq', (SELECT MAX(edicion_id) FROM edicion));
SELECT setval('fase_fase_id_seq', (SELECT MAX(fase_id) FROM fase));
SELECT setval('grupo_grupo_id_seq', (SELECT MAX(grupo_id) FROM grupo));
-- =============================================================================
-- SEED 02 — PAIS
-- 48 países clasificados para el Mundial 2026
-- Fuente: FIFA oficial / Al Jazeera / Soccerphile
-- Orden: por confederación y luego alfabético
-- =============================================================================


INSERT INTO pais (
    pais_id, nombre, nombre_en, codigo_fifa, codigo_iso2, confederacion, anfitrion_2026
) VALUES

-- -------------------------------------------------------------------------
-- CONCACAF (6 equipos) — 3 anfitriones + 3 clasificados
-- -------------------------------------------------------------------------
( 1, 'México',                  'Mexico',               'MEX', 'MX', 'CONCACAF', TRUE),
( 2, 'Estados Unidos',          'United States',        'USA', 'US', 'CONCACAF', TRUE),
( 3, 'Canadá',                  'Canada',               'CAN', 'CA', 'CONCACAF', TRUE),
( 4, 'Panamá',                  'Panama',               'PAN', 'PA', 'CONCACAF', FALSE),
( 5, 'Haití',                   'Haiti',                'HAI', 'HT', 'CONCACAF', FALSE),
( 6, 'Curazao',                 'Curacao',              'CUW', 'CW', 'CONCACAF', FALSE),

-- -------------------------------------------------------------------------
-- CONMEBOL (6 equipos)
-- -------------------------------------------------------------------------
( 7, 'Argentina',               'Argentina',            'ARG', 'AR', 'CONMEBOL', FALSE),
( 8, 'Brasil',                  'Brazil',               'BRA', 'BR', 'CONMEBOL', FALSE),
( 9, 'Colombia',                'Colombia',             'COL', 'CO', 'CONMEBOL', FALSE),
(10, 'Ecuador',                 'Ecuador',              'ECU', 'EC', 'CONMEBOL', FALSE),
(11, 'Paraguay',                'Paraguay',             'PAR', 'PY', 'CONMEBOL', FALSE),
(12, 'Uruguay',                 'Uruguay',              'URU', 'UY', 'CONMEBOL', FALSE),

-- -------------------------------------------------------------------------
-- UEFA (16 equipos)
-- -------------------------------------------------------------------------
(13, 'Alemania',                'Germany',              'GER', 'DE', 'UEFA', FALSE),
(14, 'Austria',                 'Austria',              'AUT', 'AT', 'UEFA', FALSE),
(15, 'Bélgica',                 'Belgium',              'BEL', 'BE', 'UEFA', FALSE),
(16, 'Bosnia y Herzegovina',    'Bosnia and Herzegovina','BIH','BA', 'UEFA', FALSE),
(17, 'Chequia',                 'Czechia',              'CZE', 'CZ', 'UEFA', FALSE),
(18, 'Croacia',                 'Croatia',              'CRO', 'HR', 'UEFA', FALSE),
(19, 'Escocia',                 'Scotland',             'SCO', 'GB-SCT', 'UEFA', FALSE),
(20, 'España',                  'Spain',                'ESP', 'ES', 'UEFA', FALSE),
(21, 'Francia',                 'France',               'FRA', 'FR', 'UEFA', FALSE),
(22, 'Inglaterra',              'England',              'ENG', 'GB-ENG', 'UEFA', FALSE),
(23, 'Noruega',                 'Norway',               'NOR', 'NO', 'UEFA', FALSE),
(24, 'Países Bajos',            'Netherlands',          'NED', 'NL', 'UEFA', FALSE),
(25, 'Portugal',                'Portugal',             'POR', 'PT', 'UEFA', FALSE),
(26, 'Suecia',                  'Sweden',               'SWE', 'SE', 'UEFA', FALSE),
(27, 'Suiza',                   'Switzerland',          'SUI', 'CH', 'UEFA', FALSE),
(28, 'Turquía',                 'Turkiye',              'TUR', 'TR', 'UEFA', FALSE),

-- -------------------------------------------------------------------------
-- CAF (10 equipos)
-- -------------------------------------------------------------------------
(29, 'Argelia',                 'Algeria',              'ALG', 'DZ', 'CAF', FALSE),
(30, 'Cabo Verde',              'Cape Verde',           'CPV', 'CV', 'CAF', FALSE),
(31, 'Egipto',                  'Egypt',                'EGY', 'EG', 'CAF', FALSE),
(32, 'Ghana',                   'Ghana',                'GHA', 'GH', 'CAF', FALSE),
(33, 'Costa de Marfil',         'Ivory Coast',          'CIV', 'CI', 'CAF', FALSE),
(34, 'Marruecos',               'Morocco',              'MAR', 'MA', 'CAF', FALSE),
(35, 'República Democrática del Congo', 'DR Congo',     'COD', 'CD', 'CAF', FALSE),
(36, 'Senegal',                 'Senegal',              'SEN', 'SN', 'CAF', FALSE),
(37, 'Sudáfrica',               'South Africa',         'RSA', 'ZA', 'CAF', FALSE),
(38, 'Túnez',                   'Tunisia',              'TUN', 'TN', 'CAF', FALSE),

-- -------------------------------------------------------------------------
-- AFC (9 equipos)
-- -------------------------------------------------------------------------
(39, 'Arabia Saudí',            'Saudi Arabia',         'KSA', 'SA', 'AFC', FALSE),
(40, 'Australia',               'Australia',            'AUS', 'AU', 'AFC', FALSE),
(41, 'Corea del Sur',           'Korea Republic',       'KOR', 'KR', 'AFC', FALSE),
(42, 'Irak',                    'Iraq',                 'IRQ', 'IQ', 'AFC', FALSE),
(43, 'Irán',                    'Iran',                 'IRN', 'IR', 'AFC', FALSE),
(44, 'Japón',                   'Japan',                'JPN', 'JP', 'AFC', FALSE),
(45, 'Jordania',                'Jordan',               'JOR', 'JO', 'AFC', FALSE),
(46, 'Qatar',                   'Qatar',                'QAT', 'QA', 'AFC', FALSE),
(47, 'Uzbekistán',              'Uzbekistan',           'UZB', 'UZ', 'AFC', FALSE),

-- -------------------------------------------------------------------------
-- OFC (1 equipo)
-- -------------------------------------------------------------------------
(48, 'Nueva Zelanda',           'New Zealand',          'NZL', 'NZ', 'OFC', FALSE);


-- Ajustar secuencia
SELECT setval('pais_pais_id_seq', (SELECT MAX(pais_id) FROM pais));
-- =============================================================================
-- SEED 03 — CIUDAD_SEDE, ESTADIO, ESTADIO_EDICION
-- 16 sedes oficiales del Mundial 2026
-- Fuente: FIFA oficial / beIN Sports / ESPN
-- Nombres de estadios: nombres reales (nombre oficial FIFA en ALIAS_ENTIDAD)
-- =============================================================================


-- -----------------------------------------------------------------------------
-- CIUDAD_SEDE
-- pais_id: 1=México, 2=USA, 3=Canadá
-- num_partidos: partidos asignados a cada ciudad
-- -----------------------------------------------------------------------------

INSERT INTO ciudad_sede (ciudad_sede_id, edicion_id, pais_id, nombre, nombre_en, num_partidos)
VALUES
-- México (3 ciudades)
( 1, 1,  1, 'Ciudad de México',  'Mexico City',          7),
( 2, 1,  1, 'Guadalajara',       'Guadalajara',          5),
( 3, 1,  1, 'Monterrey',         'Monterrey',            5),

-- Estados Unidos (11 ciudades)
( 4, 1,  2, 'Nueva York/Nueva Jersey', 'New York/New Jersey',  8),
( 5, 1,  2, 'Los Ángeles',       'Los Angeles',          8),
( 6, 1,  2, 'Dallas',            'Dallas',               8),
( 7, 1,  2, 'San Francisco',     'San Francisco Bay Area', 7),
( 8, 1,  2, 'Miami',             'Miami',                6),
( 9, 1,  2, 'Atlanta',           'Atlanta',              6),
(10, 1,  2, 'Seattle',           'Seattle',              6),
(11, 1,  2, 'Houston',           'Houston',              6),
(12, 1,  2, 'Filadelfia',        'Philadelphia',         6),
(13, 1,  2, 'Kansas City',       'Kansas City',          6),
(14, 1,  2, 'Boston',            'Boston',               6),

-- Canadá (2 ciudades)
(15, 1,  3, 'Toronto',           'Toronto',              6),
(16, 1,  3, 'Vancouver',         'Vancouver',            6);


-- -----------------------------------------------------------------------------
-- ESTADIO
-- nombre_oficial: nombre real del estadio (pre-Mundial)
-- nombre FIFA durante el torneo va en ALIAS_ENTIDAD
-- superficie: césped natural en todos los estadios NFL adaptados
-- pais_id: 1=México, 2=USA, 3=Canadá
-- -----------------------------------------------------------------------------

INSERT INTO estadio (
    estadio_id, pais_id, ciudad, capacidad,
    superficie, techo, latitud, longitud
)
VALUES
-- -------------------------------------------------------------------------
-- MÉXICO
-- -------------------------------------------------------------------------
( 1,  1, 'Ciudad de México',  87000,  'cesped_natural',     FALSE,  19.303056, -99.150556),  -- Estadio Azteca
( 2,  1, 'Zapopan',           49850,  'cesped_natural',     FALSE,  20.686944, -103.467222), -- Estadio Akron
( 3,  1, 'Guadalupe',         53500,  'cesped_natural',     FALSE,  25.669722, -100.245833), -- Estadio BBVA

-- -------------------------------------------------------------------------
-- ESTADOS UNIDOS
-- -------------------------------------------------------------------------
( 4,  2, 'East Rutherford',   82500,  'cesped_natural',     FALSE,  40.813611, -74.074167), -- MetLife Stadium
( 5,  2, 'Inglewood',         70240,  'cesped_artificial',  TRUE,   33.953333, -118.339167),-- SoFi Stadium
( 6,  2, 'Arlington',         80000,  'cesped_artificial',  TRUE,   32.748333, -97.092778), -- AT&T Stadium
( 7,  2, 'Santa Clara',       68500,  'cesped_natural',     FALSE,  37.403333, -121.969722),-- Levi's Stadium
( 8,  2, 'Miami Gardens',     64767,  'cesped_natural',     FALSE,  25.957917, -80.238889), -- Hard Rock Stadium
( 9,  2, 'Atlanta',           71000,  'cesped_artificial',  TRUE,   33.755278, -84.401111), -- Mercedes-Benz Stadium
(10,  2, 'Seattle',           68740,  'cesped_artificial',  FALSE,  47.595278, -122.331667),-- Lumen Field
(11,  2, 'Houston',           72220,  'cesped_natural',     TRUE,   29.684722, -95.410833), -- NRG Stadium
(12,  2, 'Filadelfia',        67594,  'cesped_natural',     FALSE,  39.900833, -75.167500), -- Lincoln Financial Field
(13,  2, 'Kansas City',       76416,  'cesped_natural',     FALSE,  39.048889, -94.483889), -- Arrowhead Stadium
(14,  2, 'Foxborough',        65878,  'cesped_natural',     FALSE,  42.090833, -71.264444), -- Gillette Stadium

-- -------------------------------------------------------------------------
-- CANADÁ
-- -------------------------------------------------------------------------
(15,  3, 'Toronto',           44815,  'cesped_natural',     FALSE,  43.633056, -79.418889), -- BMO Field
(16,  3, 'Vancouver',         54500,  'cesped_artificial',  TRUE,   49.276667, -123.111944);-- BC Place


-- -----------------------------------------------------------------------------
-- ESTADIO_EDICION
-- Vincula cada estadio con la edición 2026 y su ciudad sede
-- num_partidos: partidos jugados en ese estadio
-- -----------------------------------------------------------------------------

INSERT INTO estadio_edicion (estadio_edicion_id, estadio_id, edicion_id, ciudad_sede_id, num_partidos)
VALUES
-- México
( 1,  1, 1,  1, 7),   -- Azteca       → Ciudad de México
( 2,  2, 1,  2, 5),   -- Akron        → Guadalajara
( 3,  3, 1,  3, 5),   -- BBVA         → Monterrey

-- Estados Unidos
( 4,  4, 1,  4, 8),   -- MetLife      → Nueva York/NJ
( 5,  5, 1,  5, 8),   -- SoFi         → Los Ángeles
( 6,  6, 1,  6, 8),   -- AT&T         → Dallas
( 7,  7, 1,  7, 7),   -- Levi's       → San Francisco
( 8,  8, 1,  8, 6),   -- Hard Rock    → Miami
( 9,  9, 1,  9, 6),   -- Mercedes-Benz→ Atlanta
(10, 10, 1, 10, 6),   -- Lumen Field  → Seattle
(11, 11, 1, 11, 6),   -- NRG          → Houston
(12, 12, 1, 12, 6),   -- Lincoln Fin. → Filadelfia
(13, 13, 1, 13, 6),   -- Arrowhead    → Kansas City
(14, 14, 1, 14, 6),   -- Gillette     → Boston

-- Canadá
(15, 15, 1, 15, 6),   -- BMO Field    → Toronto
(16, 16, 1, 16, 6);   -- BC Place     → Vancouver


-- Ajustar secuencias
SELECT setval('ciudad_sede_ciudad_sede_id_seq', (SELECT MAX(ciudad_sede_id) FROM ciudad_sede));
SELECT setval('estadio_estadio_id_seq',         (SELECT MAX(estadio_id)     FROM estadio));
SELECT setval('estadio_edicion_estadio_edicion_id_seq', (SELECT MAX(estadio_edicion_id) FROM estadio_edicion));
-- =============================================================================
-- SEED 04 — SELECCION
-- 48 selecciones del Mundial 2026
-- pais_id y codigo_fifa heredados del seed 02 (PAIS)
-- colores: color principal y secundario de cada camiseta
-- =============================================================================

INSERT INTO seleccion (
    seleccion_id, pais_id, codigo_fifa, confederacion,
    color_principal, color_secundario
)
VALUES

-- -------------------------------------------------------------------------
-- CONCACAF (6)
-- -------------------------------------------------------------------------
( 1,  1, 'MEX', 'CONCACAF', '#006847', '#FFFFFF'),  -- México
( 2,  2, 'USA', 'CONCACAF', '#002868', '#FFFFFF'),  -- Estados Unidos
( 3,  3, 'CAN', 'CONCACAF', '#FF0000', '#FFFFFF'),  -- Canadá
( 4,  4, 'PAN', 'CONCACAF', '#DA121A', '#FFFFFF'),  -- Panamá
( 5,  5, 'HAI', 'CONCACAF', '#00209F', '#D21034'),  -- Haití
( 6,  6, 'CUW', 'CONCACAF', '#003DA5', '#F9E526'),  -- Curazao

-- -------------------------------------------------------------------------
-- CONMEBOL (6)
-- -------------------------------------------------------------------------
( 7,  7, 'ARG', 'CONMEBOL', '#74ACDF', '#FFFFFF'),  -- Argentina
( 8,  8, 'BRA', 'CONMEBOL', '#009C3B', '#FFDF00'),  -- Brasil
( 9,  9, 'COL', 'CONMEBOL', '#FCD116', '#003087'),  -- Colombia
(10, 10, 'ECU', 'CONMEBOL', '#FFD100', '#003087'),  -- Ecuador
(11, 11, 'PAR', 'CONMEBOL', '#D52B1E', '#FFFFFF'),  -- Paraguay
(12, 12, 'URU', 'CONMEBOL', '#5EB6E4', '#FFFFFF'),  -- Uruguay

-- -------------------------------------------------------------------------
-- UEFA (16)
-- -------------------------------------------------------------------------
(13, 13, 'GER', 'UEFA', '#FFFFFF', '#000000'),  -- Alemania
(14, 14, 'AUT', 'UEFA', '#ED2939', '#FFFFFF'),  -- Austria
(15, 15, 'BEL', 'UEFA', '#000000', '#FF0000'),  -- Bélgica
(16, 16, 'BIH', 'UEFA', '#002395', '#FFCD00'),  -- Bosnia y Herzegovina
(17, 17, 'CZE', 'UEFA', '#D7141A', '#FFFFFF'),  -- Chequia
(18, 18, 'CRO', 'UEFA', '#FF0000', '#FFFFFF'),  -- Croacia
(19, 19, 'SCO', 'UEFA', '#003087', '#FFFFFF'),  -- Escocia
(20, 20, 'ESP', 'UEFA', '#AA151B', '#F1BF00'),  -- España
(21, 21, 'FRA', 'UEFA', '#002395', '#FFFFFF'),  -- Francia
(22, 22, 'ENG', 'UEFA', '#FFFFFF', '#003090'),  -- Inglaterra
(23, 23, 'NOR', 'UEFA', '#EF2B2D', '#FFFFFF'),  -- Noruega
(24, 24, 'NED', 'UEFA', '#FF6600', '#FFFFFF'),  -- Países Bajos
(25, 25, 'POR', 'UEFA', '#006600', '#FF0000'),  -- Portugal
(26, 26, 'SWE', 'UEFA', '#006AA7', '#FECC02'),  -- Suecia
(27, 27, 'SUI', 'UEFA', '#FF0000', '#FFFFFF'),  -- Suiza
(28, 28, 'TUR', 'UEFA', '#E30A17', '#FFFFFF'),  -- Turquía

-- -------------------------------------------------------------------------
-- CAF (10)
-- -------------------------------------------------------------------------
(29, 29, 'ALG', 'CAF', '#FFFFFF', '#006233'),  -- Algeria
(30, 30, 'CPV', 'CAF', '#003893', '#CF2027'),  -- Cabo Verde
(31, 31, 'EGY', 'CAF', '#CE1126', '#FFFFFF'),  -- Egipto
(32, 32, 'GHA', 'CAF', '#006B3F', '#FFFFFF'),  -- Ghana
(33, 33, 'CIV', 'CAF', '#F77F00', '#FFFFFF'),  -- Costa de Marfil
(34, 34, 'MAR', 'CAF', '#C1272D', '#006233'),  -- Marruecos
(35, 35, 'COD', 'CAF', '#007FFF', '#F7D618'),  -- DR Congo
(36, 36, 'SEN', 'CAF', '#00853F', '#FFFFFF'),  -- Senegal
(37, 37, 'RSA', 'CAF', '#007A4D', '#FFB81C'),  -- Sudáfrica
(38, 38, 'TUN', 'CAF', '#E70013', '#FFFFFF'),  -- Túnez

-- -------------------------------------------------------------------------
-- AFC (9)
-- -------------------------------------------------------------------------
(39, 39, 'KSA', 'AFC', '#006C35', '#FFFFFF'),  -- Arabia Saudí
(40, 40, 'AUS', 'AFC', '#FFD700', '#006400'),  -- Australia
(41, 41, 'KOR', 'AFC', '#CD2E3A', '#FFFFFF'),  -- Corea del Sur
(42, 42, 'IRQ', 'AFC', '#CE1126', '#FFFFFF'),  -- Irak
(43, 43, 'IRN', 'AFC', '#239F40', '#FFFFFF'),  -- Irán
(44, 44, 'JPN', 'AFC', '#000080', '#FFFFFF'),  -- Japón
(45, 45, 'JOR', 'AFC', '#007A3D', '#FFFFFF'),  -- Jordania
(46, 46, 'QAT', 'AFC', '#8D1B3D', '#FFFFFF'),  -- Qatar
(47, 47, 'UZB', 'AFC', '#1EB53A', '#FFFFFF'),  -- Uzbekistán

-- -------------------------------------------------------------------------
-- OFC (1)
-- -------------------------------------------------------------------------
(48, 48, 'NZL', 'OFC', '#FFFFFF', '#000000');  -- Nueva Zelanda


-- Ajustar secuencia
SELECT setval('seleccion_seleccion_id_seq', (SELECT MAX(seleccion_id) FROM seleccion));
-- =============================================================================
-- SEED 05 — ALIAS_ENTIDAD
-- Nombres alternativos para estadios, selecciones y países
-- Reglas:
--   · es_canonico = TRUE  → nombre que se publica y aparece en la tabla principal
--   · es_canonico = FALSE → variantes de fuentes externas o prensa
--   · Una sola fila con es_canonico = TRUE por entidad
-- =============================================================================


-- -----------------------------------------------------------------------------
-- ESTADIOS — nombres reales (canónico) vs nombres FIFA durante el torneo
-- entidad_tipo = 'estadio', entidad_id = estadio_id del seed 03
-- -----------------------------------------------------------------------------

INSERT INTO alias_entidad (entidad_tipo, entidad_id, alias, fuente, idioma, es_canonico)
VALUES

-- Estadio Azteca (estadio_id = 1)
('estadio', 1, 'Estadio Azteca',             'manual',       'es', TRUE),
('estadio', 1, 'Mexico City Stadium',         'manual',       'en', FALSE),  -- nombre FIFA 2026
('estadio', 1, 'Estadio Ciudad de México',    'manual',       'es', FALSE),
('estadio', 1, 'Azteca',                      'prensa',       'es', FALSE),

-- Estadio Akron (estadio_id = 2)
('estadio', 2, 'Estadio Akron',              'manual',       'es', TRUE),
('estadio', 2, 'Guadalajara Stadium',         'manual',       'en', FALSE),  -- nombre FIFA 2026
('estadio', 2, 'Estadio Guadalajara',         'manual',       'es', FALSE),

-- Estadio BBVA (estadio_id = 3)
('estadio', 3, 'Estadio BBVA',               'manual',       'es', TRUE),
('estadio', 3, 'Monterrey Stadium',           'manual',       'en', FALSE),  -- nombre FIFA 2026
('estadio', 3, 'Estadio Monterrey',           'manual',       'es', FALSE),

-- MetLife Stadium (estadio_id = 4)
('estadio', 4, 'MetLife Stadium',             'manual',       'en', TRUE),
('estadio', 4, 'New York New Jersey Stadium', 'manual',       'en', FALSE),  -- nombre FIFA 2026
('estadio', 4, 'MetLife',                     'prensa',       'en', FALSE),

-- SoFi Stadium (estadio_id = 5)
('estadio', 5, 'SoFi Stadium',               'manual',       'en', TRUE),
('estadio', 5, 'Los Angeles Stadium',         'manual',       'en', FALSE),  -- nombre FIFA 2026
('estadio', 5, 'Inglewood Stadium',           'prensa',       'en', FALSE),
('estadio', 5, 'SoFi',                        'prensa',       'en', FALSE),

-- AT&T Stadium (estadio_id = 6)
('estadio', 6, 'AT&T Stadium',               'manual',       'en', TRUE),
('estadio', 6, 'Dallas Stadium',              'manual',       'en', FALSE),  -- nombre FIFA 2026
('estadio', 6, 'Cowboys Stadium',             'prensa',       'en', FALSE),  -- nombre histórico

-- Levi's Stadium (estadio_id = 7)
('estadio', 7, 'Levi''s Stadium',            'manual',       'en', TRUE),
('estadio', 7, 'San Francisco Bay Area Stadium', 'manual',   'en', FALSE),  -- nombre FIFA 2026
('estadio', 7, 'Levis Stadium',              'fbref',        'en', FALSE),

-- Hard Rock Stadium (estadio_id = 8)
('estadio', 8, 'Hard Rock Stadium',          'manual',       'en', TRUE),
('estadio', 8, 'Miami Stadium',              'manual',       'en', FALSE),  -- nombre FIFA 2026
('estadio', 8, 'Hard Rock',                  'prensa',       'en', FALSE),

-- Mercedes-Benz Stadium (estadio_id = 9)
('estadio', 9, 'Mercedes-Benz Stadium',      'manual',       'en', TRUE),
('estadio', 9, 'Atlanta Stadium',            'manual',       'en', FALSE),  -- nombre FIFA 2026
('estadio', 9, 'Mercedes Benz Stadium',      'fbref',        'en', FALSE),

-- Lumen Field (estadio_id = 10)
('estadio', 10, 'Lumen Field',              'manual',       'en', TRUE),
('estadio', 10, 'Seattle Stadium',           'manual',       'en', FALSE),  -- nombre FIFA 2026
('estadio', 10, 'CenturyLink Field',         'prensa',       'en', FALSE),  -- nombre histórico

-- NRG Stadium (estadio_id = 11)
('estadio', 11, 'NRG Stadium',              'manual',       'en', TRUE),
('estadio', 11, 'Houston Stadium',           'manual',       'en', FALSE),  -- nombre FIFA 2026

-- Lincoln Financial Field (estadio_id = 12)
('estadio', 12, 'Lincoln Financial Field',  'manual',       'en', TRUE),
('estadio', 12, 'Philadelphia Stadium',      'manual',       'en', FALSE),  -- nombre FIFA 2026
('estadio', 12, 'The Linc',                  'prensa',       'en', FALSE),

-- Arrowhead Stadium (estadio_id = 13)
('estadio', 13, 'Arrowhead Stadium',        'manual',       'en', TRUE),
('estadio', 13, 'Kansas City Stadium',       'manual',       'en', FALSE),  -- nombre FIFA 2026
('estadio', 13, 'GEHA Field at Arrowhead Stadium', 'manual','en', FALSE),

-- Gillette Stadium (estadio_id = 14)
('estadio', 14, 'Gillette Stadium',         'manual',       'en', TRUE),
('estadio', 14, 'Boston Stadium',            'manual',       'en', FALSE),  -- nombre FIFA 2026

-- BMO Field (estadio_id = 15)
('estadio', 15, 'BMO Field',               'manual',       'en', TRUE),
('estadio', 15, 'Toronto Stadium',           'manual',       'en', FALSE),  -- nombre FIFA 2026

-- BC Place (estadio_id = 16)
('estadio', 16, 'BC Place',                'manual',       'en', TRUE),
('estadio', 16, 'Vancouver Stadium',         'manual',       'en', FALSE);  -- nombre FIFA 2026


-- -----------------------------------------------------------------------------
-- SELECCIONES — variantes de nombre más habituales en fuentes y prensa
-- entidad_tipo = 'seleccion', entidad_id = seleccion_id del seed 04
-- -----------------------------------------------------------------------------

INSERT INTO alias_entidad (entidad_tipo, entidad_id, alias, fuente, idioma, es_canonico)
VALUES

-- México (1)
('seleccion', 1,  'México',               'manual',           'es', TRUE),
('seleccion', 1,  'Mexico',               'football_data',    'en', FALSE),
('seleccion', 1,  'El Tri',               'prensa',           'es', FALSE),

-- Estados Unidos (2)
('seleccion', 2,  'Estados Unidos',       'manual',           'es', TRUE),
('seleccion', 2,  'United States',        'football_data',    'en', FALSE),
('seleccion', 2,  'USA',                  'football_data',    'en', FALSE),
('seleccion', 2,  'USMNT',               'prensa',           'en', FALSE),

-- Canadá (3)
('seleccion', 3,  'Canadá',              'manual',           'es', TRUE),
('seleccion', 3,  'Canada',              'football_data',    'en', FALSE),

-- Panamá (4)
('seleccion', 4,  'Panamá',             'manual',           'es', TRUE),
('seleccion', 4,  'Panama',             'football_data',    'en', FALSE),

-- Haití (5)
('seleccion', 5,  'Haití',              'manual',           'es', TRUE),
('seleccion', 5,  'Haiti',              'football_data',    'en', FALSE),

-- Curazao (6)
('seleccion', 6,  'Curazao',            'manual',           'es', TRUE),
('seleccion', 6,  'Curacao',            'football_data',    'en', FALSE),
('seleccion', 6,  'Curaçao',            'prensa',           'en', FALSE),

-- Argentina (7)
('seleccion', 7,  'Argentina',          'manual',           'es', TRUE),
('seleccion', 7,  'La Albiceleste',     'prensa',           'es', FALSE),

-- Brasil (8)
('seleccion', 8,  'Brasil',             'manual',           'es', TRUE),
('seleccion', 8,  'Brazil',             'football_data',    'en', FALSE),
('seleccion', 8,  'La Canarinha',       'prensa',           'es', FALSE),
('seleccion', 8,  'La Verdeamarela',    'prensa',           'es', FALSE),

-- Colombia (9)
('seleccion', 9,  'Colombia',           'manual',           'es', TRUE),
('seleccion', 9,  'Los Cafeteros',      'prensa',           'es', FALSE),

-- Ecuador (10)
('seleccion', 10, 'Ecuador',            'manual',           'es', TRUE),
('seleccion', 10, 'La Tri',             'prensa',           'es', FALSE),

-- Paraguay (11)
('seleccion', 11, 'Paraguay',           'manual',           'es', TRUE),
('seleccion', 11, 'La Albirroja',       'prensa',           'es', FALSE),

-- Uruguay (12)
('seleccion', 12, 'Uruguay',            'manual',           'es', TRUE),
('seleccion', 12, 'La Celeste',         'prensa',           'es', FALSE),

-- Alemania (13)
('seleccion', 13, 'Alemania',           'manual',           'es', TRUE),
('seleccion', 13, 'Germany',            'football_data',    'en', FALSE),
('seleccion', 13, 'Die Mannschaft',     'prensa',           'de', FALSE),

-- Austria (14)
('seleccion', 14, 'Austria',            'manual',           'es', TRUE),

-- Bélgica (15)
('seleccion', 15, 'Bélgica',           'manual',           'es', TRUE),
('seleccion', 15, 'Belgium',            'football_data',    'en', FALSE),
('seleccion', 15, 'Los Diablos Rojos',  'prensa',           'es', FALSE),
('seleccion', 15, 'Red Devils',         'prensa',           'en', FALSE),

-- Bosnia y Herzegovina (16)
('seleccion', 16, 'Bosnia y Herzegovina', 'manual',         'es', TRUE),
('seleccion', 16, 'Bosnia and Herzegovina', 'football_data','en', FALSE),
('seleccion', 16, 'Bosnia',             'prensa',           'es', FALSE),
('seleccion', 16, 'Bosnia & Herzegovina', 'fbref',          'en', FALSE),

-- Chequia (17)
('seleccion', 17, 'Chequia',            'manual',           'es', TRUE),
('seleccion', 17, 'Czech Republic',     'football_data',    'en', FALSE),
('seleccion', 17, 'Czechia',            'fbref',            'en', FALSE),

-- Croacia (18)
('seleccion', 18, 'Croacia',            'manual',           'es', TRUE),
('seleccion', 18, 'Croatia',            'football_data',    'en', FALSE),
('seleccion', 18, 'Los Vatreni',        'prensa',           'es', FALSE),

-- Escocia (19)
('seleccion', 19, 'Escocia',            'manual',           'es', TRUE),
('seleccion', 19, 'Scotland',           'football_data',    'en', FALSE),

-- España (20)
('seleccion', 20, 'España',             'manual',           'es', TRUE),
('seleccion', 20, 'Spain',              'football_data',    'en', FALSE),
('seleccion', 20, 'La Roja',            'prensa',           'es', FALSE),
('seleccion', 20, 'La Furia Española',  'prensa',           'es', FALSE),

-- Francia (21)
('seleccion', 21, 'Francia',            'manual',           'es', TRUE),
('seleccion', 21, 'France',             'football_data',    'en', FALSE),
('seleccion', 21, 'Les Bleus',          'prensa',           'fr', FALSE),

-- Inglaterra (22)
('seleccion', 22, 'Inglaterra',         'manual',           'es', TRUE),
('seleccion', 22, 'England',            'football_data',    'en', FALSE),
('seleccion', 22, 'Los Tres Leones',    'prensa',           'es', FALSE),
('seleccion', 22, 'Three Lions',        'prensa',           'en', FALSE),

-- Noruega (23)
('seleccion', 23, 'Noruega',            'manual',           'es', TRUE),
('seleccion', 23, 'Norway',             'football_data',    'en', FALSE),

-- Países Bajos (24)
('seleccion', 24, 'Países Bajos',       'manual',           'es', TRUE),
('seleccion', 24, 'Netherlands',        'football_data',    'en', FALSE),
('seleccion', 24, 'Holanda',            'prensa',           'es', FALSE),
('seleccion', 24, 'Holland',            'prensa',           'en', FALSE),
('seleccion', 24, 'La Naranja Mecánica','prensa',           'es', FALSE),

-- Portugal (25)
('seleccion', 25, 'Portugal',           'manual',           'es', TRUE),
('seleccion', 25, 'A Seleção',          'prensa',           'pt', FALSE),

-- Suecia (26)
('seleccion', 26, 'Suecia',             'manual',           'es', TRUE),
('seleccion', 26, 'Sweden',             'football_data',    'en', FALSE),

-- Suiza (27)
('seleccion', 27, 'Suiza',              'manual',           'es', TRUE),
('seleccion', 27, 'Switzerland',        'football_data',    'en', FALSE),

-- Turquía (28)
('seleccion', 28, 'Turquía',            'manual',           'es', TRUE),
('seleccion', 28, 'Turkiye',            'football_data',    'en', FALSE),
('seleccion', 28, 'Turkey',             'fbref',            'en', FALSE),

-- Argelia (29)
('seleccion', 29, 'Argelia',            'manual',           'es', TRUE),
('seleccion', 29, 'Algeria',            'football_data',    'en', FALSE),
('seleccion', 29, 'Les Fennecs',        'prensa',           'fr', FALSE),

-- Cabo Verde (30)
('seleccion', 30, 'Cabo Verde',         'manual',           'es', TRUE),
('seleccion', 30, 'Cape Verde',         'football_data',    'en', FALSE),

-- Egipto (31)
('seleccion', 31, 'Egipto',             'manual',           'es', TRUE),
('seleccion', 31, 'Egypt',              'football_data',    'en', FALSE),
('seleccion', 31, 'Los Faraones',       'prensa',           'es', FALSE),

-- Ghana (32)
('seleccion', 32, 'Ghana',              'manual',           'es', TRUE),
('seleccion', 32, 'Black Stars',        'prensa',           'en', FALSE),

-- Costa de Marfil (33)
('seleccion', 33, 'Costa de Marfil',    'manual',           'es', TRUE),
('seleccion', 33, 'Ivory Coast',        'football_data',    'en', FALSE),
('seleccion', 33, 'Côte d''Ivoire',     'fbref',            'fr', FALSE),
('seleccion', 33, 'Cote d''Ivoire',     'football_data',    'en', FALSE),

-- Marruecos (34)
('seleccion', 34, 'Marruecos',          'manual',           'es', TRUE),
('seleccion', 34, 'Morocco',            'football_data',    'en', FALSE),
('seleccion', 34, 'Los Leones del Atlas','prensa',          'es', FALSE),
('seleccion', 34, 'Atlas Lions',        'prensa',           'en', FALSE),

-- DR Congo (35)
('seleccion', 35, 'República Democrática del Congo', 'manual','es', TRUE),
('seleccion', 35, 'DR Congo',           'football_data',    'en', FALSE),
('seleccion', 35, 'Congo DR',           'fbref',            'en', FALSE),
('seleccion', 35, 'RD Congo',           'prensa',           'es', FALSE),

-- Senegal (36)
('seleccion', 36, 'Senegal',            'manual',           'es', TRUE),
('seleccion', 36, 'Los Leones de Teranga','prensa',         'es', FALSE),
('seleccion', 36, 'Lions of Teranga',   'prensa',           'en', FALSE),

-- Sudáfrica (37)
('seleccion', 37, 'Sudáfrica',          'manual',           'es', TRUE),
('seleccion', 37, 'South Africa',       'football_data',    'en', FALSE),
('seleccion', 37, 'Bafana Bafana',      'prensa',           'en', FALSE),

-- Túnez (38)
('seleccion', 38, 'Túnez',              'manual',           'es', TRUE),
('seleccion', 38, 'Tunisia',            'football_data',    'en', FALSE),

-- Arabia Saudí (39)
('seleccion', 39, 'Arabia Saudí',       'manual',           'es', TRUE),
('seleccion', 39, 'Saudi Arabia',       'football_data',    'en', FALSE),
('seleccion', 39, 'Arabia Saúdita',     'prensa',           'es', FALSE),

-- Australia (40)
('seleccion', 40, 'Australia',          'manual',           'es', TRUE),
('seleccion', 40, 'Socceroos',          'prensa',           'en', FALSE),

-- Corea del Sur (41)
('seleccion', 41, 'Corea del Sur',      'manual',           'es', TRUE),
('seleccion', 41, 'Korea Republic',     'football_data',    'en', FALSE),
('seleccion', 41, 'South Korea',        'fbref',            'en', FALSE),

-- Irak (42)
('seleccion', 42, 'Irak',               'manual',           'es', TRUE),
('seleccion', 42, 'Iraq',               'football_data',    'en', FALSE),

-- Irán (43)
('seleccion', 43, 'Irán',               'manual',           'es', TRUE),
('seleccion', 43, 'Iran',               'football_data',    'en', FALSE),

-- Japón (44)
('seleccion', 44, 'Japón',              'manual',           'es', TRUE),
('seleccion', 44, 'Japan',              'football_data',    'en', FALSE),
('seleccion', 44, 'Samurai Azul',       'prensa',           'es', FALSE),

-- Jordania (45)
('seleccion', 45, 'Jordania',           'manual',           'es', TRUE),
('seleccion', 45, 'Jordan',             'football_data',    'en', FALSE),

-- Qatar (46)
('seleccion', 46, 'Qatar',              'manual',           'es', TRUE),

-- Uzbekistán (47)
('seleccion', 47, 'Uzbekistán',         'manual',           'es', TRUE),
('seleccion', 47, 'Uzbekistan',         'football_data',    'en', FALSE),

-- Nueva Zelanda (48)
('seleccion', 48, 'Nueva Zelanda',      'manual',           'es', TRUE),
('seleccion', 48, 'New Zealand',        'football_data',    'en', FALSE),
('seleccion', 48, 'All Whites',         'prensa',           'en', FALSE);
-- =============================================================================
-- SEED 06 — PARTICIPACION y FUENTE
-- =============================================================================


-- -----------------------------------------------------------------------------
-- PARTICIPACION
-- 48 selecciones × edición 2026
-- seleccion_id: del seed 04
-- grupo_id: 1=A, 2=B, 3=C, 4=D, 5=E, 6=F, 7=G, 8=H, 9=I, 10=J, 11=K, 12=L
-- dt_id: NULL — se poblará en pipeline cuando tengamos entidad DT
-- resultado_final: NULL — se rellena al terminar el torneo
-- clasificacion_via: anfitrion para MEX/USA/CAN, clasificatorio para el resto
-- posicion_fifa_previa: ranking FIFA abril 2026
-- Fuente grupos: FIFA oficial / Al Jazeera mayo 2026
-- -----------------------------------------------------------------------------

INSERT INTO participacion (
    participacion_id, seleccion_id, edicion_id, grupo_id,
    dt_id, clasificacion_via, resultado_final, posicion_fifa_previa
)
VALUES

-- -------------------------------------------------------------------------
-- GRUPO A: México, Sudáfrica, Corea del Sur, Chequia
-- -------------------------------------------------------------------------
( 1,  1, 1,  1, NULL, 'anfitrion',      NULL, 16),  -- México
( 2, 37, 1,  1, NULL, 'clasificatorio', NULL, 61),  -- Sudáfrica
( 3, 41, 1,  1, NULL, 'clasificatorio', NULL, 23),  -- Corea del Sur
( 4, 17, 1,  1, NULL, 'clasificatorio', NULL, 37),  -- Chequia

-- -------------------------------------------------------------------------
-- GRUPO B: Canadá, Bosnia y Herzegovina, Qatar, Suiza
-- -------------------------------------------------------------------------
( 5,  3, 1,  2, NULL, 'anfitrion',      NULL, 41),  -- Canadá
( 6, 16, 1,  2, NULL, 'clasificatorio', NULL, 62),  -- Bosnia y Herzegovina
( 7, 46, 1,  2, NULL, 'clasificatorio', NULL, 58),  -- Qatar
( 8, 27, 1,  2, NULL, 'clasificatorio', NULL, 19),  -- Suiza

-- -------------------------------------------------------------------------
-- GRUPO C: Brasil, Marruecos, Haití, Escocia
-- -------------------------------------------------------------------------
( 9,  8, 1,  3, NULL, 'clasificatorio', NULL,  4),  -- Brasil
(10, 34, 1,  3, NULL, 'clasificatorio', NULL, 14),  -- Marruecos
(11,  5, 1,  3, NULL, 'clasificatorio', NULL, 83),  -- Haití
(12, 19, 1,  3, NULL, 'clasificatorio', NULL, 39),  -- Escocia

-- -------------------------------------------------------------------------
-- GRUPO D: Estados Unidos, Paraguay, Australia, Turquía
-- -------------------------------------------------------------------------
(13,  2, 1,  4, NULL, 'anfitrion',      NULL, 11),  -- Estados Unidos
(14, 11, 1,  4, NULL, 'clasificatorio', NULL, 63),  -- Paraguay
(15, 40, 1,  4, NULL, 'clasificatorio', NULL, 24),  -- Australia
(16, 28, 1,  4, NULL, 'clasificatorio', NULL, 29),  -- Turquía

-- -------------------------------------------------------------------------
-- GRUPO E: Alemania, Curazao, Costa de Marfil, Ecuador
-- -------------------------------------------------------------------------
(17, 13, 1,  5, NULL, 'clasificatorio', NULL, 12),  -- Alemania
(18,  6, 1,  5, NULL, 'clasificatorio', NULL, 81),  -- Curazao
(19, 33, 1,  5, NULL, 'clasificatorio', NULL, 48),  -- Costa de Marfil
(20, 10, 1,  5, NULL, 'clasificatorio', NULL, 44),  -- Ecuador

-- -------------------------------------------------------------------------
-- GRUPO F: Países Bajos, Japón, Suecia, Túnez
-- -------------------------------------------------------------------------
(21, 24, 1,  6, NULL, 'clasificatorio', NULL,  7),  -- Países Bajos
(22, 44, 1,  6, NULL, 'clasificatorio', NULL, 18),  -- Japón
(23, 26, 1,  6, NULL, 'clasificatorio', NULL, 26),  -- Suecia
(24, 38, 1,  6, NULL, 'clasificatorio', NULL, 30),  -- Túnez

-- -------------------------------------------------------------------------
-- GRUPO G: Bélgica, Egipto, Irán, Nueva Zelanda
-- -------------------------------------------------------------------------
(25, 15, 1,  7, NULL, 'clasificatorio', NULL,  3),  -- Bélgica
(26, 31, 1,  7, NULL, 'clasificatorio', NULL, 35),  -- Egipto
(27, 43, 1,  7, NULL, 'clasificatorio', NULL, 22),  -- Irán
(28, 48, 1,  7, NULL, 'clasificatorio', NULL, 97),  -- Nueva Zelanda

-- -------------------------------------------------------------------------
-- GRUPO H: España, Cabo Verde, Arabia Saudí, Uruguay
-- -------------------------------------------------------------------------
(29, 20, 1,  8, NULL, 'clasificatorio', NULL,  2),  -- España
(30, 30, 1,  8, NULL, 'clasificatorio', NULL, 73),  -- Cabo Verde
(31, 39, 1,  8, NULL, 'clasificatorio', NULL, 56),  -- Arabia Saudí
(32, 12, 1,  8, NULL, 'clasificatorio', NULL, 17),  -- Uruguay

-- -------------------------------------------------------------------------
-- GRUPO I: Francia, Senegal, Irak, Noruega
-- -------------------------------------------------------------------------
(33, 21, 1,  9, NULL, 'clasificatorio', NULL,  1),  -- Francia
(34, 36, 1,  9, NULL, 'clasificatorio', NULL, 20),  -- Senegal
(35, 42, 1,  9, NULL, 'clasificatorio', NULL, 59),  -- Irak
(36, 23, 1,  9, NULL, 'clasificatorio', NULL, 27),  -- Noruega

-- -------------------------------------------------------------------------
-- GRUPO J: Argentina, Argelia, Austria, Jordania
-- -------------------------------------------------------------------------
(37,  7, 1, 10, NULL, 'campeon_defensor', NULL,  5),  -- Argentina
(38, 29, 1, 10, NULL, 'clasificatorio',   NULL, 36),  -- Argelia
(39, 14, 1, 10, NULL, 'clasificatorio',   NULL, 25),  -- Austria
(40, 45, 1, 10, NULL, 'clasificatorio',   NULL, 87),  -- Jordania

-- -------------------------------------------------------------------------
-- GRUPO K: Portugal, DR Congo, Uzbekistán, Colombia
-- -------------------------------------------------------------------------
(41, 25, 1, 11, NULL, 'clasificatorio', NULL,  6),  -- Portugal
(42, 35, 1, 11, NULL, 'clasificatorio', NULL, 52),  -- DR Congo
(43, 47, 1, 11, NULL, 'clasificatorio', NULL, 69),  -- Uzbekistán
(44,  9, 1, 11, NULL, 'clasificatorio', NULL,  9),  -- Colombia

-- -------------------------------------------------------------------------
-- GRUPO L: Inglaterra, Croacia, Ghana, Panamá
-- -------------------------------------------------------------------------
(45, 22, 1, 12, NULL, 'clasificatorio', NULL,  8),  -- Inglaterra
(46, 18, 1, 12, NULL, 'clasificatorio', NULL, 10),  -- Croacia
(47, 32, 1, 12, NULL, 'clasificatorio', NULL, 55),  -- Ghana
(48,  4, 1, 12, NULL, 'clasificatorio', NULL, 78);  -- Panamá


-- Ajustar secuencia
SELECT setval('participacion_participacion_id_seq', (SELECT MAX(participacion_id) FROM participacion));


-- -----------------------------------------------------------------------------
-- FUENTE
-- Fuentes de datos y noticias que usará el pipeline
-- -----------------------------------------------------------------------------

INSERT INTO fuente (fuente_id, codigo, nombre, url_base, idioma, activa)
VALUES

-- Estadísticas y fixtures
( 1, 'football_data',   'Football-Data.co.uk',      'https://www.football-data.co.uk',      'en', TRUE),
( 2, 'fbref',           'FBref',                    'https://fbref.com',                    'en', TRUE),
( 3, 'understat',       'Understat',                'https://understat.com',                'en', TRUE),
( 4, 'sofascore',       'SofaScore',                'https://www.sofascore.com',            'en', TRUE),

-- Noticias en español
( 5, 'marca',           'Marca',                    'https://www.marca.com',                'es', TRUE),
( 6, 'as',              'AS',                        'https://as.com',                       'es', TRUE),
( 7, 'relevo',          'Relevo',                   'https://www.relevo.com',               'es', FALSE), -- medio desaparecido
( 8, 'mundodeportivo',  'Mundo Deportivo',          'https://www.mundodeportivo.com',       'es', TRUE),

-- Noticias en inglés
( 9, 'bbc_sport',       'BBC Sport',                'https://www.bbc.com/sport',            'en', TRUE),
(10, 'guardian',        'The Guardian',             'https://www.theguardian.com/football', 'en', TRUE),
(11, 'espn',            'ESPN FC',                  'https://www.espn.com/soccer',          'en', TRUE),

-- FIFA oficial
(12, 'fifa',            'FIFA Official',            'https://www.fifa.com',                 'en', TRUE),

-- Fuente manual (datos introducidos a mano)
(13, 'manual',          'Entrada manual',           NULL,                                   NULL, TRUE);


-- Ajustar secuencia
SELECT setval('fuente_fuente_id_seq', (SELECT MAX(fuente_id) FROM fuente));
