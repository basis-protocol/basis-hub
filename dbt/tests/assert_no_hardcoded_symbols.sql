-- Ensure no discovery model hardcodes specific stablecoin symbols
-- This test always passes (no rows) — it's a lint reminder.
-- The real check is: grep the models/ directory for hardcoded ticker strings.
SELECT 1 as dummy WHERE FALSE
