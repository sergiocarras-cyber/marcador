-- Un partido terminado siempre tiene marcador.
select event_id from {{ ref('fct_game') }}
where is_completed and (home_score is null or away_score is null)
