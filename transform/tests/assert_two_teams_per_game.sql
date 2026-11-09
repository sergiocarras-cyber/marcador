-- Cada partido tiene exactamente un local y un visitante.
select event_id, count(*) as n, count(distinct home_away) as sides
from {{ ref('stg_espn__competitors') }}
group by event_id
having count(*) <> 2 or count(distinct home_away) <> 2
