-- All signals in disc_all_signals should have positive novelty scores
SELECT *
FROM {{ ref('disc_all_signals') }}
WHERE novelty_score < 0
