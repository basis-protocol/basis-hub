SELECT
    asset_symbol,
    issuer_name,
    last_successful_collection,
    consecutive_failures,
    is_active,
    updated_at
FROM {{ source('basis', 'cda_issuer_registry') }}
WHERE is_active = TRUE
