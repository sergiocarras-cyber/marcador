{# ESPN mezcla "2026-11-08T20:30Z" (sin segundos) con ISO completo: normalizamos antes de convertir #}
{% macro parse_ts(expr) -%}
  try_cast(regexp_replace({{ expr }}, 'T(\d\d:\d\d)Z$', 'T\1:00Z') as timestamptz)
{%- endmacro %}
