CREATE OR REPLACE TABLE databricks_proyectobg.tpcds_gold.kpi_ventas_categoria_anual AS
SELECT
    d.d_year AS anio,
    i.i_category AS categoria,
    COUNT(*) AS cantidad_transacciones,
    SUM(CAST(ss.ss_quantity AS INT)) AS unidades_vendidas,
    ROUND(SUM(CAST(ss.ss_sales_price AS DOUBLE)), 2) AS ventas_totales,
    ROUND(SUM(CAST(ss.ss_net_profit AS DOUBLE)), 2) AS utilidad_neta
FROM databricks_proyectobg.tpcds_bronze.store_sales ss
JOIN databricks_proyectobg.tpcds_bronze.date_dim d
    ON ss.ss_sold_date_sk = d.d_date_sk
JOIN databricks_proyectobg.tpcds_bronze.item i
    ON ss.ss_item_sk = i.i_item_sk
GROUP BY
    d.d_year,
    i.i_category;


-- Crea otra Gold por tienda

CREATE OR REPLACE TABLE databricks_proyectobg.tpcds_gold.kpi_ventas_tienda_anual AS
SELECT
    d.d_year AS anio,
    s.s_store_name AS tienda,
    s.s_city AS ciudad,
    s.s_state AS estado,
    COUNT(*) AS cantidad_transacciones,
    SUM(CAST(ss.ss_quantity AS INT)) AS unidades_vendidas,
    ROUND(SUM(CAST(ss.ss_sales_price AS DOUBLE)), 2) AS ventas_totales,
    ROUND(SUM(CAST(ss.ss_net_profit AS DOUBLE)), 2) AS utilidad_neta
FROM databricks_proyectobg.tpcds_bronze.store_sales ss
JOIN databricks_proyectobg.tpcds_bronze.date_dim d
    ON ss.ss_sold_date_sk = d.d_date_sk
JOIN databricks_proyectobg.tpcds_bronze.store s
    ON ss.ss_store_sk = s.s_store_sk
GROUP BY
    d.d_year,
    s.s_store_name,
    s.s_city,
    s.s_state;