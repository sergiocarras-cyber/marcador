-- Estadísticas de equipo por partido que enseña la app: solo las del seed stat_labels,
-- con etiqueta en español y el valor normalizado para comparar (porcentajes en 0-100).
select
    b.event_id,
    b.sport || '-' || b.team_id                         as team_key,
    b.stat_name,
    l.label_es,
    l.sort_order,
    l.format,
    b.display_value,
    case l.format
        when 'ratio' then round(b.value * 100)          -- 0.8 → 80
        else b.value
    end                                                 as value
from {{ ref('stg_espn__team_box') }} b
join {{ ref('stat_labels') }} l on l.sport = b.sport and l.stat_name = b.stat_name
