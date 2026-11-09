-- Hecho equipo-partido: dos filas por partido, una desde el punto de vista de cada equipo.
-- Es la tabla base para forma, rachas y estadísticas por equipo.
with sides as (
    select event_id, sport, league_key, start_time, local_date, status_state, is_completed, result,
           decided_by_penalties, is_preseason,
           home_team_key as team_key, away_team_key as opponent_key, true as is_home,
           home_score as points_for, away_score as points_against
    from {{ ref('fct_game') }}
    union all
    select event_id, sport, league_key, start_time, local_date, status_state, is_completed, result,
           decided_by_penalties, is_preseason,
           away_team_key, home_team_key, false,
           away_score, home_score
    from {{ ref('fct_game') }}
)

select
    event_id,
    team_key,
    opponent_key,
    sport,
    league_key,
    start_time,
    local_date,
    status_state,
    is_completed,
    is_home,
    points_for,
    points_against,
    case
        when not is_completed then null
        when result = 'draw' then 'D'
        when (result = 'home') = is_home then 'W'
        else 'L'
    end as outcome,
    decided_by_penalties,
    is_preseason
from sides
