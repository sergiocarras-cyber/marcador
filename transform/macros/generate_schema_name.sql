{# Usa el nombre de esquema tal cual (silver, gold, ref) en lugar de prefijarlo con el del perfil #}
{% macro generate_schema_name(custom_schema_name, node) -%}
  {{ custom_schema_name if custom_schema_name else target.schema }}
{%- endmacro %}
