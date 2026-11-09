-- Un registro por archivo bronze de marcadores (liga × día), con su metadato de linaje.
select
    json ->> '$._meta.league'                         as league_key,
    json ->> '$._meta.sport'                          as sport,
    cast(json ->> '$._meta.date' as date)             as scoreboard_date,
    cast(json ->> '$._meta.ingested_at' as timestamptz) as ingested_at,
    json ->> '$._meta.source_url'                     as source_url,
    json -> '$.payload'                               as payload
from read_json_objects('{{ var("bronze") }}/scoreboard/*/*.json.gz', format = 'auto')
