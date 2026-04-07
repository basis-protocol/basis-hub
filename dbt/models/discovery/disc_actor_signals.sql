-- Actor domain signals (Primitive #21)
-- Detects composition shifts, flow divergences, reclassification waves, agent spikes

WITH composition_shift AS (
    -- Agent holder share changed >5pp in 7 days for any stablecoin
    SELECT
        'actor_composition_shift' AS signal_type,
        'actor' AS domain,
        symbol || ': agent share shifted to ' || ROUND(curr.pct_value::numeric, 1) || '%' AS title,
        'Agent holder share for ' || symbol || ' changed by '
            || ROUND(ABS(curr.pct_value - prev.pct_value)::numeric, 1) || 'pp in 7 days' AS description,
        jsonb_build_array(symbol) AS entities,
        ABS(curr.pct_value - prev.pct_value) / 5.0 AS novelty_score,
        CASE WHEN curr.pct_value > prev.pct_value THEN 'up' ELSE 'down' END AS direction,
        curr.pct_value AS magnitude,
        prev.pct_value AS baseline,
        jsonb_build_object(
            'current_pct', curr.pct_value,
            'previous_pct', prev.pct_value,
            'change_pp', curr.pct_value - prev.pct_value,
            'current_usd', curr.total_usd
        ) AS detail
    FROM {{ ref('int_actor_composition_by_asset') }} curr
    JOIN {{ ref('int_actor_composition_by_asset') }} prev
        ON curr.token_address = prev.token_address
        AND curr.actor_type = prev.actor_type
        AND prev.indexed_date = curr.indexed_date - INTERVAL '7 days'
    WHERE curr.actor_type = 'autonomous_agent'
      AND curr.indexed_date = (SELECT MAX(indexed_date) FROM {{ ref('int_actor_composition_by_asset') }})
      AND ABS(curr.pct_value - prev.pct_value) > 5
),
flow_divergence AS (
    -- Agent and human flows in opposite directions for 3+ consecutive days
    SELECT
        'actor_flow_divergence' AS signal_type,
        'actor' AS domain,
        symbol || ': agent/human flow divergence' AS title,
        'Agents and humans flowing opposite directions for ' || symbol AS description,
        jsonb_build_array(symbol) AS entities,
        2.5 AS novelty_score,
        'divergence' AS direction,
        ABS(agent_flow.net_flow_usd) AS magnitude,
        0 AS baseline,
        jsonb_build_object(
            'agent_net_flow', agent_flow.net_flow_usd,
            'human_net_flow', human_flow.net_flow_usd
        ) AS detail
    FROM {{ ref('int_actor_flow_direction') }} agent_flow
    JOIN {{ ref('int_actor_flow_direction') }} human_flow
        ON agent_flow.symbol = human_flow.symbol
        AND agent_flow.flow_date = human_flow.flow_date
    WHERE agent_flow.actor_type = 'autonomous_agent'
      AND human_flow.actor_type = 'human'
      AND agent_flow.flow_date = (SELECT MAX(flow_date) FROM {{ ref('int_actor_flow_direction') }})
      AND SIGN(agent_flow.net_flow_usd) != SIGN(human_flow.net_flow_usd)
      AND ABS(agent_flow.net_flow_usd) > 1000
      AND ABS(human_flow.net_flow_usd) > 1000
),
reclassification_wave AS (
    -- >10 wallets reclassified in 24 hours
    SELECT
        'reclassification_wave' AS signal_type,
        'actor' AS domain,
        cnt || ' wallets reclassified in 24h' AS title,
        cnt || ' wallets changed actor type. Most common: ' || most_common AS description,
        '[]'::jsonb AS entities,
        cnt::float / 10.0 AS novelty_score,
        'shift' AS direction,
        cnt::float AS magnitude,
        0 AS baseline,
        jsonb_build_object('reclassification_count', cnt, 'most_common_transition', most_common) AS detail
    FROM (
        SELECT
            COUNT(*) AS cnt,
            MODE() WITHIN GROUP (ORDER BY previous_type || ' -> ' || actor_type) AS most_common
        FROM {{ source('wallet_graph', 'actor_classification_history') }}
        WHERE classified_at > NOW() - INTERVAL '24 hours'
    ) sub
    WHERE cnt > 10
),
agent_concentration_spike AS (
    -- Agent share exceeded 40% for any stablecoin (high correlated exit risk)
    SELECT
        'agent_concentration_spike' AS signal_type,
        'actor' AS domain,
        symbol || ': ' || ROUND(pct_value::numeric, 1) || '% agent-held' AS title,
        'Autonomous agents hold ' || ROUND(pct_value::numeric, 1) || '% of ' || symbol || ' by value' AS description,
        jsonb_build_array(symbol) AS entities,
        (pct_value - 40) / 10.0 AS novelty_score,
        'up' AS direction,
        pct_value AS magnitude,
        40 AS baseline,
        jsonb_build_object('agent_usd', total_usd, 'wallet_count', wallet_count) AS detail
    FROM {{ ref('int_actor_composition_by_asset') }}
    WHERE actor_type = 'autonomous_agent'
      AND indexed_date = (SELECT MAX(indexed_date) FROM {{ ref('int_actor_composition_by_asset') }})
      AND pct_value > 40
)

SELECT * FROM composition_shift
UNION ALL SELECT * FROM flow_divergence
UNION ALL SELECT * FROM reclassification_wave
UNION ALL SELECT * FROM agent_concentration_spike
