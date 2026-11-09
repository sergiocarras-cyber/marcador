-- Incidencias de fútbol: goles y tarjetas, una fila por incidencia.
with exploded as (
    select
        event_id,
        unnest(json_extract(competition, '$.details[*]')) as d
    from {{ ref('stg_espn__events') }}
    where sport = 'futbol'
)

select
    event_id,
    d ->> '$.team.id'                                  as team_id,
    d ->> '$.type.text'                                as event_type,
    d ->> '$.clock.displayValue'                       as minute_label,
    cast(d ->> '$.clock.value' as double)              as clock_seconds,
    d ->> '$.athletesInvolved[0].id'                   as player_id,
    d ->> '$.athletesInvolved[0].shortName'            as player_short_name,
    d ->> '$.athletesInvolved[0].displayName'          as player_name,
    coalesce(try_cast(d ->> '$.scoringPlay' as boolean), false) as is_goal,
    coalesce(try_cast(d ->> '$.penaltyKick' as boolean), false) as is_penalty,
    coalesce(try_cast(d ->> '$.ownGoal' as boolean), false)     as is_own_goal,
    coalesce(try_cast(d ->> '$.redCard' as boolean), false)     as is_red_card,
    coalesce(try_cast(d ->> '$.yellowCard' as boolean), false)  as is_yellow_card,
    coalesce(try_cast(d ->> '$.shootout' as boolean), false)    as is_shootout
from exploded
