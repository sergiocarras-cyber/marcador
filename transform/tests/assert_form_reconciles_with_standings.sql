-- Conciliación entre fuentes: las victorias y derrotas que calculamos a partir de los
-- partidos deben coincidir con la clasificación oficial (NBA y NFL, temporada regular).
-- Aviso y no error: la clasificación puede ir unas horas por detrás de los marcadores.
{{ config(severity = 'warn') }}
select f.team_key, f.wins, s.wins as official_wins, f.losses, s.losses as official_losses
from {{ ref('team_form') }} f
join {{ ref('standings') }} s using (team_key)
where f.sport in ('nba', 'nfl')
  and (f.wins <> s.wins or f.losses <> s.losses)
