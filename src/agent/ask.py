"""Claude text-to-SQL assistant over the Gold tables.

Usage (local, against exported CSVs):
    export ANTHROPIC_API_KEY=...
    python -m src.agent.ask "Which pickup zip had the most trips?" --data-dir data/sample

In a Databricks notebook, use SparkBackend(spark) instead of DuckDBBackend.
"""
import argparse
import os
import re
import time

from src.agent.sql_guard import validate_sql

try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv()  # so ANTHROPIC_MODEL in .env is honoured at import time
except ImportError:
    pass

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
MAX_ROWS = 100

SCHEMA_PROMPT = """You translate questions into a single read-only SQL query.

Tables (all columns listed):

gold_daily_zone_stats  -- one row per pickup_date and pickup_zip
  pickup_date DATE, pickup_zip INT, trips BIGINT, total_fare DOUBLE,
  avg_fare DOUBLE, avg_distance DOUBLE, avg_duration_min DOUBLE

gold_daily_summary  -- one row per pickup_date (all zips combined)
  pickup_date DATE, trips BIGINT, total_fare DOUBLE, avg_fare DOUBLE,
  active_pickup_zips BIGINT

Rules:
- Output exactly one SELECT statement and nothing else. No explanation, no markdown.
- Use only the tables and columns above. Never modify data.
- Return only the columns needed to answer the question. For a 'which X' question return just X,
  and for a 'how many' or 'what is the total' question return just that number.
  Include extra columns only when the question asks for them (for example 'show the trips for ...').
- Fares are in US dollars, distances in miles, durations in minutes.
- If the question cannot be answered from these tables, output: SELECT 'unanswerable' AS result
- Use standard SQL that works in both Spark SQL and DuckDB.
"""


def extract_sql(text: str) -> str:
    """Pull SQL out of a model reply, tolerating markdown fences."""
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return (fenced.group(1) if fenced else text).strip()


def generate_sql(client, question: str, model: str = DEFAULT_MODEL):
    """Ask Claude for SQL. Returns (sql, usage) where usage has input/output token counts."""
    response = client.messages.create(
        model=model,
        max_tokens=500,
        system=SCHEMA_PROMPT,
        messages=[{"role": "user", "content": question}],
    )
    text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
    usage = {
        "input_tokens": getattr(response.usage, "input_tokens", 0),
        "output_tokens": getattr(response.usage, "output_tokens", 0),
    }
    return extract_sql(text), usage


class DuckDBBackend:
    """Runs queries on CSV exports of the Gold tables (one CSV per table in data_dir)."""

    def __init__(self, data_dir: str):
        import duckdb

        self.con = duckdb.connect()
        for table in ("gold_daily_zone_stats", "gold_daily_summary"):
            path = os.path.join(data_dir, f"{table}.csv")
            self.con.execute(
                f"CREATE VIEW {table} AS SELECT * FROM read_csv_auto('{path}', header=true)"
            )

    def run(self, sql: str):
        cur = self.con.execute(sql)
        columns = [d[0] for d in cur.description]
        return columns, cur.fetchmany(MAX_ROWS)


class SparkBackend:
    """Runs queries on the Gold tables inside Databricks."""

    def __init__(self, spark, catalog: str = "workspace", schema: str = "lakehouse_demo"):
        self.spark = spark
        spark.sql(f"USE CATALOG {catalog}")
        spark.sql(f"USE SCHEMA {schema}")

    def run(self, sql: str):
        df = self.spark.sql(sql).limit(MAX_ROWS)
        return df.columns, [tuple(r) for r in df.collect()]


def answer(client, backend, question: str, model: str = DEFAULT_MODEL) -> dict:
    """Question in, dict out: sql, columns, rows, latency, token usage, or an error."""
    start = time.time()
    result = {"question": question, "sql": None, "columns": [], "rows": [], "error": None}
    try:
        sql, usage = generate_sql(client, question, model)
        result["usage"] = usage
        result["sql"] = validate_sql(sql)
        result["columns"], result["rows"] = backend.run(result["sql"])
    except Exception as exc:  # noqa: BLE001 - report any failure to the caller
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["latency_s"] = round(time.time() - start, 2)
    return result


def main():
    parser = argparse.ArgumentParser(description="Ask a question about the Gold tables.")
    parser.add_argument("question")
    parser.add_argument("--data-dir", default="data/sample")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    import anthropic
    from dotenv import load_dotenv

    load_dotenv()  # reads ANTHROPIC_API_KEY from a local .env file if present

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    out = answer(client, DuckDBBackend(args.data_dir), args.question, args.model)
    print("SQL:", out["sql"])
    if out["error"]:
        print("ERROR:", out["error"])
    else:
        print(out["columns"])
        for row in out["rows"]:
            print(row)
    print(f"({out['latency_s']}s)")


if __name__ == "__main__":
    main()
