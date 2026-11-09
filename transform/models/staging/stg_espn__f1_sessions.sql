-- Fórmula 1: una fila por piloto y sesión (libres, clasificación, sprint, carrera).
with files as (
    select
        cast(json ->> '$._meta.season' as integer) as season,
        json -> '$.payload' as payload
    from read_json_objects('{{ var("bronze") }}/f1/*.json.gz', format = 'auto')
),

grand_prix as (
    select season, unnest(json_extract(payload, '$.events[*]')) as ev from files
),

sessions as (
    select
        season,
        ev ->> '$.id'                 as grand_prix_id,
        ev ->> '$.name'               as grand_prix_name,
        ev ->> '$.circuit.fullName'   as circuit,
        unnest(json_extract(ev, '$.competitions[*]')) as s
    from grand_prix
),

results as (
    select
        season, grand_prix_id, grand_prix_name, circuit,
        s ->> '$.id'                      as session_id,
        s ->> '$.type.abbreviation'       as session_type,
        {{ parse_ts("s ->> '$.date'") }} as session_start,
        s ->> '$.status.type.state'       as status_state,
        -- Las sesiones futuras aún no tienen pilotos: se conservan con una fila vacía
        unnest(case when len(coalesce(json_extract(s, '$.competitors[*]'), [])) = 0
                    then [null::json] else json_extract(s, '$.competitors[*]') end) as c
    from sessions
)

select
    season, grand_prix_id, grand_prix_name, circuit, session_id, session_type, session_start, status_state,
    c ->> '$.id'                          as driver_id,
    c ->> '$.athlete.displayName'         as driver_name,
    c ->> '$.athlete.shortName'           as driver_short_name,
    c ->> '$.athlete.flag.alt'            as driver_country,
    c ->> '$.athlete.flag.href'           as driver_flag,
    try_cast(c ->> '$.order' as integer)  as position,
    coalesce(try_cast(c ->> '$.winner' as boolean), false) as is_winner
from results
