{% macro rolling_mean(column, partition_by, order_by, window_size) %}
    AVG({{ column }}) OVER (
        PARTITION BY {{ partition_by }}
        ORDER BY {{ order_by }}
        ROWS BETWEEN {{ window_size - 1 }} PRECEDING AND CURRENT ROW
    )
{% endmacro %}

{% macro rolling_stddev(column, partition_by, order_by, window_size) %}
    STDDEV_SAMP({{ column }}) OVER (
        PARTITION BY {{ partition_by }}
        ORDER BY {{ order_by }}
        ROWS BETWEEN {{ window_size - 1 }} PRECEDING AND CURRENT ROW
    )
{% endmacro %}
