select event_id, interest_score from {{ ref('game_interest') }}
where interest_score is null or interest_score < 0 or interest_score > 100
