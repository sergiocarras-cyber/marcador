-- Puntuación de interés (0-100) por partido, para destacar los mejores en la portada.
--
--   Partido por jugar:  50 % peso de la competición + 50 % nivel del enfrentamiento
--   Partido terminado:  30 % competición + 35 % enfrentamiento + 35 % emoción
--   Playoffs de EE. UU.: +15 puntos (con tope en 100)
--
-- El nivel del enfrentamiento premia que los dos equipos sean buenos, no solo uno:
-- mezcla la media de su porcentaje de victorias con el peor de los dos.
-- La emoción mide lo ajustado del marcador por deporte, con extras por prórroga,
-- remontada y muchos goles. Cada ingrediente sale como columna para poder explicar
-- por qué se destaca un partido.

with strength as (
    select team_key,
           case when played >= 3 then (wins + 0.5 * coalesce(draws, 0)) / played end as win_rate
    from {{ ref('team_form') }}
),

first_goal as (
    select event_id, arg_min('futbol-' || team_id, clock_seconds) as first_scoring_team
    from {{ ref('stg_espn__match_events') }}
    where is_goal and not is_shootout and not is_own_goal
    group by event_id
),

base as (
    select
        g.*,
        coalesce(l.prestige, 0.5)                           as prestige,
        coalesce(sh.win_rate, 0.5)                          as home_strength,
        coalesce(sa.win_rate, 0.5)                          as away_strength,
        ph.position                                         as home_position,
        pa.position                                         as away_position,
        fg.first_scoring_team,
        case g.sport when 'mlb' then 4 else 2 end           as half_periods,
        case when g.result = 'home' then g.away_team_key
             when g.result = 'away' then g.home_team_key end as loser_key
    from {{ ref('fct_game') }} g
    left join {{ ref('leagues') }} l on l.league_key = g.league_key
    left join strength sh on sh.team_key = g.home_team_key
    left join strength sa on sa.team_key = g.away_team_key
    left join {{ ref('standings') }} ph on ph.team_key = g.home_team_key
    left join {{ ref('standings') }} pa on pa.team_key = g.away_team_key
    left join first_goal fg on fg.event_id = g.event_id
    where not g.is_preseason
      and g.status_name not in ('STATUS_POSTPONED', 'STATUS_CANCELED')
),

features as (
    select
        *,
        0.5 * (home_strength + away_strength) / 2 + 0.5 * least(home_strength, away_strength) as matchup,
        coalesce(home_position <= 3 and away_position <= 3, false)                           as top_clash,
        sport in ('nba', 'nfl', 'mlb') and season_type = 3                                    as is_playoffs,
        case when is_completed then
            case sport
                when 'futbol' then case when margin <= 1 then 1.0 when margin = 2 then 0.5 else 0.2 end
                when 'nba'    then case when margin <= 5 then 1.0 when margin <= 10 then 0.6 else 0.2 end
                when 'nfl'    then case when margin <= 3 then 1.0 when margin <= 8 then 0.6 else 0.2 end
                when 'mlb'    then case when margin <= 1 then 1.0 when margin <= 3 then 0.5 else 0.2 end
            end
        end                                                                                   as closeness,
        is_completed and went_to_extra_time                                                   as overtime,
        is_completed and sport = 'futbol' and home_score + away_score >= 5                    as goal_fest,
        is_completed and coalesce(case
            when sport = 'futbol' then first_scoring_team = loser_key
            when result = 'home' then list_sum(away_linescores[1:half_periods]) - list_sum(home_linescores[1:half_periods])
                                      >= case sport when 'nba' then 8 when 'nfl' then 7 else 2 end
            when result = 'away' then list_sum(home_linescores[1:half_periods]) - list_sum(away_linescores[1:half_periods])
                                      >= case sport when 'nba' then 8 when 'nfl' then 7 else 2 end
        end, false)                                                                            as comeback
    from base
)

select
    event_id,
    sport,
    league_key,
    start_time,
    status_state,
    is_completed,
    round(prestige, 2)  as prestige,
    round(matchup, 2)   as matchup,
    round(closeness, 2) as closeness,
    top_clash,
    is_playoffs,
    overtime,
    comeback,
    goal_fest,
    coalesce(closeness >= 1, false) as tight_finish,
    least(100, round(100 * (
        case
            when is_completed then 0.30 * prestige + 0.35 * matchup
                 + 0.35 * least(1.0, 0.75 * closeness + 0.25 * overtime::int + 0.25 * comeback::int + 0.25 * goal_fest::int)
            else 0.5 * prestige + 0.5 * matchup
        end
    ) + 15 * is_playoffs::int))::integer as interest_score
from features
