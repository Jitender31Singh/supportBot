"""Run starter intent and fault-category evaluations against the LangSmith datasets.

First run: python -m evals.langsmith_setup
Then:      python -m evals.langsmith_evaluate
"""
from __future__ import annotations
import os

from langsmith.evaluation import evaluate
from trackobit_assistant.config.settings import Settings
from trackobit_assistant.nodes.intent.intent_parser import _heuristic
from trackobit_assistant.services.fault_rules import classify_fault

settings = Settings()


def intent_target(inputs: dict) -> dict:
    state = dict(inputs)
    state["last_user_message"] = inputs.get("message", "")
    result = _heuristic(state, settings)
    return {"intent": result.intent.value, "confidence": result.confidence}


def fault_target(inputs: dict) -> dict:
    result = classify_fault(
        inputs.get("snapshot"), inputs.get("dashboard_evidence"),
        settings.freshness_threshold_minutes,
    )
    return {"category": result.category.value, "confidence": result.confidence}


def intent_exact_match(run, example) -> dict:
    expected = (example.outputs or {}).get("expected_intent")
    actual = (run.outputs or {}).get("intent")
    return {"key": "intent_exact_match", "score": actual == expected}


def fault_exact_match(run, example) -> dict:
    expected = (example.outputs or {}).get("expected_category")
    actual = (run.outputs or {}).get("category")
    return {"key": "fault_category_exact_match", "score": actual == expected}


def main() -> None:
    if not os.getenv("LANGSMITH_API_KEY"):
        raise SystemExit("Set LANGSMITH_API_KEY before running the LangSmith evaluators.")
    evaluate(
        intent_target, data="trackobit-intent-parser-v1",
        evaluators=[intent_exact_match], experiment_prefix="intent-baseline",
    )
    evaluate(
        fault_target, data="trackobit-fault-classifier-v1",
        evaluators=[fault_exact_match], experiment_prefix="fault-baseline",
    )


if __name__ == "__main__":
    main()
