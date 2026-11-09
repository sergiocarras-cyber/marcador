-- Fútbol: los goles registrados como incidencias cuadran con el marcador.
-- Es un aviso y no un error: la fuente a veces publica el resultado antes que el detalle.
{{ config(severity = 'warn') }}
with goals as (
    select event_id, team_id, count(*) as goals
    from {{ ref('stg_espn__match_events') }}
    where is_goal and not is_shootout
    group by all
),
games as (
    select g.event_id, g.home_team_key, g.away_team_key, g.home_score, g.away_score
    from {{ ref('fct_game') }} g
    where g.sport = 'futbol' and g.is_completed
      and exists (select 1 from {{ ref('stg_espn__match_events') }} m where m.event_id = g.event_id)
)
select g.*, coalesce(h.goals, 0) as home_goals_logged, coalesce(a.goals, 0) as away_goals_logged
from games g
left join goals h on h.event_id = g.event_id and 'futbol-' || h.team_id = g.home_team_key
left join goals a on a.event_id = g.event_id and 'futbol-' || a.team_id = g.away_team_key
where coalesce(h.goals, 0) <> g.home_score or coalesce(a.goals, 0) <> g.away_score
