# Databricks notebook source
dbutils.widgets.text("catalog", "databricks_proyectobg")
dbutils.widgets.text("bronze_schema", "tpcds_bronze")
dbutils.widgets.text("silver_schema", "tpcds_silver")
dbutils.widgets.text("gold_schema", "tpcds_gold")

from pyspark.sql import functions as F

catalog = dbutils.widgets.get("catalog")
bronze = dbutils.widgets.get("bronze_schema")
silver = dbutils.widgets.get("silver_schema")
gold = dbutils.widgets.get("gold_schema")

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{gold}")

sales = spark.table(f"{catalog}.{silver}.store_sales_clean")
date_dim = spark.table(f"{catalog}.{bronze}.date_dim")
item = spark.table(f"{catalog}.{bronze}.item")
store = spark.table(f"{catalog}.{bronze}.store")

sales_by_year_category = (
    sales
    .join(date_dim, sales.ss_sold_date_sk == F.col("d_date_sk"), "left")
    .join(item, sales.ss_item_sk == F.col("i_item_sk"), "left")
    .groupBy(F.col("d_year").alias("year"), F.col("i_category").alias("category"))
    .agg(
        F.count("*").alias("sales_rows"),
        F.sum("ss_quantity").alias("units_sold"),
        F.round(F.sum("ss_sales_price"), 2).alias("gross_sales"),
        F.round(F.sum("ss_net_profit"), 2).alias("net_profit"),
    )
)

sales_by_store = (
    sales
    .join(store, sales.ss_store_sk == F.col("s_store_sk"), "left")
    .groupBy("s_store_id", "s_store_name", "s_state")
    .agg(
        F.count("*").alias("sales_rows"),
        F.sum("ss_quantity").alias("units_sold"),
        F.round(F.sum("ss_sales_price"), 2).alias("gross_sales"),
        F.round(F.sum("ss_net_profit"), 2).alias("net_profit"),
    )
)

sales_by_year_category.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{gold}.sales_by_year_category")
sales_by_store.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{gold}.sales_by_store")
