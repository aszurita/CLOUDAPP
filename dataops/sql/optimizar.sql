-- Después de crear las Gold, ejecuta:

OPTIMIZE databricks_proyectobg.tpcds_bronze.store_sales;
OPTIMIZE databricks_proyectobg.tpcds_gold.kpi_ventas_categoria_anual;
OPTIMIZE databricks_proyectobg.tpcds_gold.kpi_ventas_tienda_anual;

-- Si te permite ZORDER, usa:

OPTIMIZE databricks_proyectobg.tpcds_bronze.store_sales
ZORDER BY (ss_sold_date_sk, ss_item_sk);