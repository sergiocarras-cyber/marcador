-- Conciliación: en la NBA, la suma de puntos de los jugadores es el marcador del equipo.
select p.event_id, p.team_key, sum(p.value) as player_points,
       any_value(case when p.team_key = g.home_team_key then g.home_score else g.away_score end) as team_score
from {{ ref('fct_player_game_stats') }} p
join {{ ref('fct_game') }} g using (event_id)
where p.stat_key = 'points' and g.sport = 'nba' and g.is_completed
group by all
having sum(p.value) <> any_value(case when p.team_key = g.home_team_key then g.home_score else g.away_score end)
