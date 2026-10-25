# Databricks notebook source
# MAGIC %md
# MAGIC # 02 - Silver layer
# MAGIC Cleans Bronze data, applies data quality rules, and writes valid rows to Silver
# MAGIC and rejected rows (with a reason) to a quarantine table.

# COMMAND ----------

import os
import sys

# Make the repo root importable (this notebook lives in <repo>/notebooks).
# If the import below fails, print os.getcwd() and adjust the path.
sys.path.append(os.path.abspath(".."))

from pyspark.sql import functions as F
from src.transforms.silver import standardize, split_valid_rejected

# COMMAND ----------

CATALOG = "workspace"
SCHEMA = "lakehouse_demo"
BRONZE_TABLE = f"{CATALOG}.{SCHEMA}.bronze_trips"
SILVER_TABLE = f"{CATALOG}.{SCHEMA}.silver_trips"
QUARANTINE_TABLE = f"{CATALOG}.{SCHEMA}.quarantine_trips"

# COMMAND ----------

bronze_df = spark.table(BRONZE_TABLE)
standardized_df = standardize(bronze_df)
valid_df, rejected_df = split_valid_rejected(standardized_df)

# COMMAND ----------

(
    valid_df.withColumn("_silver_at", F.current_timestamp())
    .write.format("delta").mode("overwrite").saveAsTable(SILVER_TABLE)
)

(
    rejected_df.withColumn("_silver_at", F.current_timestamp())
    .write.format("delta").mode("overwrite").saveAsTable(QUARANTINE_TABLE)
)

# COMMAND ----------

# Record these numbers in the README (data quality section).
bronze_n = bronze_df.count()
silver_n = spark.table(SILVER_TABLE).count()
quarantine_n = spark.table(QUARANTINE_TABLE).count()
print(f"Bronze: {bronze_n} | Silver: {silver_n} | Quarantine: {quarantine_n}")
print(f"Removed as duplicates: {bronze_n - silver_n - quarantine_n}")

display(
    spark.table(QUARANTINE_TABLE)
    .groupBy("_reject_reason").count().orderBy(F.desc("count"))
)
