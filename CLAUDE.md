# World Cup Emotion — Guía del proyecto

## Stack
- Python 3.11+, psycopg3, python-dotenv
- Base de datos: Supabase (PostgreSQL + pgvector)
- Distribución: Telegram, Substack/Beehiiv, X, Instagram

## Estructura
```
db/          → SQL de esquema y seeds
src/world_cup/ → código Python del proyecto
```

## Conexión a BD
Requiere `.env` con `DATABASE_URL` (ver `.env.example`).
Usar siempre `db.get_conn()` o `db.get_cursor()` como context managers.

## Convenciones BD
- PKs: BIGSERIAL
- Auditoría: creado_en / actualizado_en (DEFAULT NOW(), no gestionar manualmente)
- Nombres normalizados via tabla `alias_entidad` (polimórfica)
- Tras inserts con IDs explícitos: `SELECT setval('tabla_col_seq', (SELECT MAX(col) FROM tabla))`

## Desarrollo atómico
Construir por pasos: un pipeline, una fuente, una tabla a la vez.
