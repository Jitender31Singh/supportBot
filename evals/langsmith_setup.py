"""Optional helper to create starter LangSmith datasets when LANGSMITH_API_KEY is configured."""
from __future__ import annotations
import json
import os
from pathlib import Path


def main() -> None:
    try:
        from langsmith import Client
    except ImportError as exc:
        raise SystemExit("Install requirements.txt before running LangSmith dataset setup") from exc
    if not os.getenv("LANGSMITH_API_KEY"):
        raise SystemExit("Set LANGSMITH_API_KEY in the environment first")
    client = Client()
    root = Path(__file__).parent
    for filename, dataset_name, input_key, output_key in [
        ("intent_cases.jsonl", "trackobit-intent-parser-v1", "input", "expected_intent"),
        ("fault_cases.jsonl", "trackobit-fault-classifier-v1", "input", "expected_category"),
    ]:
        try:
            dataset = client.create_dataset(dataset_name=dataset_name, description=f"Starter regression cases from {filename}")
        except Exception:
            # Dataset may already exist; do not silently rewrite existing examples.
            print(f"Dataset {dataset_name!r} may already exist; skipping it.")
            continue
        with (root / filename).open(encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                client.create_example(inputs=row[input_key], outputs={output_key: row[output_key]}, dataset_id=dataset.id)
        print(f"Created {dataset_name}")

if __name__ == "__main__":
    main()
