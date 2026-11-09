-- Hoja de cada jugador por partido, en formato largo. ESPN da, por grupo de estadísticas
-- (general en NBA; passing/rushing/receiving en NFL; batting/pitching en MLB), una lista
-- de claves y, por jugador, una lista de valores en el mismo orden: se recorren en paralelo.
with teams as (
    select event_id, sport, unnest(json_extract(payload, '$.boxscore.players[*]')) as p
    from {{ ref('stg_espn__summary_files') }}
),

groups as (
    select event_id, sport, p ->> '$.team.id' as team_id, unnest(json_extract(p, '$.statistics[*]')) as g
    from teams
),

athletes as (
    select
        event_id, sport, team_id,
        coalesce(g ->> '$.name', 'general')                as stat_group,
        json_extract_string(g, '$.keys[*]')                as stat_keys,
        json_extract_string(g, '$.labels[*]')              as stat_labels,
        unnest(json_extract(g, '$.athletes[*]'))           as a
    from groups
),

long as (
    select
        event_id, sport, team_id, stat_group,
        a ->> '$.athlete.id'                               as player_id,
        a ->> '$.athlete.displayName'                      as player_name,
        a ->> '$.athlete.shortName'                        as player_short_name,
        a ->> '$.athlete.headshot.href'                    as headshot,
        a ->> '$.athlete.jersey'                           as jersey,
        a ->> '$.athlete.position.abbreviation'            as position,
        coalesce(try_cast(a ->> '$.starter' as boolean), false)    as is_starter,
        coalesce(try_cast(a ->> '$.didNotPlay' as boolean), false) as did_not_play,
        unnest(stat_keys)                                  as stat_key,
        unnest(stat_labels)                                as stat_label,
        unnest(json_extract_string(a, '$.stats[*]'))       as display_value
    from athletes
)

select * from long
where stat_key is not null and display_value is not null
