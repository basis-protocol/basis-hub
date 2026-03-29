-- Witness / CDA domain signals — disclosure cadence anomalies
WITH cadence_signals AS (
    SELECT
        'disclosure_gap_anomaly' as signal_type,
        'witness' as domain,
        asset_symbol || ': latest disclosure gap ' || ROUND(latest_gap_days::numeric, 1) || ' days (avg ' || ROUND(avg_gap_days::numeric, 1) || ')' as title,
        'Disclosure cadence for ' || asset_symbol || ' deviated from historical pattern. ' || extraction_count || ' extractions observed.' as description,
        jsonb_build_array(asset_symbol) as entities,
        CASE WHEN gap_stddev > 0
             THEN ABS(latest_gap_days - avg_gap_days) / gap_stddev
             ELSE 0 END as novelty_score,
        CASE WHEN latest_gap_days > avg_gap_days THEN 'delayed' ELSE 'accelerated' END as direction,
        latest_gap_days as magnitude,
        avg_gap_days as baseline,
        jsonb_build_object(
            'avg_gap_days', avg_gap_days,
            'gap_stddev', gap_stddev,
            'max_gap_days', max_gap_days,
            'extraction_count', extraction_count
        ) as detail
    FROM {{ ref('int_cda_disclosure_cadence') }}
    WHERE extraction_count >= 3
      AND ABS(latest_gap_days - avg_gap_days) > COALESCE(gap_stddev, 1)
),
inactive_issuer_signals AS (
    SELECT
        'issuer_stale' as signal_type,
        'witness' as domain,
        i.asset_symbol || ': ' || i.consecutive_failures || ' consecutive collection failures' as title,
        'Issuer ' || i.issuer_name || ' has ' || i.consecutive_failures || ' consecutive failures. Last success: ' || COALESCE(i.last_successful_collection::text, 'never') as description,
        jsonb_build_array(i.asset_symbol) as entities,
        i.consecutive_failures::float as novelty_score,
        'down' as direction,
        i.consecutive_failures::float as magnitude,
        0 as baseline,
        jsonb_build_object('issuer_name', i.issuer_name, 'last_success', i.last_successful_collection) as detail
    FROM {{ ref('stg_cda_issuers') }} i
    WHERE i.consecutive_failures >= 3
)

SELECT * FROM cadence_signals
UNION ALL SELECT * FROM inactive_issuer_signals
