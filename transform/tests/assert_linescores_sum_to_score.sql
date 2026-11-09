-- NBA, NFL y MLB: la suma de parciales (cuartos o entradas) coincide con el marcador final.
select event_id, sport, home_score, list_sum(home_linescores) as home_sum, away_score, list_sum(away_linescores) as away_sum
from {{ ref('fct_game') }}
where is_completed
  and sport in ('nba', 'nfl', 'mlb')
  and len(home_linescores) > 0
  and (list_sum(home_linescores) <> home_score or list_sum(away_linescores) <> away_score)
