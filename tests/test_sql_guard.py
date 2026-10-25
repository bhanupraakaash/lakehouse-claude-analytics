import pytest

from src.agent.sql_guard import UnsafeSQLError, validate_sql


def test_accepts_simple_select():
    sql = "SELECT SUM(trips) FROM gold_daily_summary"
    assert validate_sql(sql + ";") == sql


def test_accepts_cte_and_qualified_table():
    sql = (
        "WITH t AS (SELECT pickup_zip, SUM(trips) AS n FROM workspace.lakehouse_demo.gold_daily_zone_stats "
        "GROUP BY pickup_zip) SELECT * FROM t ORDER BY n DESC LIMIT 1"
    )
    assert validate_sql(sql).startswith("WITH t AS")


def test_accepts_join_of_allowed_tables():
    sql = (
        "SELECT a.pickup_date FROM gold_daily_summary a "
        "JOIN gold_daily_zone_stats b ON a.pickup_date = b.pickup_date"
    )
    assert validate_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE gold_daily_summary",
        "DELETE FROM gold_daily_summary",
        "INSERT INTO gold_daily_summary VALUES (1)",
        "UPDATE gold_daily_summary SET trips = 0",
        "SELECT 1; DROP TABLE gold_daily_summary",
        "SELECT * FROM silver_trips",
        "SELECT * FROM workspace.lakehouse_demo.bronze_trips",
        "SELECT * FROM gold_daily_summary INTO OUTFILE 'x'",
        "CREATE TABLE x AS SELECT * FROM gold_daily_summary",
        "",
        "   ",
        "EXPLAIN SELECT 1",
    ],
)
def test_rejects_unsafe_sql(sql):
    with pytest.raises(UnsafeSQLError):
        validate_sql(sql)


def test_comments_cannot_hide_a_second_statement():
    with pytest.raises(UnsafeSQLError):
        validate_sql("SELECT 1 FROM gold_daily_summary /* x */; DROP TABLE gold_daily_summary")


def test_keyword_inside_string_literal_is_allowed():
    assert validate_sql("SELECT 'drop table' AS result")
