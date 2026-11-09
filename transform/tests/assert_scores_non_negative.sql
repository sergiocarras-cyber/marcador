select event_id from {{ ref('fct_game') }}
where home_score < 0 or away_score < 0
