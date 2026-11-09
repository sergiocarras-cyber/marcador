-- Fórmula 1: resultados por sesión y piloto, con la etiqueta de sesión en español.
select
    season,
    grand_prix_id,
    grand_prix_name,
    circuit,
    session_id,
    session_type,
    case session_type
        when 'FP1' then 'Libres 1'
        when 'FP2' then 'Libres 2'
        when 'FP3' then 'Libres 3'
        when 'Qual' then 'Clasificación'
        when 'Race' then 'Carrera'
        when 'Sprint' then 'Sprint'
        when 'SS' then 'Clasificación sprint'
        when 'SQ' then 'Clasificación sprint'
        else session_type
    end as session_label,
    session_start,
    status_state,
    driver_id,
    driver_name,
    driver_short_name,
    coalesce(c.country_es, f.driver_country) as driver_country,
    driver_flag,
    position,
    is_winner
from {{ ref('stg_espn__f1_sessions') }} f
left join {{ ref('countries') }} c on c.country_en = f.driver_country
