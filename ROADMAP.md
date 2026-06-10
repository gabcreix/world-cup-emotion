# Roadmap

## Pendientes / mejoras futuras

- **Texto completo de noticias (`noticia.texto_completo`)**: actualmente
  el pipeline `news_rss` solo persiste título + resumen del RSS. Para
  mejorar la cobertura de `mencion` (sobre todo de DTs, que rara vez
  aparecen en el resumen) y dar más contexto a `embedding`, habría que
  añadir un scraping del cuerpo completo de cada artículo (ej. con
  `trafilatura`/`readability`), por fuente o genérico.

- **Histórico de mundiales**: `historico_edicion`, `historico_resultado`,
  `historico_record`.

- **Eventos/stats de partido**: `evento_partido`, `stats_equipo`,
  `stats_jugador` — pausado hasta que se jueguen los primeros partidos
  del Mundial 2026 y haya `match_report_url` en
  `bronze.fbref_fixture_raw`.

- **Narrativas**: agrupación de noticias similares vía `embedding`
  (clustering) hacia la tabla `narrativa`.

- **Interfaz de búsqueda**: si el uso de `embeddings.search` crece,
  evaluar una interfaz sencilla (HTML/Streamlit) para curación editorial,
  en vez de CLI.
