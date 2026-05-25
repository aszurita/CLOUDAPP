# Databricks notebook source
dbutils.widgets.text("catalog", "databricks_proyectobg")
dbutils.widgets.text("bronze_schema", "tpcds_bronze")
dbutils.widgets.text("silver_schema", "tpcds_silver")
dbutils.widgets.text("gold_schema", "tpcds_gold")

catalog = dbutils.widgets.get("catalog")
bronze = dbutils.widgets.get("bronze_schema")
silver = dbutils.widgets.get("silver_schema")
gold = dbutils.widgets.get("gold_schema")

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{silver}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{gold}")

required_tables = ["store_sales", "date_dim", "item", "store"]
missing = []
for table_name in required_tables:
    full_name = f"{catalog}.{bronze}.{table_name}"
    if not spark.catalog.tableExists(full_name):
        missing.append(full_name)

if missing:
    raise ValueError(
        "Missing TPC-DS Bronze tables. Run your 01_generate_tpcds_data notebook first. "
        f"Missing: {', '.join(missing)}"
    )

bronze_counts = []
for table_name in required_tables:
    full_name = f"{catalog}.{bronze}.{table_name}"
    bronze_counts.append((table_name, spark.table(full_name).count(), full_name))

display(spark.createDataFrame(bronze_counts, ["table_name", "row_count", "full_name"]))
