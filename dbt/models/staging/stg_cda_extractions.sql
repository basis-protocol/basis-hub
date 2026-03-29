SELECT
    asset_symbol,
    source_url,
    source_type,
    extraction_method,
    extraction_vendor,
    structured_data,
    confidence_score,
    extracted_at
FROM {{ source('basis', 'cda_vendor_extractions') }}
