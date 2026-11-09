-- Hecho de partidos: un registro por partido, con local y visitante en columnas.
with home as (select * from {{ ref('stg_espn__competitors') }} where home_away = 'home'),
     away as (select * from {{ ref('stg_espn__competitors') }} where home_away = 'away')

select
    e.event_id,
    e.sport,
    e.league_key,
    l.league_name,
    e.season,
    e.season_type,
    -- En EE. UU. el tipo 1 es pretemporada: no cuenta para forma ni rachas
    e.sport in ('nba', 'nfl', 'mlb') and e.season_type = 1 as is_preseason,
    e.start_time,
    -- Día "natural" del aficionado: hora de Madrid para el fútbol, de Nueva York para EE. UU.
    cast(timezone(s.local_timezone, e.start_time) as date) as local_date,
    e.status_state,
    e.status_name,
    e.period,
    e.display_clock,
    e.status_detail,
    e.venue,
    e.broadcast,
    e.link,

    h.sport || '-' || h.team_id                         as home_team_key,
    a.sport || '-' || a.team_id                         as away_team_key,
    h.score                                             as home_score,
    a.score                                             as away_score,
    h.linescores                                        as home_linescores,
    a.linescores                                        as away_linescores,
    h.record_summary                                    as home_record,
    a.record_summary                                    as away_record,

    e.status_state = 'post' and e.status_name not in ('STATUS_POSTPONED', 'STATUS_CANCELED') as is_completed,
    case
        when not (e.status_state = 'post' and e.status_name not in ('STATUS_POSTPONED', 'STATUS_CANCELED')) then null
        when h.is_winner then 'home'
        when a.is_winner then 'away'
        when h.score > a.score then 'home'
        when a.score > h.score then 'away'
        else 'draw'
    end                                                 as result,
    abs(h.score - a.score)                              as margin,
    case
        when e.sport = 'futbol' then e.status_name in ('STATUS_FINAL_AET', 'STATUS_FINAL_PEN')
        else e.period > s.regulation_periods
    end                                                 as went_to_extra_time,
    e.status_name = 'STATUS_FINAL_PEN'                  as decided_by_penalties,
    e.ingested_at
from {{ ref('stg_espn__events') }} e
join home h using (event_id)
join away a using (event_id)
left join {{ ref('leagues') }} l on l.league_key = e.league_key
left join {{ ref('sports') }} s on s.sport = e.sport
