-- Attestation domain signals — input vector stability
WITH change_rate_signals AS (
    SELECT
        'input_vector_instability' as signal_type,
        'attestation' as domain,
        COUNT(*) || ' wallets with changed input vectors' as title,
        'Of observed wallets, ' || COUNT(*) || ' had input vector changes between scoring cycles.' as description,
        '[]'::jsonb as entities,
        COUNT(*)::float / GREATEST((SELECT COUNT(*) FROM {{ ref('int_input_vector_similarity') }}), 1) * 10 as novelty_score,
        'shift' as direction,
        COUNT(*)::float as magnitude,
        0 as baseline,
        jsonb_build_object(
            'total_observed', (SELECT COUNT(*) FROM {{ ref('int_input_vector_similarity') }}),
            'unchanged', (SELECT COUNT(*) FROM {{ ref('int_input_vector_similarity') }} WHERE change_status = 'unchanged')
        ) as detail
    FROM {{ ref('int_input_vector_similarity') }}
    WHERE change_status = 'changed'
),
edge_growth_signals AS (
    SELECT
        'edge_growth_spike' as signal_type,
        'attestation' as domain,
        'Edge creation: ' || edges_created || ' edges on ' || edge_date as title,
        'Daily edge creation rate: ' || edges_created || ' edges, $' || ROUND(total_value::numeric, 0) || ' total value.' as description,
        '[]'::jsonb as entities,
        CASE WHEN (SELECT AVG(edges_created) FROM {{ ref('int_edge_emergence_rate') }}) > 0
             THEN (edges_created - (SELECT AVG(edges_created) FROM {{ ref('int_edge_emergence_rate') }}))
                  / GREATEST((SELECT STDDEV_SAMP(edges_created) FROM {{ ref('int_edge_emergence_rate') }}), 1)
             ELSE 0 END as novelty_score,
        CASE WHEN edges_created > (SELECT AVG(edges_created) FROM {{ ref('int_edge_emergence_rate') }}) THEN 'up' ELSE 'down' END as direction,
        edges_created::float as magnitude,
        (SELECT AVG(edges_created) FROM {{ ref('int_edge_emergence_rate') }}) as baseline,
        jsonb_build_object('total_value', total_value, 'avg_weight', avg_weight) as detail
    FROM {{ ref('int_edge_emergence_rate') }}
    WHERE edge_date = (SELECT MAX(edge_date) FROM {{ ref('int_edge_emergence_rate') }})
)

SELECT * FROM change_rate_signals
UNION ALL SELECT * FROM edge_growth_signals
