# Databricks notebook source
# MAGIC %md
# MAGIC # 01 - Bronze layer
# MAGIC Loads the raw NYC taxi sample data into a Delta table, unchanged,
# MAGIC and adds ingestion metadata.

# COMMAND ----------

from pyspark.sql import functions as F

# Change CATALOG if your default catalog has a different name (check Catalog explorer).
CATALOG = "workspace"
SCHEMA = "lakehouse_demo"
SOURCE_TABLE = "samples.nyctaxi.trips"
BRONZE_TABLE = f"{CATALOG}.{SCHEMA}.bronze_trips"

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

# COMMAND ----------

raw_df = spark.table(SOURCE_TABLE)

bronze_df = (
    raw_df
    .withColumn("_ingested_at", F.current_timestamp())
    .withColumn("_source_table", F.lit(SOURCE_TABLE))
)

# COMMAND ----------

(
    bronze_df.write
    .format("delta")
    .mode("overwrite")
    .saveAsTable(BRONZE_TABLE)
)

# COMMAND ----------

# Sanity checks: record these numbers in the README.
print("Source rows:", raw_df.count())
print("Bronze rows:", spark.table(BRONZE_TABLE).count())
display(spark.table(BRONZE_TABLE).limit(10))
spark.table(BRONZE_TABLE).printSchema()
