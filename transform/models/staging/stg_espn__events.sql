-- Un registro por partido. Si un partido aparece en varios archivos (p. ej. se aplazó
-- y cambió de día), nos quedamos con la versión ingerida más recientemente.
with exploded as (
    select
        f.league_key,
        f.sport,
        f.ingested_at,
        unnest(json_extract(f.payload, '$.events[*]')) as e
    from {{ ref('stg_espn__scoreboard_files') }} f
)

select
    e ->> '$.id'                                       as event_id,
    league_key,
    sport,
    cast(e ->> '$.season.year' as integer)             as season,
    cast(e ->> '$.season.type' as integer)             as season_type,
    {{ parse_ts("e ->> '$.date'") }}              as start_time,
    e ->> '$.name'                                     as event_name,
    e ->> '$.status.type.state'                        as status_state,
    e ->> '$.status.type.name'                         as status_name,
    cast(e ->> '$.status.period' as integer)           as period,
    e ->> '$.status.displayClock'                      as display_clock,
    e ->> '$.status.type.shortDetail'                  as status_detail,
    e ->> '$.competitions[0].venue.fullName'           as venue,
    e ->> '$.competitions[0].broadcasts[0].names[0]'   as broadcast,
    e ->> '$.links[0].href'                            as link,
    e -> '$.competitions[0]'                           as competition,
    ingested_at
from exploded
qualify row_number() over (partition by e ->> '$.id' order by ingested_at desc) = 1
