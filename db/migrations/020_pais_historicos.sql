-- =============================================================================
-- MIGRACIÓN 020 — Países históricos para historico_resultado
--   `pais` solo contiene las 48 selecciones del Mundial 2026. El histórico
--   de mundiales (1930-2022) incluye otras ~40 selecciones, algunas de
--   países ya desaparecidos (URSS, Yugoslavia, Checoslovaquia, Alemania
--   del Este, Serbia y Montenegro, Indias Orientales Holandesas).
--   Se añaden con confederacion según la federación de la época/sucesora.
-- Ejecutar en Supabase SQL Editor
-- =============================================================================

INSERT INTO pais (nombre, nombre_en, codigo_fifa, codigo_iso2, confederacion) VALUES
    ('Angola',                 'Angola',                 'AGO', 'AO', 'CAF'),
    ('Bolivia',                'Bolivia',                'BOL', 'BO', 'CONMEBOL'),
    ('Bulgaria',               'Bulgaria',               'BUL', 'BG', 'UEFA'),
    ('Camerún',                'Cameroon',               'CMR', 'CM', 'CAF'),
    ('Chile',                  'Chile',                  'CHI', 'CL', 'CONMEBOL'),
    ('China',                  'China',                  'CHN', 'CN', 'AFC'),
    ('Costa Rica',             'Costa Rica',             'CRC', 'CR', 'CONCACAF'),
    ('Cuba',                   'Cuba',                   'CUB', 'CU', 'CONCACAF'),
    ('Checoslovaquia',         'Czechoslovakia',         'TCH', NULL, 'UEFA'),
    ('Dinamarca',              'Denmark',                'DEN', 'DK', 'UEFA'),
    ('Indias Orientales Neerlandesas', 'Dutch East Indies', 'IDN', NULL, 'AFC'),
    ('Alemania Oriental',      'East Germany',           'GDR', NULL, 'UEFA'),
    ('El Salvador',            'El Salvador',            'SLV', 'SV', 'CONCACAF'),
    ('Grecia',                 'Greece',                 'GRE', 'GR', 'UEFA'),
    ('Honduras',               'Honduras',               'HON', 'HN', 'CONCACAF'),
    ('Hungría',                'Hungary',                'HUN', 'HU', 'UEFA'),
    ('Islandia',               'Iceland',                'ISL', 'IS', 'UEFA'),
    ('Israel',                 'Israel',                 'ISR', 'IL', 'UEFA'),
    ('Italia',                 'Italy',                  'ITA', 'IT', 'UEFA'),
    ('Jamaica',                'Jamaica',                'JAM', 'JM', 'CONCACAF'),
    ('Kuwait',                 'Kuwait',                 'KUW', 'KW', 'AFC'),
    ('Nigeria',                'Nigeria',                'NGA', 'NG', 'CAF'),
    ('Corea del Norte',        'North Korea',            'PRK', 'KP', 'AFC'),
    ('Irlanda del Norte',      'Northern Ireland',       'NIR', 'GB-NIR', 'UEFA'),
    ('Perú',                   'Peru',                   'PER', 'PE', 'CONMEBOL'),
    ('Polonia',                'Poland',                 'POL', 'PL', 'UEFA'),
    ('República de Irlanda',   'Republic of Ireland',    'IRL', 'IE', 'UEFA'),
    ('Rumanía',                'Romania',                'ROU', 'RO', 'UEFA'),
    ('Rusia',                  'Russia',                 'RUS', 'RU', 'UEFA'),
    ('Serbia',                 'Serbia',                 'SRB', 'RS', 'UEFA'),
    ('Serbia y Montenegro',    'Serbia and Montenegro',  'SCG', NULL, 'UEFA'),
    ('Eslovaquia',             'Slovakia',               'SVK', 'SK', 'UEFA'),
    ('Eslovenia',              'Slovenia',               'SVN', 'SI', 'UEFA'),
    ('Unión Soviética',        'Soviet Union',           'URS', NULL, 'UEFA'),
    ('Togo',                   'Togo',                   'TOG', 'TG', 'CAF'),
    ('Trinidad y Tobago',      'Trinidad and Tobago',    'TRI', 'TT', 'CONCACAF'),
    ('Ucrania',                'Ukraine',                'UKR', 'UA', 'UEFA'),
    ('Emiratos Árabes Unidos', 'United Arab Emirates',   'UAE', 'AE', 'AFC'),
    ('Gales',                  'Wales',                  'WAL', 'GB-WLS', 'UEFA'),
    ('Yugoslavia',             'Yugoslavia',             'YUG', NULL, 'UEFA')
ON CONFLICT (codigo_fifa) DO NOTHING;
