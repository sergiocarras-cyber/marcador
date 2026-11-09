-- Dimensión de equipos (SCD tipo 1: atributos más recientes).
-- Fuentes: los marcadores (cubren copas y competiciones europeas) y la clasificación
-- (que fija la liga doméstica del equipo).
with appearances as (
    select c.sport, c.team_id, c.team_name, c.team_short_name, c.team_abbreviation, c.team_logo,
           c.team_color, c.team_alt_color,
           e.league_key, e.start_time
    from {{ ref('stg_espn__competitors') }} c
    join {{ ref('stg_espn__events') }} e using (event_id)
),

latest_attributes as (
    select
        sport,
        team_id,
        arg_max(team_name, start_time)         as team_name,
        arg_max(team_short_name, start_time)   as team_short_name,
        arg_max(team_abbreviation, start_time) as team_abbreviation,
        arg_max(team_logo, start_time)         as team_logo,
        arg_max(team_color, start_time)        as team_color,
        arg_max(team_alt_color, start_time)    as team_alt_color,
        count(*)                               as games_seen
    from appearances
    group by all
),

most_frequent_league as (
    select sport, team_id, arg_max(league_key, n) as league_key
    from (select sport, team_id, league_key, count(*) as n from appearances group by all)
    group by all
),

domestic_league as (
    select sport, team_id, any_value(league_key) as league_key, any_value(group_name) as group_name
    from {{ ref('stg_espn__standings') }}
    group by all
)

select
    a.sport || '-' || a.team_id                       as team_key,
    a.sport,
    a.team_id,
    a.team_name,
    a.team_short_name,
    a.team_abbreviation,
    a.team_logo,
    a.team_color,
    a.team_alt_color,
    coalesce(d.league_key, f.league_key)              as primary_league_key,
    d.group_name                                      as conference,
    d.league_key is not null                          as has_standings,
    a.games_seen
from latest_attributes a
left join domestic_league d using (sport, team_id)
left join most_frequent_league f using (sport, team_id)
