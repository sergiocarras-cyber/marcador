-- Clasificación actual por liga y grupo.
select
    s.sport || '-' || s.team_id as team_key,
    s.league_key,
    l.league_name,
    case s.group_name
        when 'Eastern Conference' then 'Conferencia Este'
        when 'Western Conference' then 'Conferencia Oeste'
        when 'American Football Conference' then 'AFC'
        when 'National Football Conference' then 'NFC'
        when 'American League' then 'Liga Americana'
        when 'National League' then 'Liga Nacional'
        else s.group_name
    end as group_name,
    -- Fútbol publica 'rank'; NBA/NFL/MLB, la posición en su conferencia como 'playoffSeed'
    cast(coalesce(s.rank, s.playoffSeed) as integer) as position,
    cast(s.gamesPlayed as integer)   as played,
    cast(s.wins as integer)          as wins,
    cast(s.ties as integer)          as draws,
    cast(s.losses as integer)        as losses,
    cast(s.points as integer)        as points,
    cast(s.pointsFor as integer)     as points_for,
    cast(s.pointsAgainst as integer) as points_against,
    s.overall_record,
    s.qualification_note,
    s.ingested_at
from {{ ref('stg_espn__standings') }} s
left join {{ ref('leagues') }} l using (league_key)
