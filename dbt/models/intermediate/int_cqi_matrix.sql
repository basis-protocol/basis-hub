-- CQI = sqrt(SII x PSI) for all scored pairs
WITH latest_sii AS (
    SELECT stablecoin_id, overall_score as sii_score
    FROM {{ source('basis', 'scores') }}
    WHERE overall_score IS NOT NULL
),
latest_psi AS (
    SELECT DISTINCT ON (protocol_slug)
        protocol_slug, overall_score as psi_score
    FROM {{ source('basis', 'psi_scores') }}
    WHERE overall_score IS NOT NULL
    ORDER BY protocol_slug, computed_at DESC
)
SELECT
    s.stablecoin_id,
    p.protocol_slug,
    s.sii_score,
    p.psi_score,
    SQRT(s.sii_score * p.psi_score) as cqi_score,
    s.sii_score - SQRT(s.sii_score * p.psi_score) as sii_dominance,
    p.psi_score - SQRT(s.sii_score * p.psi_score) as psi_dominance
FROM latest_sii s
CROSS JOIN latest_psi p
