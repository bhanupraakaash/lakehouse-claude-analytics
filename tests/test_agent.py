import json
import os
from types import SimpleNamespace

from src.agent.ask import DuckDBBackend, answer, extract_sql
from src.agent.evaluate import normalize, run_eval, summarize

HERE = os.path.dirname(__file__)
QUESTIONS = os.path.join(HERE, "..", "eval", "questions.json")
HELDOUT = os.path.join(HERE, "..", "eval", "questions_heldout.json")


class FakeClient:
    """Mimics anthropic.Anthropic().messages.create, returning a fixed reply."""

    def __init__(self, reply):
        self.reply = reply
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.reply)],
            usage=SimpleNamespace(input_tokens=100, output_tokens=20),
        )


def write_data(tmp_path):
    (tmp_path / "gold_daily_summary.csv").write_text(
        "pickup_date,trips,total_fare,avg_fare,active_pickup_zips\n"
        "2016-02-01,3,36.0,12.0,2\n2016-02-02,1,12.0,12.0,1\n"
    )
    (tmp_path / "gold_daily_zone_stats.csv").write_text(
        "pickup_date,pickup_zip,trips,total_fare,avg_fare,avg_distance,avg_duration_min\n"
        "2016-02-01,10001,2,30.0,15.0,3.0,15.0\n2016-02-01,10002,1,6.0,6.0,1.0,5.0\n"
        "2016-02-02,10001,1,12.0,12.0,3.0,15.0\n"
    )
    return DuckDBBackend(str(tmp_path))


def test_extract_sql_handles_markdown_fence():
    assert extract_sql("```sql\nSELECT 1\n```") == "SELECT 1"
    assert extract_sql("SELECT 2") == "SELECT 2"


def test_answer_runs_valid_sql(tmp_path):
    backend = write_data(tmp_path)
    out = answer(FakeClient("SELECT SUM(trips) FROM gold_daily_summary"), backend, "total trips?")
    assert out["error"] is None
    assert out["rows"] == [(4,)]
    assert out["usage"] == {"input_tokens": 100, "output_tokens": 20}


def test_answer_blocks_unsafe_sql(tmp_path):
    backend = write_data(tmp_path)
    out = answer(FakeClient("DROP TABLE gold_daily_summary"), backend, "delete everything")
    assert out["rows"] == []
    assert "UnsafeSQLError" in out["error"]


def test_reference_queries_all_run_and_pass_the_guard(tmp_path):
    from src.agent.sql_guard import validate_sql

    backend = write_data(tmp_path)
    with open(QUESTIONS) as f:
        questions = json.load(f)
    assert len(questions) == 15
    for item in questions:
        backend.run(validate_sql(item["reference_sql"]))


def test_heldout_reference_queries_run_and_pass_the_guard(tmp_path):
    from src.agent.sql_guard import validate_sql

    backend = write_data(tmp_path)
    with open(HELDOUT) as f:
        questions = json.load(f)
    assert len(questions) == 9
    for item in questions:
        backend.run(validate_sql(item["reference_sql"]))


def test_prompt_asks_for_only_needed_columns():
    from src.agent.ask import SCHEMA_PROMPT

    assert "only the columns needed" in SCHEMA_PROMPT


def test_eval_scores_matching_and_mismatching_answers(tmp_path):
    backend = write_data(tmp_path)
    questions = [
        {"question": "total trips?", "reference_sql": "SELECT SUM(trips) FROM gold_daily_summary"},
        {"question": "total trips again?", "reference_sql": "SELECT SUM(trips) FROM gold_daily_summary"},
    ]
    good = summarize(run_eval(FakeClient("SELECT SUM(trips) FROM gold_daily_summary"), backend, questions))
    bad = summarize(run_eval(FakeClient("SELECT COUNT(*) FROM gold_daily_summary"), backend, questions))
    assert good["accuracy_pct"] == 100.0
    assert bad["accuracy_pct"] == 0.0


def test_normalize_is_order_insensitive_and_rounds():
    assert normalize([(2, 1.234), (1, 2.0)]) == normalize([(1, 2.0), (2, 1.2349)])
