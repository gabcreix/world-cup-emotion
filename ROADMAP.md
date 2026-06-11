# World Cup Emotion — Planning y estado actual

## Contexto
El torneo **arranca hoy, 11 de junio de 2026**. El pipeline de stats de partido
se desarrollará esta noche tras el primer encuentro, en cuanto FBref publique
el match report (1–3h después del pitido final).

---

## Estado actual de pipelines

### ✅ Implementados y funcionando
| Pipeline | Descripción |
|---|---|
| `fbref_fixtures` | Fixtures del torneo (bronze → silver → gold → `partido`) |
| `fbref_dts` | Entrenadores (bronze → silver → gold → `dt` + `participacion.dt_id`) |
| `fbref_squads` | Plantillas por selección (bronze → silver → gold) |
| `news_rss` | Ingesta de noticias vía RSS + scraping NewsNow (bronze → silver → gold → `noticia`) |
| `embeddings` | Vectorización de noticias con OpenAI text-embedding-3-small → `embedding` |
| `menciones` | Detección de entidades (seleccion, dt) en noticias → `mencion` |

### ⏳ Pendientes — por orden de prioridad

---

## Prioridad 1 — HOY (tras el primer partido)

### Pipeline de stats de partido
- **Tablas destino**: `evento_partido`, `stats_equipo`, `stats_jugador`
- **Fuente**: FBref match reports (el `match_report_url` ya está en `bronze.fbref_fixture_raw`)
- **Desbloqueado**: en cuanto FBref publique el report del primer partido (1–3h post-pitido)
- **Stats a capturar** (sin xG — no disponible en FBref actualmente):
  - `stats_equipo`: posesión, tiros totales, tiros a puerta, tiros bloqueados, pases totales,
    pases completados, pases clave, corners, fueras de juego, faltas cometidas, despejes
  - `stats_jugador`: minutos jugados, titular, goles, asistencias, tiros, tiros a puerta,
    pases completados, pases intentados, pases clave, regates exitosos, regates intentados,
    conducciones, presiones, presiones exitosas, recuperaciones, pérdidas de balón,
    duelos ganados, duelos totales, duelos aéreos ganados, intercepciones, despejes,
    entradas exitosas, tarjetas amarillas, tarjetas rojas, nota
  - `stats_extra_json` (JSONB, solo porteros): paradas, goles_encajados, paradas_penalti,
    salidas, despejes_puño, pases_largos_completados, pases_largos_intentados
  - `evento_partido`: goles, tarjetas, sustituciones, minuto, jugador, jugador relacionado

---

## Prioridad 2 — Esta semana

### Texto completo de noticias
- **Problema**: `news_rss` solo persiste título + resumen del RSS
- **Impacto**: el pipeline de menciones pierde menciones de jugadores y entidades
  secundarias que solo aparecen en el cuerpo del artículo
- **Solución**: añadir scraping del cuerpo completo con `trafilatura` (añadir a
  `pyproject.toml`) después de la ingesta RSS
- **Campo destino**: `noticia.texto_completo`
- **Nota**: aplicar por fuente o con extractor genérico; respetar robots.txt

### Menciones de jugadores
- **Problema**: `ENTIDAD_TIPOS` en `menciones/run.py` solo incluye `seleccion` y `dt`
- **Requisito previo**: que `jugador` y `convocatoria` estén poblados (fbref_squads gold)
- **Solución**: añadir `'jugador'` a `ENTIDAD_TIPOS` — el pipeline ya soporta la extensión
- **Impacto**: las menciones de Mbappé, Yamal, Vinicius, etc. empezarán a registrarse

### Histórico de mundiales
- **Tablas destino**: `historico_edicion`, `historico_resultado`, `historico_record`
- **Fuente sugerida**: dataset Kaggle de resultados históricos FIFA (1930–2022),
  complementado con Wikipedia API para récords y datos de edición
- **Valor**: convierte un stat del torneo actual en narrativa con contexto de 22 mundiales

---

## Prioridad 3 — Durante la fase de grupos

### Sentimiento en menciones
- **Campo destino**: `mencion.sentimiento` (actualmente siempre NULL)
- **Solución**: tras la detección por regex, llamada al LLM con el campo `contexto`
  para clasificar como `positivo / negativo / neutro`
- **Modelo sugerido**: gpt-4o-mini (ya integrado en el proyecto para reranking)

### Scheduler de pipelines
- **Problema**: todos los pipelines corren manualmente
- **Solución**: script `run_scheduler.py` con la librería `schedule` o Task Scheduler
  de Windows, con esta cadencia:
  - Cada 2h: `news_rss → embeddings → menciones`
  - Cada día (madrugada): `fbref_fixtures` (actualización de resultados)
  - Tras cada partido (trigger manual o cron post-partido): stats de partido

### Deduplicación de noticias
- **Problema**: BBC y Guardian pueden cubrir el mismo partido generando noticias
  duplicadas que contaminan menciones y embeddings
- **Solución**: hash del título normalizado (minúsculas, sin puntuación) como
  constraint o check antes de insertar en `noticia`

---

## Prioridad 4 — Segunda fase del torneo en adelante

### Pipeline de publicación — Telegram
- **Canal**: bot de Telegram existente (stack ya definido)
- **Contenido inicial**: mensaje post-partido con resultado, stats clave y
  una narrativa destacada
- **Trigger**: manual o automático cuando `partido.estado = 'finalizado'`
- **Formato sugerido**:
  ```
  🏆 [Local] X – Y [Visitante] | Grupo A
  📊 Posesión: 58% – 42%
  🎯 Tiros a puerta: 5 – 2
  💡 [Narrativa del partido]
  ```

### Pipeline de publicación — Newsletter
- **Canal**: Substack / Beehiiv
- **Cadencia**: diaria durante el torneo
- **Contenido**: resumen de partidos del día + narrativa de fondo + dato histórico

### Pipeline de publicación — X
- **Formato**: hilo con datos del partido + narrativa diferenciadora
- **Requiere**: mayor curaduría editorial que Telegram

### Dashboard editorial (Streamlit)
- **Propósito**: revisar narrativas candidatas en `narrativa`, asignar
  `score_editorial` y marcar como `publicada` sin tocar SQL
- **Prioridad**: cuando la tabla `narrativa` empiece a llenarse con datos reales

### Motor de narrativas automáticas
Tres capas sobre la infraestructura existente:
1. **Queries analíticas precompiladas**: rachas, invictos, comparativas de grupos,
   rendimiento por confederación → insertan en `narrativa` automáticamente
2. **Cruce con histórico**: contextualiza stats actuales con los 22 mundiales anteriores
   (requiere Prioridad 2 — histórico)
3. **Clustering de embeddings**: agrupa noticias similares para detectar narrativas
   emergentes (ej: si 8 artículos mencionan la misma lesión en 6h → narrativa)

---

## Notas técnicas importantes

### xG y stats avanzadas
- **No disponibles en FBref** actualmente para el Mundial 2026
- Los campos `xg` y `xag` en `stats_equipo` y `stats_jugador` quedan vacíos por ahora
- Alternativa futura si se necesita: Sofascore API no oficial (tiene xG en tiempo real)

### Fuentes RSS activas confirmadas
| Fuente | URL |
|---|---|
| BBC Sport | `https://feeds.bbci.co.uk/sport/football/rss.xml` |
| The Guardian | `https://www.theguardian.com/football/worldcup/rss` |
| Marca | `https://e00-marca.uecdn.es/rss/futbol/seleccion.xml` |
| Reddit r/worldcup | `https://www.reddit.com/r/worldcup.rss` |
| Reddit r/soccer | `https://www.reddit.com/r/soccer.rss` |
| Reddit r/football | `https://www.reddit.com/r/football.rss` |

### Fuentes sin RSS (scraping requerido para texto completo)
AS, Goal, FIFA, ESPN, TyC Sports, Infobae, Olé

### Stack técnico
- Python 3.11+, psycopg3, python-dotenv
- Supabase (PostgreSQL + pgvector)
- OpenAI API (text-embedding-3-small para embeddings, gpt-4o-mini para reranking)
- undetected-chromedriver para FBref (Cloudflare)
- feedparser para RSS
- trafilatura (pendiente de añadir) para texto completo
