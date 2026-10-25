# Lakehouse Claude Analytics

![CI](https://github.com/<your-username>/lakehouse-claude-analytics/actions/workflows/ci.yml/badge.svg)

A medallion-architecture data pipeline on Databricks Free Edition, with a Claude-powered text-to-SQL assistant on top of the Gold tables. Transform logic is unit tested, and linting and tests run on GitHub Actions for every push.

> Status: pipeline, tests, CI, dashboard, text-to-SQL assistant and evaluation are built. Items marked TODO are measured values still to be filled in from Databricks runs.

## Architecture

![Architecture](docs/architecture.png)

```
samples.nyctaxi.trips
        |
        v
  Bronze (raw Delta + ingestion metadata)
        |
        v
  Silver (typed, deduplicated, validated)  --->  Quarantine (rejected rows + reason)
        |
        v
  Gold (daily aggregates)
        |
        +--> Databricks SQL dashboard
        |
        +--> Claude text-to-SQL assistant (read-only, guarded)
```

## Tech stack

- Databricks Free Edition (serverless), PySpark, Delta Lake
- Claude API (Anthropic Python SDK) for text-to-SQL
- DuckDB for running the assistant locally on exported Gold tables
- pytest and ruff for tests and linting
- GitHub Actions for CI

## Dataset

Databricks built-in sample data: `samples.nyctaxi.trips` (NYC taxi trips).

- Rows: 21,932 (the Bronze row count, a straight copy of the source)
- Columns used: `tpep_pickup_datetime`, `tpep_dropoff_datetime`, `pickup_zip`, `dropoff_zip`, `trip_distance`, `fare_amount`
- Gold tables as exported for the assistant: `gold_daily_summary` has 60 rows (60 days) and `gold_daily_zone_stats` has 3,271 rows (one per pickup zip per day)
- Source: Databricks sample datasets. Check the Databricks documentation for the dataset's terms before redistributing any data.

## Project structure

```
.
├── src/
│   ├── transforms/
│   │   ├── silver.py          # cleaning and data quality rules
│   │   └── gold.py            # daily aggregates
│   └── agent/
│       ├── ask.py             # Claude text-to-SQL assistant
│       ├── sql_guard.py       # read-only SQL validation
│       └── evaluate.py        # execution-accuracy evaluation
├── notebooks/
│   ├── 01_bronze.py
│   ├── 02_silver.py
│   └── 03_gold.py
├── tests/                     # pytest unit tests
├── eval/
│   ├── questions.json            # 15 evaluation questions with reference SQL
│   ├── questions_heldout.json    # 9 held-out questions, written before the prompt fix
│   ├── results_baseline.json     # run 1 on questions.json (before the prompt fix)
│   ├── results.json              # run 2 on questions.json (after the prompt fix)
│   └── results_heldout.json      # run on the held-out set (after the prompt fix)
├── data/sample/               # exported Gold tables (CSV) for local runs
├── docs/                      # architecture diagram, dashboard screenshot
├── .github/workflows/ci.yml   # lint and tests on every push
├── .env.example
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Pipeline layers

All tables are created in `workspace.lakehouse_demo`.

| Layer | What it does | Table(s) |
|-------|--------------|----------|
| Bronze | Copies the raw source data into Delta unchanged and adds `_ingested_at` and `_source_table` | `bronze_trips` |
| Silver | Casts types, removes duplicates, derives trip duration, applies data quality rules | `silver_trips`, `quarantine_trips` |
| Gold | Daily aggregates for dashboards and the assistant | `gold_daily_zone_stats`, `gold_daily_summary` |

Gold tables:

- `gold_daily_zone_stats`: trips, total fare, average fare, average distance and average duration per pickup zip per day
- `gold_daily_summary`: trips, total fare, average fare and active pickup zips per day

### Data quality rules

Rows that fail a rule are written to `quarantine_trips` with the first failing rule in `_reject_reason`. Thresholds are defined in `src/transforms/silver.py`.

| Rule | Rejects when | Rows rejected |
|------|--------------|---------------|
| `null_pickup_time` | pickup time is null | 0 |
| `null_dropoff_time` | dropoff time is null | 0 |
| `dropoff_not_after_pickup` | dropoff is not after pickup | 1 |
| `non_positive_distance` | distance is null or <= 0 | 75 |
| `distance_too_large` | distance > 200 miles | 0 |
| `non_positive_fare` | fare is null or <= 0 | 9 |
| `fare_too_large` | fare > $1000 | 0 |
| `duration_too_long` | duration > 360 minutes | 32 |

Each rejected row is counted once, under the first rule it fails, in the order listed above. Rows rejected in total: 117.

Row counts from the last run: Bronze 21,932, Silver 21,815, Quarantine 117 (0.53% of rows), removed as duplicates 0. Silver plus Quarantine equals Bronze.

Reconciliation: the sum of daily trips in `gold_daily_summary` (21,815) equals the row count of `silver_trips` (21,815); the check in `03_gold.py` prints `Match: True`.

The thresholds are judgment calls. On this dataset the upper limits for distance (200 miles) and fare ($1000) rejected no rows, so they were not binding. The 360-minute duration limit rejected 32 rows, and zero-distance trips account for most rejections (75 of 117).

## Dashboard

![Dashboard](docs/dashboard.png)

A Databricks SQL dashboard on the Gold tables: trips per day, top 10 pickup zips by trips, and total trips.

## How to run

### 1. Pipeline on Databricks

1. Sign up for Databricks Free Edition.
2. Create a Git folder linked to this repository (Workspace > Create > Git folder).
3. Open each notebook in `notebooks/`, select **Serverless** compute, and run them in order: `01_bronze.py`, `02_silver.py`, `03_gold.py`.
4. If your default catalog is not named `workspace`, change `CATALOG` at the top of each notebook.

### 2. Tests and lint locally

Requires Python 3.10+ and Java (PySpark needs it). On Windows:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
ruff check .
pytest
```

On macOS or Linux, activate with `source .venv/bin/activate`. The same commands run in CI.

## Claude text-to-SQL assistant

The assistant takes a plain-English question and sends it to Claude together with a description of the two Gold tables. Claude returns one SQL query. The query is validated by `sql_guard.py` (single read-only `SELECT`, Gold tables only) and then executed. Your data rows are never sent to Claude; only the question and the schema description are.

### Setup

1. Export the Gold tables from Databricks as CSV and save them as:
   - `data/sample/gold_daily_summary.csv`
   - `data/sample/gold_daily_zone_stats.csv`
2. Create an API key in the Claude Console (console.anthropic.com).
3. Copy `.env.example` to `.env` in the repo root and set your key. `.env` is git-ignored; never commit it.

   ```
   ANTHROPIC_API_KEY=your-key-here
   ```

### Ask a question

Run from the repo root:

```
python -m src.agent.ask "Which pickup zip had the most trips overall?"
```

The default model is `claude-sonnet-5-5`. Override it with the `ANTHROPIC_MODEL` environment variable or the `--model` flag.

### Safety

The SQL guard blocks multiple statements, write and DDL keywords, and any table other than the two Gold tables. It is a safety net, not a security boundary. For real deployments, run queries with read-only credentials limited to the Gold tables.

### Evaluation

Two question sets live in `eval/`:

- `questions.json`: 15 questions, each with a hand-written reference query.
- `questions_heldout.json`: 9 further questions, written before the prompt was changed.

For each question the evaluator runs Claude's SQL and the reference SQL on the same data and compares the full result sets (order-insensitive, numbers rounded to 2 decimals). An extra column therefore counts as a miss. Each set includes a deliberately unanswerable question, to check that the assistant declines properly.

```
python -m src.agent.evaluate
python -m src.agent.evaluate --questions eval/questions_heldout.json --out eval/results_heldout.json
```

Results (25 Oct 2026, model: `claude-sonnet-5-5`):

| Run | Questions | Correct | Accuracy | Errors | Avg latency | Input / output tokens |
|-----|-----------|---------|----------|--------|-------------|-----------------------|
| Baseline, `questions.json` | 15 | 9 | 60.0% | 0 | 1.25 s | 5,714 / 826 |
| After prompt change, `questions.json` | 15 | 15 | 100.0% | 0 | 1.24 s | 6,929 / 868 |
| After prompt change, held-out | 9 | 9 | 100.0% | 0 | 1.22 s | 4,203 / 437 |

What happened:

- The baseline's six failures all had the same cause. Claude's SQL was logically correct but returned extra columns (for example `pickup_date, trips` where only `pickup_date` was asked for), which the strict comparison counts as wrong.
- The fix was one rule added to the system prompt in `src/agent/ask.py`: return only the columns needed to answer the question, unless extra columns are requested. The scoring was not loosened.
- The prompt was changed after seeing the baseline failures, so the 100% on `questions.json` is not independent evidence. The held-out set is the fairer number. It includes a question that needs two columns, to check the rule does not over-trim.
- Each set was run once. TODO: rerun a few times to check stability and note any variation.
- Cost: TODO, compute from the token counts above and the current per-token prices for the model.

## Limitations

- Databricks Free Edition has limited compute and restricted outbound network access. TODO: record whether the Claude API was reachable from Databricks. The assistant here runs locally on exported CSVs.
- The dataset is small and static; there is no streaming ingestion.
- The evaluation sets are small (15 and 9 questions), were written by the project author, and consist mostly of direct single-aggregate questions, so accuracy numbers are indicative, not a benchmark. Results are from single runs.
- Data quality thresholds are heuristics chosen for this dataset.
- TODO: add anything else you found while building.

## Possible next steps

- Incremental processing with Auto Loader
- Databricks Asset Bundles for deployment
- A larger and harder evaluation set (ambiguous wording, joins across the two tables), repeated runs, and a comparison of prompt variants
- Running the assistant inside Databricks if the API is reachable

## License

TODO: choose a license (MIT is common) and add a `LICENSE` file.
