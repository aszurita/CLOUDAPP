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

bronze_rows = spark.table(f"{catalog}.{bronze}.store_sales").count()
silver_rows = spark.table(f"{catalog}.{silver}.store_sales_clean").count()
gold_rows = spark.table(f"{catalog}.{gold}.sales_by_year_category").count()
quarantine = spark.table(f"{catalog}.{silver}.quarantine_store_sales")
quarantine_rows = quarantine.count()
quality_score = round((silver_rows / bronze_rows) * 100, 2) if bronze_rows else 0

failed_rules = [
    row.asDict()
    for row in (
        quarantine
        .groupBy("rule_code")
        .agg(F.count("*").alias("failed_rows"))
        .orderBy(F.desc("failed_rows"))
        .collect()
    )
]

def safe_task_value(key, value):
    try:
        dbutils.jobs.taskValues.set(key=key, value=value)
    except Exception:
        pass


safe_task_value("bronze_rows", bronze_rows)
safe_task_value("silver_rows", silver_rows)
safe_task_value("gold_rows", gold_rows)
safe_task_value("quarantine_rows", quarantine_rows)
safe_task_value("quality_score", quality_score)
safe_task_value("failed_rules", str(failed_rules))

display(
    spark.createDataFrame(
        [(bronze_rows, silver_rows, gold_rows, quality_score, quarantine_rows)],
        ["bronze_rows", "silver_rows", "gold_rows", "quality_score", "quarantine_rows"],
    )
)
