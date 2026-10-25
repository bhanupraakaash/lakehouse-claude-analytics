from datetime import datetime

from src.transforms.silver import (
    add_reject_reason,
    split_valid_rejected,
    standardize,
)

COLUMNS = [
    "tpep_pickup_datetime",
    "tpep_dropoff_datetime",
    "pickup_zip",
    "dropoff_zip",
    "trip_distance",
    "fare_amount",
]

PICKUP = datetime(2016, 2, 1, 10, 0, 0)
DROPOFF = datetime(2016, 2, 1, 10, 20, 0)


def make_df(spark, rows):
    return spark.createDataFrame(rows, COLUMNS)


def good_row(**overrides):
    row = {
        "tpep_pickup_datetime": PICKUP,
        "tpep_dropoff_datetime": DROPOFF,
        "pickup_zip": 10001,
        "dropoff_zip": 10002,
        "trip_distance": 2.5,
        "fare_amount": 12.0,
    }
    row.update(overrides)
    return tuple(row[c] for c in COLUMNS)


def reasons(spark, rows):
    df = add_reject_reason(standardize(make_df(spark, rows)))
    return [r["_reject_reason"] for r in df.collect()]


def test_standardize_removes_exact_duplicates(spark):
    df = make_df(spark, [good_row(), good_row()])
    assert standardize(df).count() == 1


def test_standardize_adds_duration_in_minutes(spark):
    out = standardize(make_df(spark, [good_row()])).collect()[0]
    assert out["trip_duration_min"] == 20.0


def test_valid_row_has_no_reject_reason(spark):
    assert reasons(spark, [good_row()]) == [None]


def test_dropoff_not_after_pickup(spark):
    assert reasons(spark, [good_row(tpep_dropoff_datetime=PICKUP)]) == ["dropoff_not_after_pickup"]


def test_non_positive_distance(spark):
    assert reasons(spark, [good_row(trip_distance=0.0)]) == ["non_positive_distance"]


def test_distance_too_large(spark):
    assert reasons(spark, [good_row(trip_distance=5000.0)]) == ["distance_too_large"]


def test_non_positive_fare(spark):
    assert reasons(spark, [good_row(fare_amount=-3.0)]) == ["non_positive_fare"]


def test_fare_too_large(spark):
    assert reasons(spark, [good_row(fare_amount=5000.0)]) == ["fare_too_large"]


def test_duration_too_long(spark):
    long_dropoff = datetime(2016, 2, 1, 20, 0, 0)  # 600 minutes
    assert reasons(spark, [good_row(tpep_dropoff_datetime=long_dropoff)]) == ["duration_too_long"]


def test_null_pickup_time(spark):
    schema_rows = [good_row(tpep_pickup_datetime=None)]
    df = spark.createDataFrame(
        schema_rows,
        "tpep_pickup_datetime timestamp, tpep_dropoff_datetime timestamp, "
        "pickup_zip int, dropoff_zip int, trip_distance double, fare_amount double",
    )
    out = add_reject_reason(standardize(df)).collect()
    assert [r["_reject_reason"] for r in out] == ["null_pickup_time"]


def test_split_separates_valid_and_rejected(spark):
    df = standardize(make_df(spark, [good_row(), good_row(pickup_zip=10003, fare_amount=-1.0)]))
    valid, rejected = split_valid_rejected(df)
    assert valid.count() == 1
    assert rejected.count() == 1
    assert "_reject_reason" not in valid.columns
    assert rejected.collect()[0]["_reject_reason"] == "non_positive_fare"
