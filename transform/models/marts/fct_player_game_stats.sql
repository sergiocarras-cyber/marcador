-- Hoja de jugador por partido (formato largo): NBA, NFL y MLB.
select
    event_id,
    sport || '-' || team_id as team_key,
    stat_group,
    player_id,
    player_name,
    player_short_name,
    headshot,
    jersey,
    position,
    is_starter,
    stat_key,
    stat_label,
    display_value,
    try_cast(display_value as double) as value
from {{ ref('stg_espn__player_box') }}
where not did_not_play
