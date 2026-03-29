-- CQI domain signals — composite quality divergences
WITH dominance_signals AS (
    SELECT
        'cqi_dominance_gap' as signal_type,
        'cqi' as domain,
        stablecoin_id || ' on ' || protocol_slug || ': SII-PSI gap = ' || ROUND(ABS(sii_dominance - psi_dominance)::numeric, 1) as title,
        'CQI score ' || ROUND(cqi_score::numeric, 1) || '. SII=' || ROUND(sii_score::numeric, 1) || ', PSI=' || ROUND(psi_score::numeric, 1) || '. Large divergence between asset and protocol quality.' as description,
        jsonb_build_array(stablecoin_id, protocol_slug) as entities,
        ABS(sii_dominance - psi_dominance) / 10.0 as novelty_score,
        CASE WHEN sii_dominance > psi_dominance THEN 'sii_dominant' ELSE 'psi_dominant' END as direction,
        ABS(sii_dominance - psi_dominance) as magnitude,
        cqi_score as baseline,
        jsonb_build_object('sii_score', sii_score, 'psi_score', psi_score, 'cqi_score', cqi_score, 'sii_dominance', sii_dominance, 'psi_dominance', psi_dominance) as detail
    FROM {{ ref('int_cqi_matrix') }}
    WHERE ABS(sii_dominance - psi_dominance) > 10
),
low_cqi_signals AS (
    SELECT
        'low_composite_quality' as signal_type,
        'cqi' as domain,
        stablecoin_id || ' on ' || protocol_slug || ': CQI = ' || ROUND(cqi_score::numeric, 1) as title,
        'Both asset and protocol scores are low. CQI=' || ROUND(cqi_score::numeric, 1) || '.' as description,
        jsonb_build_array(stablecoin_id, protocol_slug) as entities,
        (70 - cqi_score) / 10.0 as novelty_score,
        'down' as direction,
        cqi_score as magnitude,
        70 as baseline,
        jsonb_build_object('sii_score', sii_score, 'psi_score', psi_score) as detail
    FROM {{ ref('int_cqi_matrix') }}
    WHERE cqi_score < 50
)

SELECT * FROM dominance_signals
UNION ALL SELECT * FROM low_cqi_signals
