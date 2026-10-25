"""Execution-accuracy evaluation for the text-to-SQL agent.

For each question, run Claude's SQL and the hand-written reference SQL on the same data
and compare the result sets (order-insensitive, numbers rounded).

Usage:
    python -m src.agent.evaluate --data-dir data/sample
"""
import argparse
import json

from src.agent.ask import DEFAULT_MODEL, DuckDBBackend, answer
from src.agent.sql_guard import validate_sql


def normalize(rows):
    """Order-insensitive, rounding-tolerant form of a result set."""
    def norm(value):
        if isinstance(value, float):
            return round(value, 2)
        try:
            from decimal import Decimal

            if isinstance(value, Decimal):
                return round(float(value), 2)
        except ImportError:  # pragma: no cover
            pass
        return str(value) if value is not None else None

    return sorted((tuple(norm(v) for v in row) for row in rows), key=repr)


def run_eval(client, backend, questions, model=DEFAULT_MODEL):
    results = []
    for item in questions:
        _, expected_rows = backend.run(validate_sql(item["reference_sql"]))
        out = answer(client, backend, item["question"], model)
        correct = out["error"] is None and normalize(out["rows"]) == normalize(expected_rows)
        results.append({**out, "correct": correct, "reference_sql": item["reference_sql"]})
    return results


def summarize(results):
    n = len(results)
    correct = sum(r["correct"] for r in results)
    errors = sum(1 for r in results if r["error"])
    in_tok = sum(r.get("usage", {}).get("input_tokens", 0) for r in results)
    out_tok = sum(r.get("usage", {}).get("output_tokens", 0) for r in results)
    return {
        "questions": n,
        "correct": correct,
        "accuracy_pct": round(100 * correct / n, 1) if n else 0.0,
        "errors": errors,
        "avg_latency_s": round(sum(r["latency_s"] for r in results) / n, 2) if n else 0.0,
        "total_input_tokens": in_tok,
        "total_output_tokens": out_tok,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/sample")
    parser.add_argument("--questions", default="eval/questions.json")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--out", default="eval/results.json")
    args = parser.parse_args()

    import anthropic

    with open(args.questions) as f:
        questions = json.load(f)
    results = run_eval(anthropic.Anthropic(), DuckDBBackend(args.data_dir), questions, args.model)
    summary = summarize(results)
    with open(args.out, "w") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2, default=str)
    for r in results:
        print("PASS" if r["correct"] else "FAIL", "|", r["question"])
        if not r["correct"]:
            print("   generated:", r["sql"], "|", r["error"])
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
