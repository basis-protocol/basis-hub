-- Days between extractions per issuer
WITH extraction_gaps AS (
    SELECT
        asset_symbol,
        extracted_at,
        LAG(extracted_at) OVER (PARTITION BY asset_symbol ORDER BY extracted_at) as prev_extraction,
        EXTRACT(EPOCH FROM (extracted_at - LAG(extracted_at) OVER (PARTITION BY asset_symbol ORDER BY extracted_at))) / 86400.0 as gap_days
    FROM {{ ref('stg_cda_extractions') }}
)
SELECT
    asset_symbol,
    AVG(gap_days) as avg_gap_days,
    STDDEV_SAMP(gap_days) as gap_stddev,
    MAX(gap_days) as max_gap_days,
    MIN(gap_days) as min_gap_days,
    COUNT(*) as extraction_count,
    (SELECT gap_days FROM extraction_gaps eg
     WHERE eg.asset_symbol = extraction_gaps.asset_symbol
     ORDER BY extracted_at DESC LIMIT 1) as latest_gap_days
FROM extraction_gaps
WHERE gap_days IS NOT NULL
GROUP BY asset_symbol
