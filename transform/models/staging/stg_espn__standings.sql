-- Clasificación actual por liga y grupo (conferencia en NBA/NFL/MLB).
with files as (
    select
        json ->> '$._meta.league' as league_key,
        json ->> '$._meta.sport'  as sport,
        cast(json ->> '$._meta.ingested_at' as timestamptz) as ingested_at,
        json -> '$.payload'       as payload
    from read_json_objects('{{ var("bronze") }}/standings/*.json.gz', format = 'auto')
),

groups as (
    select league_key, sport, ingested_at, unnest(json_extract(payload, '$.children[*]')) as g
    from files
),

entries as (
    select league_key, sport, ingested_at, g ->> '$.name' as group_name,
           unnest(json_extract(g, '$.standings.entries[*]')) as entry
    from groups
),

flat as (
    select
        league_key,
        sport,
        group_name,
        ingested_at,
        entry ->> '$.team.id'                   as team_id,
        entry ->> '$.team.displayName'          as team_name,
        entry ->> '$.team.shortDisplayName'     as team_short_name,
        entry ->> '$.team.abbreviation'         as team_abbreviation,
        entry ->> '$.team.logos[0].href'        as team_logo,
        entry ->> '$.note.description'          as qualification_note,
        json_extract(entry, '$.stats[*]')       as stats
    from entries
)

select
    league_key, sport, group_name, team_id, team_name, team_short_name, team_abbreviation, team_logo,
    qualification_note, ingested_at,
    {% for stat in ['rank', 'gamesPlayed', 'wins', 'losses', 'ties', 'points', 'pointsFor', 'pointsAgainst', 'playoffSeed'] %}
    try_cast(json_extract_string(list_filter(stats, s -> json_extract_string(s, '$.name') = '{{ stat }}')[1], '$.value') as double) as {{ stat | lower if stat == 'rank' else stat }},
    {% endfor %}
    json_extract_string(list_filter(stats, s -> json_extract_string(s, '$.name') = 'overall')[1], '$.displayValue') as overall_record
from flat
