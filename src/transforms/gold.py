"""Gold-layer aggregates for the NYC taxi data.

Pure PySpark functions so they can be unit tested without Databricks.
"""
from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def daily_zone_stats(silver: DataFrame) -> DataFrame:
    """Trips and fare/distance/duration statistics per pickup zip per day."""
    return (
        silver
        .withColumn("pickup_date", F.to_date("tpep_pickup_datetime"))
        .groupBy("pickup_date", "pickup_zip")
        .agg(
            F.count("*").alias("trips"),
            F.round(F.sum("fare_amount"), 2).alias("total_fare"),
            F.round(F.avg("fare_amount"), 2).alias("avg_fare"),
            F.round(F.avg("trip_distance"), 2).alias("avg_distance"),
            F.round(F.avg("trip_duration_min"), 2).alias("avg_duration_min"),
        )
    )


def daily_summary(silver: DataFrame) -> DataFrame:
    """Network-wide totals per day."""
    return (
        silver
        .withColumn("pickup_date", F.to_date("tpep_pickup_datetime"))
        .groupBy("pickup_date")
        .agg(
            F.count("*").alias("trips"),
            F.round(F.sum("fare_amount"), 2).alias("total_fare"),
            F.round(F.avg("fare_amount"), 2).alias("avg_fare"),
            F.countDistinct("pickup_zip").alias("active_pickup_zips"),
        )
    )
