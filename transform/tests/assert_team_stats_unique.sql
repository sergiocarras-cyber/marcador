-- Una sola fila por partido, equipo y estadística.
select event_id, team_key, stat_name, count(*) from {{ ref('fct_team_game_stats') }}
group by all having count(*) > 1
