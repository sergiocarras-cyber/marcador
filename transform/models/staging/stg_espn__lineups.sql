-- Alineaciones de fútbol: titulares, suplentes y cambios, con la formación de cada equipo.
with rosters as (
    select event_id, unnest(json_extract(payload, '$.rosters[*]')) as r
    from {{ ref('stg_espn__summary_files') }}
    where sport = 'futbol'
),

players as (
    select event_id, r ->> '$.team.id' as team_id, r ->> '$.formation' as formation,
           unnest(json_extract(r, '$.roster[*]')) as x
    from rosters
)

select
    event_id,
    team_id,
    formation,
    x ->> '$.athlete.id'                                   as player_id,
    x ->> '$.athlete.displayName'                          as player_name,
    x ->> '$.athlete.shortName'                            as player_short_name,
    x ->> '$.jersey'                                       as jersey,
    x ->> '$.position.abbreviation'                        as position,
    coalesce(try_cast(x ->> '$.starter' as boolean), false)     as is_starter,
    coalesce(try_cast(x ->> '$.subbedIn' as boolean), false)    as subbed_in,
    coalesce(try_cast(x ->> '$.subbedOut' as boolean), false)   as subbed_out,
    try_cast(x ->> '$.formationPlace' as integer)          as formation_place
from players
