# Databricks notebook source
# MAGIC %md
# MAGIC # 03 - Gold layer
# MAGIC Builds business-level aggregates from Silver for dashboards and the Claude text-to-SQL assistant.

# COMMAND ----------

import os
import sys

sys.path.append(os.path.abspath(".."))

from pyspark.sql import functions as F
from src.transforms.gold import daily_summary, daily_zone_stats

# COMMAND ----------

CATALOG = "workspace"
SCHEMA = "lakehouse_demo"
SILVER_TABLE = f"{CATALOG}.{SCHEMA}.silver_trips"
GOLD_ZONE_TABLE = f"{CATALOG}.{SCHEMA}.gold_daily_zone_stats"
GOLD_SUMMARY_TABLE = f"{CATALOG}.{SCHEMA}.gold_daily_summary"

# COMMAND ----------

silver_df = spark.table(SILVER_TABLE)

(
    daily_zone_stats(silver_df).withColumn("_gold_at", F.current_timestamp())
    .write.format("delta").mode("overwrite").saveAsTable(GOLD_ZONE_TABLE)
)

(
    daily_summary(silver_df).withColumn("_gold_at", F.current_timestamp())
    .write.format("delta").mode("overwrite").saveAsTable(GOLD_SUMMARY_TABLE)
)

# COMMAND ----------

# Record these in the README. Reconciliation: trips in Gold must equal rows in Silver.
silver_n = silver_df.count()
gold_trips = spark.table(GOLD_SUMMARY_TABLE).agg(F.sum("trips")).collect()[0][0]
print(f"Silver rows: {silver_n} | Sum of Gold daily trips: {gold_trips} | Match: {silver_n == gold_trips}")
display(spark.table(GOLD_SUMMARY_TABLE).orderBy("pickup_date"))
display(spark.table(GOLD_ZONE_TABLE).orderBy(F.desc("trips")).limit(10))
