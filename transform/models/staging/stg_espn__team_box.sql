-- Estadísticas de equipo por partido, en formato largo (una fila por estadística).
-- Fútbol, NBA y NFL las dan planas; MLB las agrupa (batting, pitching, fielding) y aquí
-- se aplanan como "grupo.estadística".
with teams as (
    select event_id, sport, unnest(json_extract(payload, '$.boxscore.teams[*]')) as t
    from {{ ref('stg_espn__summary_files') }}
),

stats as (
    select event_id, sport, t ->> '$.team.id' as team_id, unnest(json_extract(t, '$.statistics[*]')) as s
    from teams
),

flat as (
    select event_id, sport, team_id,
           s ->> '$.name' as stat_name, s ->> '$.label' as source_label, s ->> '$.displayValue' as display_value
    from stats
    where json_extract(s, '$.stats') is null
    union all
    select event_id, sport, team_id,
           (s ->> '$.name') || '.' || (x ->> '$.name'), x ->> '$.displayName', x ->> '$.displayValue'
    from (select *, unnest(json_extract(s, '$.stats[*]')) as x from stats where json_extract(s, '$.stats') is not null)
)

select *, try_cast(display_value as double) as value
from flat
-- ESPN repite alguna estadística (p. ej. "interceptions" en NFL): una por equipo y partido
qualify row_number() over (partition by event_id, team_id, stat_name order by display_value) = 1
