{% macro rank_stability(score_column, entity_column, date_column, window_days) %}
    WITH ranked AS (
        SELECT
            {{ entity_column }},
            {{ date_column }},
            RANK() OVER (PARTITION BY {{ date_column }} ORDER BY {{ score_column }} DESC) as daily_rank
        FROM {{ source }}
        WHERE {{ date_column }} >= CURRENT_DATE - INTERVAL '{{ window_days }} days'
    )
    SELECT
        {{ entity_column }},
        STDDEV_SAMP(daily_rank) as rank_volatility,
        AVG(daily_rank) as avg_rank,
        COUNT(*) as days_observed
    FROM ranked
    GROUP BY {{ entity_column }}
{% endmacro %}
