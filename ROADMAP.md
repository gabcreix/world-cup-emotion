# World Cup Emotion — Planning completo

## Fecha de referencia
Torneo en curso desde el 11 de junio de 2026.
Este documento es la fuente de verdad para todo el trabajo pendiente.
Actualizar cuando se complete cada ítem.

---

## Arquitectura del proyecto — referencia obligatoria

Antes de implementar cualquier ítem, respetar estos patrones:

### Patrón Bronze → Gold (pipelines de datos)
```
bronze.py   → descarga/scraping de fuente externa, persiste raw en bronze.*_raw
silver.py   → normalización y validación (cuando aplica), persiste en silver.*
gold.py     → upsert en tablas públicas (public.*), resolución de FKs
run.py      → orquestador que llama bronze → silver → gold en orden
```
Para datos históricos estáticos (como historico_mundiales) se puede omitir silver
y usar transform.py como módulo de funciones puras sin dependencia de BD.

### Conexión a BD
Siempre usar `db.get_conn()` como context manager:
```python
from world_cup import db

with db.get_conn() as conn:
    with conn.cursor() as cur:
        cur.execute(...)
    conn.commit()
```

### Migraciones
Cada cambio de esquema va en `db/migrations/NNN_descripcion.sql` con el número
siguiente al último existente. Ejecutar en Supabase SQL Editor antes de correr
el pipeline que lo necesite.

### Convenciones de BD
- PKs: BIGSERIAL
- Auditoría: `creado_en` / `actualizado_en` con `DEFAULT NOW()` — no gestionar manualmente
- Nombres normalizados vía `alias_entidad` (tabla polimórfica, sin FK constraint)
- Secuencias tras inserts con IDs explícitos:
  `SELECT setval('tabla_columna_seq', (SELECT MAX(columna) FROM tabla))`
- Nombres de secuencias: patrón Supabase `tabla_columna_seq`

### Ubicación de archivos
```
db/migrations/          → cambios de esquema (numerados)
src/world_cup/
    db.py               → conexión BD
    pipelines/          → un directorio por pipeline
        nombre/
            bronze.py
            silver.py   (opcional)
            gold.py
            run.py
    reports/            → generación de HTML u otros outputs
```

### Dependencias disponibles
psycopg[binary], python-dotenv, requests, beautifulsoup4, lxml,
undetected-chromedriver, selenium, feedparser, openai, trafilatura

Añadir nuevas dependencias en `pyproject.toml` y documentarlo.

---

## Estado actual — pipelines implementados

| Pipeline | Tablas destino | Estado |
|---|---|---|
| `fbref_fixtures` | `partido` | ✅ |
| `fbref_dts` | `dt`, `participacion.dt_id` | ✅ |
| `fbref_squads` | `jugador`, `convocatoria` | ✅ |
| `news_rss` | `noticia` | ✅ |
| `news_rss/fulltext` | `noticia.texto_completo` | ✅ |
| `embeddings` | `embedding` | ✅ |
| `menciones` | `mencion` (seleccion, dt, jugador) | ✅ |
| `menciones/sentimiento` | `mencion.sentimiento` | ✅ |
| `historico_mundiales` | `historico_edicion`, `historico_resultado`, `historico_record` | ✅ |

---

## PRIORIDAD 1 — Pipeline de stats de partido

**Contexto**: FBref publica el match report 1–3h después del pitido final.
La URL ya está en `bronze.fbref_fixture_raw.match_report_url`.
Desarrollar tras el primer partido (11 jun 2026).

### Tablas destino
- `evento_partido` — goles, tarjetas, sustituciones
- `stats_equipo` — stats agregadas por equipo y partido
- `stats_jugador` — stats individuales por jugador y partido

### Ubicación
```
src/world_cup/pipelines/fbref_match_stats/
    __init__.py
    bronze.py
    silver.py
    gold.py
    run.py
```

### bronze.py
- Leer partidos finalizados con `match_report_url IS NOT NULL` y sin stats aún:
  ```sql
  SELECT p.partido_id, f.match_report_url
  FROM partido p
  JOIN bronze.fbref_fixture_raw f ON f.match_id = p.partido_id  -- ajustar JOIN según esquema real
  WHERE p.estado = 'finalizado'
  AND NOT EXISTS (SELECT 1 FROM stats_equipo se WHERE se.partido_id = p.partido_id)
  ```
- Descargar HTML del match report con `undetected_chromedriver` (mismo patrón que `fbref_squads/bronze.py`)
- Persistir HTML crudo en nueva tabla `bronze.fbref_match_report_raw`

### Migración necesaria
```sql
-- NNN_bronze_match_reports.sql
CREATE TABLE bronze.fbref_match_report_raw (
    id              BIGSERIAL PRIMARY KEY,
    partido_id      BIGINT NOT NULL,
    match_report_url VARCHAR(500),
    html_raw        TEXT NOT NULL,
    scraped_en      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX ON bronze.fbref_match_report_raw(partido_id);
```

### silver.py
Parsear HTML con BeautifulSoup y extraer:

**Eventos de partido** (`evento_partido`):
- Goles: minuto, jugador, equipo, tipo (gol / gol_penalti / gol_propia)
- Tarjetas: minuto, jugador, equipo, tipo (amarilla / roja / doble_amarilla)
- Sustituciones: minuto, jugador_sale, jugador_entra, equipo

**Stats por equipo** (`stats_equipo`):
- posesion, tiros_totales, tiros_a_puerta, tiros_bloqueados
- pases_totales, pases_completados, pases_clave
- corners, fueras_de_juego, faltas_cometidas, despejes
- NOTA: xG no disponible en FBref para el Mundial 2026

**Stats por jugador** (`stats_jugador`):
- minutos_jugados, titular
- goles, asistencias, tiros, tiros_a_puerta
- pases_completados, pases_intentados, pases_clave
- regates_exitosos, regates_intentados, conducciones
- presiones, presiones_exitosas, recuperaciones, perdidas_balon
- duelos_ganados, duelos_totales, duelos_aereos_ganados
- intercepciones, despejes, entradas_exitosas
- tarjetas_amarillas, tarjetas_rojas, nota
- `stats_extra_json` JSONB solo para porteros:
  `{"paradas": N, "goles_encajados": N, "paradas_penalti": N, "salidas": N}`

### gold.py
Resolución de FKs:
- `jugador_id`: buscar en `alias_entidad` donde `entidad_tipo = 'jugador'` con el nombre de FBref
- `participacion_id`: desde `partido` + `seleccion.codigo_fifa`
- Upsert idempotente en `evento_partido`, `stats_equipo` (UNIQUE partido_id + participacion_id),
  `stats_jugador` (UNIQUE partido_id + jugador_id)

---

## PRIORIDAD 2 — Deduplicación de noticias

**Problema**: varias fuentes RSS pueden cubrir el mismo evento generando
noticias duplicadas que contaminan menciones y embeddings.

### Migración necesaria
```sql
-- NNN_noticia_titulo_hash.sql
ALTER TABLE noticia ADD COLUMN titulo_hash CHAR(64);
CREATE UNIQUE INDEX uq_noticia_titulo_hash ON noticia(titulo_hash)
    WHERE titulo_hash IS NOT NULL;
```

### Implementación
En `news_rss/gold.py`, antes de insertar en `noticia`:
```python
import hashlib, re

def _normalizar_titulo(titulo: str) -> str:
    t = titulo.lower().strip()
    t = re.sub(r'[^a-záéíóúüñ0-9\s]', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t

def _hash_titulo(titulo: str) -> str:
    return hashlib.sha256(_normalizar_titulo(titulo).encode()).hexdigest()
```
Calcular hash, intentar INSERT, capturar `UniqueViolation` y saltar silenciosamente.

---

## PRIORIDAD 3 — Scheduler de pipelines

**Objetivo**: automatizar la cadena de pipelines para no ejecutar manualmente.

### Ubicación
```
src/world_cup/scheduler.py
```

### Dependencia a añadir en pyproject.toml
```
"schedule>=1.2",
```

### Cadencia
```python
# Cada 2 horas: noticias completas
schedule.every(2).hours.do(run_news_chain)
# news_rss → fulltext → embeddings → menciones → sentimiento

# Una vez al día a las 6:00: actualizar fixtures
schedule.every().day.at("06:00").do(run_fixtures)

# Una vez al día a las 23:30: informe email si hubo partidos
schedule.every().day.at("23:30").do(run_email_diario)
```

### Función post-partido (ejecución manual o trigger)
```python
def run_post_partido(partido_id: int):
    """Ejecutar tras cada partido finalizado."""
    fbref_match_stats.run(partido_id)
    # actualiza stats → genera narrativas analíticas del partido
```

### Notas
- Ejecutar `scheduler.py` como proceso en segundo plano en Windows:
  `pythonw -m world_cup.scheduler` o via Task Scheduler de Windows
- Logging básico a `data/logs/scheduler_YYYY-MM-DD.log`
- Si un pipeline falla, loggear el error y continuar con el siguiente

---

## PRIORIDAD 4 — Motor de narrativas automáticas

**Objetivo**: poblar la tabla `narrativa` automáticamente con datos
interesantes del torneo, listos para consumo editorial.

### Ubicación
```
src/world_cup/pipelines/narrativas/
    __init__.py
    analiticas.py   → queries SQL predefinidas
    historico.py    → cruce con historico_resultado / historico_record
    clustering.py   → agrupación de embeddings similares
    run.py
```

### Tabla destino
`narrativa` — campos clave:
- `titulo`: la narrativa en una frase
- `tipo`: 'estadistica' | 'racha' | 'comparativa' | 'hito' | 'curiosidad'
- `descripcion`: desarrollo completo
- `score_relevancia`: float 0–1 asignado por el pipeline
- `score_editorial`: float 0–1, asignado manualmente por el usuario
- `publicada`: boolean, marcar cuando se use en contenido
- `entidades_json`: `[{"tipo": "seleccion", "id": 12}, ...]`
- `fuente_datos`: 'historico' | 'torneo_actual' | 'mixta'

### analiticas.py — queries predefinidas (ejemplos)
Estas queries corren tras cada jornada y generan filas en `narrativa`:

```sql
-- Selecciones invictas en el torneo actual
SELECT p.nombre, COUNT(*) as partidos_sin_perder ...
FROM partido pa JOIN participacion ...
WHERE pa.estado = 'finalizado' AND (goles_local > goles_visitante OR ...)

-- Goleadores del torneo ordenados
SELECT j.nombre_completo, COUNT(*) as goles
FROM evento_partido e JOIN jugador j ON j.jugador_id = e.jugador_id
WHERE e.tipo IN ('gol', 'gol_penalti') GROUP BY j.jugador_id ORDER BY goles DESC

-- Partido con más goles del torneo hasta ahora
-- Equipo con mejor/peor posesión media
-- Grupo con más goles por partido
```

### historico.py — cruce con histórico
Comparar stats actuales con `historico_resultado` y `historico_record`:

```python
# Ejemplo: ¿Es esta la mayor racha invicta de España en Mundiales?
# Ejemplo: ¿Cuántas veces se han enfrentado estos dos equipos en Mundiales?
# Ejemplo: ¿Francia ha marcado en todos los partidos de la fase de grupos?
```

Usar LLM (gpt-4o-mini) para redactar la narrativa una vez identificado el dato:
```python
prompt = f"""
Eres un periodista deportivo. Redacta una narrativa breve (2-3 frases) en español
sobre este dato del Mundial 2026:
{dato_estructurado}
Tono: analítico, con dato concreto. Sin clichés.
"""
```

### clustering.py — narrativas emergentes de noticias
Agrupar embeddings similares para detectar temas recurrentes:
```python
# Cargar embeddings de las últimas 24h
# Calcular similitud coseno entre pares (pgvector: <=> operador)
# Si un grupo de N >= 5 noticias tiene similitud > 0.85 → narrativa emergente
# Usar LLM para resumir el tema del cluster en una frase
```

Query de similitud en pgvector:
```sql
SELECT n1.noticia_id, n2.noticia_id, e1.vector <=> e2.vector AS distancia
FROM embedding e1
JOIN embedding e2 ON e1.noticia_id < e2.noticia_id
JOIN noticia n1 ON n1.noticia_id = e1.noticia_id
JOIN noticia n2 ON n2.noticia_id = e2.noticia_id
WHERE e1.vector <=> e2.vector < 0.15  -- muy similares
AND n1.fecha_ingestion > NOW() - INTERVAL '24 hours'
```

### Idempotencia
Antes de insertar en `narrativa`, verificar que no existe ya una narrativa
con el mismo `titulo` en las últimas 48h para evitar duplicados.

---

## PRIORIDAD 5 — Informe diario por email

### Ubicación
```
src/world_cup/reports/email_diario.py
```

### Ejecución
```
python -m world_cup.reports.email_diario
python -m world_cup.reports.email_diario --fecha 2026-06-11
```

### Variables de entorno (.env)
```
EMAIL_SENDER=tu@gmail.com
EMAIL_PASSWORD=xxxx xxxx xxxx xxxx   # Gmail app password
EMAIL_RECIPIENT=tu@gmail.com
```

### Dependencias
Solo stdlib: `smtplib`, `email.mime`. Sin dependencias nuevas.

### Idempotencia
Guardar HTML en `data/emails/YYYY-MM-DD.html` antes de enviar.
Si el fichero existe, no volver a enviar.

### Lógica de ejecución
Solo enviar si hay partidos con `estado = 'finalizado'` en la fecha del informe.

### Secciones del informe (en orden)

**1. Cabecera**
Título con fecha larga en español. Cuántos partidos, en qué fase.

**2. Resultados del día**
Partidos finalizados hoy ordenados por hora.
Por partido: emoji de bandera + nombre + goles + nombre + emoji bandera.
Indicar prórroga/penaltis si aplica. Estadio y ciudad.
Fuente: `partido` + `participacion` + `seleccion` + `pais` + `estadio` + `fase` + `grupo`

**3. Tabla de grupos actualizada** (solo fase GRP)
Solo los grupos con partidos hoy.
Columnas: Pos | Selección | PJ | G | E | P | GF | GC | DG | Pts
Calcular desde `partido` + `evento_partido` o `partido.goles_*`.

**4. Datos relevantes del día** (LLM, omitir si stats vacías)
Goleadores, portero destacado, stat curiosa del día.
Fuente: `stats_equipo` + `stats_jugador` + `evento_partido`

**5. Hecho histórico del día** (LLM, omitir si no hay dato relevante)
Una sola frase conectando resultado de hoy con `historico_resultado`.
Fuente: `historico_resultado` + `historico_record`

**6. Noticias destacadas** (LLM)
Párrafo introductorio articulado + lista de 8-10 noticias con título enlazado.
Filtrar por `mencion` de entidades que jugaron hoy + `fecha_ingestion::date = hoy`.
Fuente: `noticia` + `mencion` + `fuente`

**7. Sentimiento de prensa**
Ranking de selecciones que jugaron hoy con su tono en prensa.
🟢 positivo / 🔴 negativo / ⚪ neutro + número de menciones.
Fuente: `mencion` + `mencion.sentimiento` (últimas 24h)

**8. Lo más destacado fuera del campo** (LLM)
3-4 noticias no relacionadas directamente con los partidos de hoy.
Lesiones, polémicas, historias humanas de selecciones que juegan pronto.

**9. Crónica del día** (LLM)
150-200 palabras. Tono periodístico en español.
Qué fue lo más importante, qué sorprendió, qué historia define la jornada.

**10. Preview del día siguiente**
Partidos de mañana con hora (UTC+2), equipos, fase, estadio.
Una línea de contexto: qué se juegan los equipos.
Fuente: `partido` + `participacion` + `seleccion` + `pais`

**11. Estadísticas acumuladas del torneo** (omitir si stats vacías)
Goles totales, media por partido, tarjetas, penaltis, autogoles.
Fuente: `evento_partido` + `stats_equipo`

### Prompt base para todas las secciones LLM
```python
SYSTEM_PROMPT = """
Eres un periodista deportivo especializado en fútbol internacional,
escribiendo para una audiencia hispanohablante global.
Tono: analítico pero accesible, con datos concretos, en español.
Evita clichés. Sé preciso y directo.
"""
```
Modelo: `gpt-4o-mini`. Una llamada por sección (5 llamadas máximo por informe).
Pasar datos siempre como JSON estructurado en el prompt.
Si una sección no tiene datos suficientes, no llamar al LLM — omitir la sección.

### Diseño HTML del email
- Ancho máximo 600px (estándar email)
- Fuente system-ui / sans-serif
- Sin imágenes externas
- Emojis de banderas para selecciones
- Colores: fondo blanco, acentos azul (grupos), naranja (eliminatorias)
- Links con `target="_blank"`

---

## PRIORIDAD 6 — Pipeline de publicación: Telegram

**Objetivo**: enviar mensaje post-partido al canal de Telegram
con resultado, stats clave y narrativa del partido.

### Ubicación
```
src/world_cup/pipelines/telegram/
    __init__.py
    sender.py   → función base de envío via Bot API
    post_partido.py → mensaje post-partido
    run.py
```

### Variables de entorno (.env)
```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHANNEL_ID=@mi_canal  # o el chat_id numérico
```

### Dependencia a añadir
```
"httpx>=0.27",   # o usar requests que ya está disponible
```

### Formato del mensaje post-partido
```
🏆 [Fase] | Grupo [X]

🇪🇸 España 2 – 1 Francia 🇫🇷
📍 MetLife Stadium, Nueva York

⏱ Goles: Yamal 23', Morata 67' | Mbappé 45+2'

📊 Posesión: 54% – 46%
🎯 Tiros a puerta: 4 – 3

💡 [Narrativa del partido — 1 frase generada por LLM]

#Mundial2026 #ESP #FRA
```

### Trigger
Ejecución manual o desde el scheduler tras confirmar `partido.estado = 'finalizado'`.

### Idempotencia
Añadir tabla o flag para no enviar dos veces el mismo partido:
```sql
-- NNN_telegram_enviado.sql
CREATE TABLE telegram_enviado (
    partido_id   BIGINT PRIMARY KEY REFERENCES partido(partido_id),
    enviado_en   TIMESTAMP NOT NULL DEFAULT NOW(),
    tipo         VARCHAR(30) NOT NULL  -- 'post_partido' | 'preview' | etc.
);
```

---

## PRIORIDAD 7 — Pipeline de publicación: Newsletter

**Objetivo**: publicación en Substack o Beehiiv con el resumen diario.

### Nota de implementación
Beehiiv tiene API REST documentada. Substack no tiene API pública oficial.
**Recomendación**: usar Beehiiv si es posible; si no, generar el HTML del email
diario (ya implementado en Prioridad 5) y publicarlo manualmente.

Posponer implementación automática hasta confirmar la plataforma y
obtener API key.

### Variables de entorno cuando esté listo
```
BEEHIIV_API_KEY=...
BEEHIIV_PUBLICATION_ID=...
```

---

## PRIORIDAD 8 — Dashboard editorial (Streamlit)

**Objetivo**: interfaz web local para revisar narrativas candidatas,
asignar `score_editorial` y marcar como `publicada`.

### Ubicación
```
src/world_cup/dashboard/
    app.py
```

### Dependencia a añadir
```
"streamlit>=1.35",
```

### Ejecución
```
streamlit run src/world_cup/dashboard/app.py
```

### Funcionalidad mínima
- Tabla de narrativas ordenadas por `score_relevancia DESC` donde `publicada = FALSE`
- Columnas: título, tipo, fuente_datos, score_relevancia, score_editorial
- Por cada narrativa: slider para `score_editorial` (0.0–1.0) + botón "Publicada"
- Filtros: por tipo, por fuente_datos, por rango de fechas
- Vista de noticias recientes con sus menciones (replicar `reports/news.py` en UI interactiva)

---

## Orden de implementación recomendado

```
1. fbref_match_stats          (esta noche — primer partido)
2. deduplicacion_noticias     (mejora inmediata del pipeline existente)
3. email_diario               (valor editorial desde el día 1)
4. narrativas/analiticas      (queries SQL, sin LLM, rápido de implementar)
5. telegram/post_partido      (distribución básica)
6. scheduler                  (automatización)
7. narrativas/historico       (requiere historico bien poblado)
8. narrativas/clustering      (requiere suficientes embeddings acumulados)
9. dashboard                  (cuando narrativa tenga datos reales)
10. newsletter                (último, requiere decisión de plataforma)
```

---

## Cadena diaria completa (objetivo final)

```
06:00  fbref_fixtures          → actualizar resultados de la noche
06:30  fbref_match_stats       → stats de partidos finalizados
07:00  news_rss                → noticias nuevas
07:15  fulltext                → texto completo
07:30  embeddings              → vectorizar noticias nuevas
07:45  menciones               → detectar entidades
08:00  sentimiento             → clasificar tono
08:15  narrativas              → generar narrativas automáticas
08:30  email_diario            → informe de la jornada anterior

Cada 2h (durante el día):
       news_rss → fulltext → embeddings → menciones → sentimiento

Post-partido (manual o trigger):
       fbref_match_stats → telegram/post_partido
```
