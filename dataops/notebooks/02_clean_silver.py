# Databricks notebook source
dbutils.widgets.text("run_id", "")
dbutils.widgets.text("catalog", "databricks_proyectobg")
dbutils.widgets.text("bronze_schema", "tpcds_bronze")
dbutils.widgets.text("silver_schema", "tpcds_silver")

from pyspark.sql import functions as F

def safe_run_id():
    widget_value = dbutils.widgets.get("run_id")
    if widget_value:
        return widget_value
    try:
        return str(spark.conf.get("spark.databricks.job.runId"))
    except Exception:
        return "manual-run"


run_id = safe_run_id()
catalog = dbutils.widgets.get("catalog")
bronze = dbutils.widgets.get("bronze_schema")
silver = dbutils.widgets.get("silver_schema")

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{silver}")

store_sales = spark.table(f"{catalog}.{bronze}.store_sales")
date_dim = spark.table(f"{catalog}.{bronze}.date_dim").select("d_date_sk").distinct()
item = spark.table(f"{catalog}.{bronze}.item").select("i_item_sk").distinct()
store = spark.table(f"{catalog}.{bronze}.store").select("s_store_sk").distinct()

typed_sales = (
    store_sales
    .withColumn("ss_sold_date_sk", F.col("ss_sold_date_sk").cast("long"))
    .withColumn("ss_item_sk", F.col("ss_item_sk").cast("long"))
    .withColumn("ss_store_sk", F.col("ss_store_sk").cast("long"))
    .withColumn("ss_ticket_number", F.col("ss_ticket_number").cast("long"))
    .withColumn("ss_quantity", F.col("ss_quantity").cast("int"))
    .withColumn("ss_sales_price", F.col("ss_sales_price").cast("double"))
    .withColumn("ss_net_profit", F.col("ss_net_profit").cast("double"))
    .withColumn("run_id", F.lit(run_id))
    .withColumn("processed_ts", F.current_timestamp())
)

enriched = (
    typed_sales
    .join(date_dim.withColumn("valid_date", F.lit(True)), typed_sales.ss_sold_date_sk == date_dim.d_date_sk, "left")
    .join(item.withColumn("valid_item", F.lit(True)), typed_sales.ss_item_sk == item.i_item_sk, "left")
    .join(store.withColumn("valid_store", F.lit(True)), typed_sales.ss_store_sk == store.s_store_sk, "left")
)

quarantine = (
    enriched
    .withColumn(
        "rule_code",
        F.when(F.col("ss_sold_date_sk").isNull(), F.lit("sold_date_not_null"))
        .when(F.col("ss_item_sk").isNull(), F.lit("item_not_null"))
        .when(F.col("ss_store_sk").isNull(), F.lit("store_not_null"))
        .when(F.col("ss_quantity") <= 0, F.lit("quantity_positive"))
        .when(F.col("ss_sales_price") < 0, F.lit("sales_price_non_negative"))
        .when(
            F.col("valid_date").isNull() | F.col("valid_item").isNull() | F.col("valid_store").isNull(),
            F.lit("referential_integrity_item_store_date"),
        )
    )
    .where(F.col("rule_code").isNotNull())
    .withColumn("reason", F.concat(F.lit("Failed quality rule: "), F.col("rule_code")))
    .select(
        "run_id",
        "rule_code",
        "reason",
        "ss_ticket_number",
        "ss_item_sk",
        "ss_store_sk",
        "ss_sold_date_sk",
        "ss_quantity",
        "ss_sales_price",
        "processed_ts",
    )
)

clean = (
    enriched
    .join(quarantine.select("ss_ticket_number", "ss_item_sk"), ["ss_ticket_number", "ss_item_sk"], "left_anti")
    .drop("d_date_sk", "i_item_sk", "s_store_sk", "valid_date", "valid_item", "valid_store")
    .dropDuplicates(["ss_ticket_number", "ss_item_sk"])
)

clean.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{silver}.store_sales_clean")
quarantine.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{silver}.quarantine_store_sales")
