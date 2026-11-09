-- Jugadores destacados por partido. ESPN los da a dos niveles:
--   · por equipo (NBA: puntos, rebotes, asistencias de cada equipo)
--   · por partido (NFL/MLB: líder de pase, carrera, recepción…)
-- Nos quedamos con el primer líder de cada categoría.
with team_level as (
    select
        event_id,
        team_id,
        'team' as leader_level,
        unnest(json_extract(leaders, '$[*]')) as cat
    from {{ ref('stg_espn__competitors') }}
    where leaders is not null
),

game_level as (
    select
        event_id,
        null::varchar as team_id,
        'game' as leader_level,
        unnest(json_extract(competition, '$.leaders[*]')) as cat
    from {{ ref('stg_espn__events') }}
    where json_extract(competition, '$.leaders') is not null
),

unioned as (
    select * from team_level
    union all
    select * from game_level
)

select
    event_id,
    coalesce(team_id, cat ->> '$.leaders[0].team.id', cat ->> '$.leaders[0].athlete.team.id') as team_id,
    leader_level,
    cat ->> '$.name'                                 as category,
    cat ->> '$.displayName'                          as category_label,
    cat ->> '$.leaders[0].athlete.id'                as player_id,
    cat ->> '$.leaders[0].athlete.displayName'       as player_name,
    cat ->> '$.leaders[0].athlete.headshot'          as player_headshot,
    cat ->> '$.leaders[0].displayValue'              as display_value,
    cast(cat ->> '$.leaders[0].value' as double)     as value
from unioned
where cat ->> '$.leaders[0].athlete.id' is not null
