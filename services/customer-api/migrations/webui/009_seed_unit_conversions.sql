-- 009_seed_unit_conversions.sql
-- Seeds unit conversions used by SellableService when raw datalake values
-- need to be expressed in panel.display_unit. The conversion model is:
--   if operation = 'divide':   to_value = from_value / factor
--   if operation = 'multiply': to_value = from_value * factor
--   if ceil_result:            to_value = ceil(to_value)
--
-- Notable defaults:
--   GHz   -> vCPU      divide 8       ceil   (1 vCPU = 8 GHz, fractional rounds up).
--   Hz    -> GHz       divide 1e9     no-ceil
--   Hz    -> vCPU      divide 8e9     ceil   (Nutanix exposes Hz)
--   bytes -> GB        divide 1.073741824e9  no-ceil
--   MB    -> GB        divide 1024
--   TB    -> GB        multiply 1024
--   Core  -> vCPU      multiply 1     no-ceil (1 Power Core = 1 vCPU equivalent for ratio math)

BEGIN;

INSERT INTO gui_unit_conversion (from_unit, to_unit, factor, operation, ceil_result, notes, updated_by)
VALUES
    ('GHz',   'vCPU',   8.0,             'divide',   TRUE,  '1 vCPU = 8 GHz; fractional CPU rounds up.', 'seed'),
    ('MHz',   'vCPU',   8000.0,          'divide',   TRUE,  '1 vCPU = 8000 MHz; fractional CPU rounds up.', 'seed'),
    ('Hz',    'GHz',    1.0e9,           'divide',   FALSE, '',  'seed'),
    ('Hz',    'vCPU',   8.0e9,           'divide',   TRUE,  'Nutanix cluster exposes Hz; convert direct to vCPU.', 'seed'),
    ('bytes', 'GB',     1073741824.0,    'divide',   FALSE, '1 GiB = 2^30 bytes.',  'seed'),
    ('bytes', 'TB',     1099511627776.0, 'divide',   FALSE, '1 TiB = 2^40 bytes.',  'seed'),
    ('MB',    'GB',     1024.0,          'divide',   FALSE, '',  'seed'),
    ('TB',    'GB',     1024.0,          'multiply', FALSE, '',  'seed'),
    ('GB',    'TB',     1024.0,          'divide',   FALSE, '',  'seed'),
    ('Core',  'vCPU',   1.0,             'multiply', FALSE, 'Treat IBM Power core as a CPU unit for ratio math.', 'seed'),
    ('vCPU',  'Core',   1.0,             'multiply', FALSE, '',  'seed')
ON CONFLICT (from_unit, to_unit) DO UPDATE SET
    factor      = CASE WHEN gui_unit_conversion.updated_by = 'seed' THEN EXCLUDED.factor      ELSE gui_unit_conversion.factor      END,
    operation   = CASE WHEN gui_unit_conversion.updated_by = 'seed' THEN EXCLUDED.operation   ELSE gui_unit_conversion.operation   END,
    ceil_result = CASE WHEN gui_unit_conversion.updated_by = 'seed' THEN EXCLUDED.ceil_result ELSE gui_unit_conversion.ceil_result END,
    notes       = COALESCE(NULLIF(EXCLUDED.notes,''), gui_unit_conversion.notes),
    updated_at  = NOW();

COMMIT;
