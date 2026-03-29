{% macro z_score(value, mean, stddev) %}
    CASE WHEN {{ stddev }} > 0 THEN ({{ value }} - {{ mean }}) / {{ stddev }} ELSE 0 END
{% endmacro %}
