-- Estado de forma por equipo: últimos 5 resultados, racha actual (gaps-and-islands),
-- balance de la temporada y punteros al último, actual y próximo partido.
with played as (
    select *,
           row_number() over (partition by team_key order by start_time desc) as recency
    from {{ ref('fct_team_game') }}
    where is_completed and not is_preseason
),

-- La racha actual es la "isla" de resultados iguales que empieza en el partido más reciente:
-- solo esas filas cumplen recency - row_number(por resultado) = 0.
islands as (
    select team_key, outcome,
           recency - row_number() over (partition by team_key, outcome order by recency) as island
    from played
),

current_streak as (
    select team_key, any_value(outcome) as streak_outcome, count(*) as streak_length
    from islands
    where island = 0
    group by team_key
),

summary as (
    select
        team_key,
        string_agg(outcome, '' order by start_time) filter (where recency <= 5) as last_5,
        count(*)                              as played,
        count(*) filter (where outcome = 'W') as wins,
        count(*) filter (where outcome = 'D') as draws,
        count(*) filter (where outcome = 'L') as losses,
        arg_min(event_id, recency)            as last_event_id
    from played
    group by team_key
),

live as (
    select team_key, arg_max(event_id, start_time) as live_event_id
    from {{ ref('fct_team_game') }}
    where status_state = 'in'
    group by team_key
),

upcoming as (
    select team_key, arg_min(event_id, start_time) as next_event_id
    from {{ ref('fct_team_game') }}
    where status_state = 'pre' and start_time > now()
    group by team_key
)

select
    t.team_key,
    t.sport,
    s.last_5,
    s.played,
    s.wins,
    s.draws,
    s.losses,
    c.streak_outcome,
    c.streak_length,
    s.last_event_id,
    l.live_event_id,
    u.next_event_id
from {{ ref('dim_team') }} t
left join summary s using (team_key)
left join current_streak c using (team_key)
left join live l using (team_key)
left join upcoming u using (team_key)
