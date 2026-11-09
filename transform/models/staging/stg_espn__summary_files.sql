-- Un registro por ficha de partido (resumen) guardada en bronze.
select
    json ->> '$._meta.event_id'                          as event_id,
    json ->> '$._meta.league'                            as league_key,
    json ->> '$._meta.sport'                             as sport,
    cast(json ->> '$._meta.ingested_at' as timestamptz)  as ingested_at,
    json -> '$.payload'                                  as payload
from read_json_objects('{{ var("bronze") }}/summary/*/*.json.gz', format = 'auto')
