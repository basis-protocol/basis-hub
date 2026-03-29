-- Wallet domain signals — including the grade migration (HODL wave candidate)
WITH migration_signals AS (
    SELECT
        'grade_migration' as signal_type,
        'wallet' as domain,
        prior_grade || ' -> ' || current_grade || ': ' || wallet_count || ' wallets' as title,
        'Net grade migration: ' || wallet_count || ' wallets moved from ' || prior_grade || ' to ' || current_grade || '. Avg score change: ' || ROUND(avg_score_change::numeric, 1) as description,
        jsonb_build_array(prior_grade, current_grade) as entities,
        wallet_count::float / GREATEST((SELECT SUM(wallet_count) FROM {{ ref('int_wallet_grade_cohorts') }}), 1) * 20 as novelty_score,
        migration_direction as direction,
        wallet_count::float as magnitude,
        0 as baseline,
        jsonb_build_object('avg_score_change', avg_score_change, 'migration_direction', migration_direction) as detail
    FROM {{ ref('int_wallet_grade_cohorts') }}
    WHERE prior_grade != current_grade
      AND wallet_count >= 5
),
concentration_signals AS (
    SELECT
        'aggregate_concentration_shift' as signal_type,
        'wallet' as domain,
        'Median wallet HHI shifted to ' || ROUND(median_hhi::numeric, 0) as title,
        'Aggregate concentration changed. ' || wallets_scored || ' wallets observed.' as description,
        '[]'::jsonb as entities,
        CASE WHEN LAG(median_hhi) OVER (ORDER BY scored_date) > 0
             THEN ABS(median_hhi - LAG(median_hhi) OVER (ORDER BY scored_date)) / 500.0
             ELSE 0 END as novelty_score,
        CASE WHEN median_hhi > LAG(median_hhi) OVER (ORDER BY scored_date) THEN 'up' ELSE 'down' END as direction,
        median_hhi as magnitude,
        LAG(median_hhi) OVER (ORDER BY scored_date) as baseline,
        jsonb_build_object('mean_hhi', mean_hhi, 'wallets_scored', wallets_scored) as detail
    FROM {{ ref('int_wallet_concentration_trend') }}
    WHERE scored_date = (SELECT MAX(scored_date) FROM {{ ref('int_wallet_concentration_trend') }})
),
volatility_signals AS (
    SELECT
        'volatility_population_shift' as signal_type,
        'wallet' as domain,
        COUNT(*) || ' wallets with volatile scores (stddev > 5)' as title,
        'Population of volatile wallets changed.' as description,
        '[]'::jsonb as entities,
        COUNT(*)::float / GREATEST((SELECT COUNT(*) FROM {{ ref('int_wallet_score_volatility') }}), 1) * 10 as novelty_score,
        'shift' as direction,
        COUNT(*)::float as magnitude,
        0 as baseline,
        jsonb_build_object('total_wallets', (SELECT COUNT(*) FROM {{ ref('int_wallet_score_volatility') }})) as detail
    FROM {{ ref('int_wallet_score_volatility') }}
    WHERE score_volatility > 5
)

SELECT * FROM migration_signals
UNION ALL SELECT * FROM concentration_signals
UNION ALL SELECT * FROM volatility_signals
