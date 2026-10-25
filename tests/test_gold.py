from datetime import date, datetime

from src.transforms.gold import daily_summary, daily_zone_stats

SCHEMA = (
    "tpep_pickup_datetime timestamp, pickup_zip int, trip_distance double, "
    "fare_amount double, trip_duration_min double"
)


def make_silver(spark):
    rows = [
        (datetime(2016, 2, 1, 8, 0), 10001, 2.0, 10.0, 10.0),
        (datetime(2016, 2, 1, 9, 0), 10001, 4.0, 20.0, 20.0),
        (datetime(2016, 2, 1, 9, 30), 10002, 1.0, 6.0, 5.0),
        (datetime(2016, 2, 2, 8, 0), 10001, 3.0, 12.0, 15.0),
    ]
    return spark.createDataFrame(rows, SCHEMA)


def test_daily_zone_stats_counts_and_averages(spark):
    out = {
        (r["pickup_date"], r["pickup_zip"]): r
        for r in daily_zone_stats(make_silver(spark)).collect()
    }
    assert len(out) == 3
    row = out[(date(2016, 2, 1), 10001)]
    assert row["trips"] == 2
    assert row["total_fare"] == 30.0
    assert row["avg_fare"] == 15.0
    assert row["avg_distance"] == 3.0
    assert row["avg_duration_min"] == 15.0


def test_daily_summary_totals(spark):
    out = {r["pickup_date"]: r for r in daily_summary(make_silver(spark)).collect()}
    day1 = out[date(2016, 2, 1)]
    assert day1["trips"] == 3
    assert day1["total_fare"] == 36.0
    assert day1["active_pickup_zips"] == 2
    assert out[date(2016, 2, 2)]["trips"] == 1
