-- Un registro por equipo y partido.
with exploded as (
    select
        event_id,
        sport,
        status_state,
        unnest(json_extract(competition, '$.competitors[*]')) as c
    from {{ ref('stg_espn__events') }}
)

select
    event_id,
    sport,
    c ->> '$.team.id'                                   as team_id,
    c ->> '$.homeAway'                                  as home_away,
    c ->> '$.team.displayName'                          as team_name,
    coalesce(c ->> '$.team.shortDisplayName', c ->> '$.team.name') as team_short_name,
    c ->> '$.team.abbreviation'                         as team_abbreviation,
    c ->> '$.team.logo'                                 as team_logo,
    -- Antes del partido ESPN devuelve "0": solo es un marcador real si ha empezado
    case when status_state in ('in', 'post') then try_cast(c ->> '$.score' as integer) end as score,
    coalesce(try_cast(c ->> '$.winner' as boolean), false) as is_winner,
    c ->> '$.records[0].summary'                        as record_summary,
    cast(json_extract(c, '$.linescores[*].value') as double[]) as linescores,
    c -> '$.leaders'                                    as leaders
from exploded
