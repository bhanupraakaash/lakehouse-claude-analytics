"""Silver-layer transforms for the NYC taxi data.

Pure PySpark functions with no Databricks-specific calls, so they can be unit tested.
"""
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

KEY_COLUMNS = [
    "tpep_pickup_datetime",
    "tpep_dropoff_datetime",
    "pickup_zip",
    "dropoff_zip",
    "trip_distance",
    "fare_amount",
]

# Thresholds are judgment calls: review them against your data and document them in the README.
MAX_TRIP_DISTANCE = 200.0
MAX_FARE = 1000.0
MAX_DURATION_MIN = 360.0


def standardize(df: DataFrame) -> DataFrame:
    """Cast types, drop exact duplicates on the key columns, add derived columns."""
    typed = (
        df
        .withColumn("tpep_pickup_datetime", F.col("tpep_pickup_datetime").cast("timestamp"))
        .withColumn("tpep_dropoff_datetime", F.col("tpep_dropoff_datetime").cast("timestamp"))
        .withColumn("trip_distance", F.col("trip_distance").cast("double"))
        .withColumn("fare_amount", F.col("fare_amount").cast("double"))
    )
    deduped = typed.dropDuplicates(KEY_COLUMNS)
    return deduped.withColumn(
        "trip_duration_min",
        (F.unix_timestamp("tpep_dropoff_datetime") - F.unix_timestamp("tpep_pickup_datetime")) / 60.0,
    )


def add_reject_reason(df: DataFrame) -> DataFrame:
    """Add _reject_reason: null for valid rows, otherwise the first failing rule."""
    reason = (
        F.when(F.col("tpep_pickup_datetime").isNull(), "null_pickup_time")
        .when(F.col("tpep_dropoff_datetime").isNull(), "null_dropoff_time")
        .when(F.col("tpep_dropoff_datetime") <= F.col("tpep_pickup_datetime"), "dropoff_not_after_pickup")
        .when(F.col("trip_distance").isNull() | (F.col("trip_distance") <= 0), "non_positive_distance")
        .when(F.col("trip_distance") > MAX_TRIP_DISTANCE, "distance_too_large")
        .when(F.col("fare_amount").isNull() | (F.col("fare_amount") <= 0), "non_positive_fare")
        .when(F.col("fare_amount") > MAX_FARE, "fare_too_large")
        .when(F.col("trip_duration_min") > MAX_DURATION_MIN, "duration_too_long")
    )
    return df.withColumn("_reject_reason", reason)


def split_valid_rejected(df: DataFrame):
    """Return (valid_df, rejected_df). Rejected rows keep their _reject_reason."""
    flagged = add_reject_reason(df)
    valid = flagged.filter(F.col("_reject_reason").isNull()).drop("_reject_reason")
    rejected = flagged.filter(F.col("_reject_reason").isNotNull())
    return valid, rejected
