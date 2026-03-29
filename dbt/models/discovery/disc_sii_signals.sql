-- SII domain signals
WITH rank_signals AS (
    SELECT
        'rank_instability' as signal_type,
        'sii' as domain,
        stablecoin || ' rank volatility: ' || ROUND(rank_volatility::numeric, 2) as title,
        'Rank has been unstable over 7 days. Range: ' || rank_range || ' positions.' as description,
        jsonb_build_array(stablecoin) as entities,
        CASE WHEN (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY rank_volatility) FROM {{ ref('int_sii_rank_history') }}) > 0
            THEN (rank_volatility - (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY rank_volatility) FROM {{ ref('int_sii_rank_history') }}))
                 / GREATEST((SELECT STDDEV_SAMP(rank_volatility) FROM {{ ref('int_sii_rank_history') }}), 0.01)
            ELSE 0 END as novelty_score,
        'shift' as direction,
        rank_volatility as magnitude,
        (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY rank_volatility) FROM {{ ref('int_sii_rank_history') }}) as baseline,
        jsonb_build_object('avg_rank', avg_rank, 'rank_range', rank_range, 'days', days_observed) as detail
    FROM {{ ref('int_sii_rank_history') }}
    WHERE rank_volatility > 0
),
distribution_signals AS (
    SELECT
        'distribution_shift' as signal_type,
        'sii' as domain,
        'SII spread ' || CASE WHEN spread > spread_7d_avg THEN 'widened' ELSE 'compressed' END || ' to ' || ROUND(spread::numeric, 1) as title,
        'Current spread (' || ROUND(spread::numeric, 1) || ') vs 7d avg (' || ROUND(spread_7d_avg::numeric, 1) || ')' as description,
        '[]'::jsonb as entities,
        CASE WHEN spread_7d_stddev > 0 THEN ABS(spread - spread_7d_avg) / spread_7d_stddev ELSE 0 END as novelty_score,
        CASE WHEN spread > spread_7d_avg THEN 'up' ELSE 'down' END as direction,
        spread as magnitude,
        spread_7d_avg as baseline,
        jsonb_build_object('std_dev', std_dev, 'mean_score', mean_score, 'coins_scored', coins_scored) as detail
    FROM {{ ref('int_sii_distribution_stats') }}
    WHERE score_date = (SELECT MAX(score_date) FROM {{ ref('int_sii_distribution_stats') }})
),
velocity_signals AS (
    SELECT
        'score_acceleration' as signal_type,
        'sii' as domain,
        stablecoin || ' score accelerating: ' || ROUND(acceleration::numeric, 2) || ' pts' as title,
        'Score velocity changed by ' || ROUND(acceleration::numeric, 2) || ' points.' as description,
        jsonb_build_array(stablecoin) as entities,
        ABS(acceleration) as novelty_score,
        CASE WHEN acceleration > 0 THEN 'up' ELSE 'down' END as direction,
        ABS(acceleration) as magnitude,
        0 as baseline,
        jsonb_build_object('velocity', velocity, 'current_score', overall_score) as detail
    FROM {{ ref('int_sii_score_deltas') }}
    WHERE score_date = (SELECT MAX(score_date) FROM {{ ref('int_sii_score_deltas') }})
      AND ABS(acceleration) > 1.0
),
correlation_signals AS (
    SELECT
        'correlation_break' as signal_type,
        'sii' as domain,
        coin_a || '-' || coin_b || ' correlation: ' || ROUND(correlation_14d::numeric, 2) as title,
        'Pairwise 14-day correlation dropped. ' || data_points || ' data points.' as description,
        jsonb_build_array(coin_a, coin_b) as entities,
        CASE WHEN correlation_14d < 0.3 THEN (0.85 - correlation_14d) / 0.3
             ELSE 0 END as novelty_score,
        'break' as direction,
        correlation_14d as magnitude,
        0.85 as baseline,
        jsonb_build_object('data_points', data_points) as detail
    FROM {{ ref('int_sii_cross_correlation') }}
    WHERE correlation_14d < 0.5
),
masked_signals AS (
    SELECT
        'masked_deterioration' as signal_type,
        'sii' as domain,
        s.stablecoin_id || ': sub-score diverging from composite' as title,
        'Overall stable but a category sub-score diverged by >15 points.' as description,
        jsonb_build_array(s.stablecoin_id) as entities,
        GREATEST(
            ABS(COALESCE(s.peg_score, s.overall_score) - s.overall_score),
            ABS(COALESCE(s.liquidity_score, s.overall_score) - s.overall_score),
            ABS(COALESCE(s.distribution_score, s.overall_score) - s.overall_score),
            ABS(COALESCE(s.structural_score, s.overall_score) - s.overall_score)
        ) / 10.0 as novelty_score,
        'down' as direction,
        GREATEST(
            ABS(COALESCE(s.peg_score, s.overall_score) - s.overall_score),
            ABS(COALESCE(s.liquidity_score, s.overall_score) - s.overall_score),
            ABS(COALESCE(s.distribution_score, s.overall_score) - s.overall_score),
            ABS(COALESCE(s.structural_score, s.overall_score) - s.overall_score)
        ) as magnitude,
        s.overall_score as baseline,
        jsonb_build_object(
            'peg_score', s.peg_score, 'liquidity_score', s.liquidity_score,
            'distribution_score', s.distribution_score, 'structural_score', s.structural_score
        ) as detail
    FROM {{ ref('stg_scores') }} s
    WHERE ABS(COALESCE(s.daily_change, 0)) < 1.0
      AND GREATEST(
            ABS(COALESCE(s.peg_score, s.overall_score) - s.overall_score),
            ABS(COALESCE(s.liquidity_score, s.overall_score) - s.overall_score),
            ABS(COALESCE(s.distribution_score, s.overall_score) - s.overall_score),
            ABS(COALESCE(s.structural_score, s.overall_score) - s.overall_score)
          ) > 15
)

SELECT * FROM rank_signals
UNION ALL SELECT * FROM distribution_signals
UNION ALL SELECT * FROM velocity_signals
UNION ALL SELECT * FROM correlation_signals
UNION ALL SELECT * FROM masked_signals
