-- Alineaciones de fútbol por partido.
select
    event_id,
    'futbol-' || team_id as team_key,
    formation,
    player_id,
    player_name,
    player_short_name,
    jersey,
    position,
    is_starter,
    subbed_in,
    subbed_out,
    formation_place
from {{ ref('stg_espn__lineups') }}
