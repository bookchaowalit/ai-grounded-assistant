"""Offline golden-question evaluation for the local answer adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import EVALUATION_PATH, EVALUATION_VERSION
from .schema import DataContractError, validate_question
from .store import read_json


def load_evaluation_cases(root: str | Path | None = None) -> list[dict[str, Any]]:
    path = Path(root or EVALUATION_PATH.parent.parent.parent) / "data" / "evaluation" / "golden_questions.v1.json"
    value = read_json(path)
    if not isinstance(value, list) or not value:
        raise DataContractError("EVAL001", "evaluation set must be a non-empty array")
    cases: list[dict[str, Any]] = []
    for index, case in enumerate(value):
        if not isinstance(case, dict) or set(case) != {"id", "question", "expected_outcome", "expected_source_id"}:
            raise DataContractError("EVAL002", "evaluation case fields are invalid", {"index": index})
        case_id = case["id"]
        if not isinstance(case_id, str) or not case_id.strip():
            raise DataContractError("EVAL003", "evaluation case id must be non-empty", {"index": index})
        question = validate_question(case["question"])
        if case["expected_outcome"] not in {"grounded", "fallback", "refused"}:
            raise DataContractError("EVAL004", "evaluation expected_outcome is invalid", {"id": case_id})
        source_id = case["expected_source_id"]
        if source_id is not None and (not isinstance(source_id, str) or not source_id.strip()):
            raise DataContractError("EVAL005", "evaluation expected_source_id is invalid", {"id": case_id})
        cases.append(
            {
                "id": case_id,
                "question": question,
                "expected_outcome": case["expected_outcome"],
                "expected_source_id": source_id,
            }
        )
    return cases


def run_evaluation(assistant: Any, root: str | Path | None = None) -> dict[str, Any]:
    cases = load_evaluation_cases(root)
    results: list[dict[str, Any]] = []
    for case in cases:
        response = assistant.answer(case["question"])
        if response["data_status"] == "refused":
            actual_outcome = "refused"
        else:
            actual_outcome = "grounded" if not response["fallback"] else "fallback"
        actual_sources = response["grounding"]["source_ids"]
        passed = actual_outcome == case["expected_outcome"] and (
            case["expected_source_id"] is None or case["expected_source_id"] in actual_sources
        )
        results.append(
            {
                "id": case["id"],
                "expected_outcome": case["expected_outcome"],
                "actual_outcome": actual_outcome,
                "expected_source_id": case["expected_source_id"],
                "actual_source_ids": actual_sources,
                "passed": passed,
            }
        )
    passed_count = sum(1 for result in results if result["passed"])
    return {
        "evaluation_version": EVALUATION_VERSION,
        "adapter": assistant.metadata()["adapter"],
        "threshold": {"required_pass_rate": 1.0, "cases": len(results)},
        "status": "pass" if passed_count == len(results) else "fail",
        "passed": passed_count,
        "failed": len(results) - passed_count,
        "per_outcome": outcome_metrics(results),
        "results": results,
    }


OUTCOMES = ("grounded", "fallback", "refused")


def outcome_metrics(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per-outcome precision/recall over expected vs. actual outcome labels.

    Precision is ``None`` when the adapter never predicted that outcome and
    recall is ``None`` when the golden set has no case expecting it, so an
    empty category is visible instead of silently scoring 1.0 or 0.0.
    """

    metrics: dict[str, dict[str, Any]] = {}
    for outcome in OUTCOMES:
        expected = sum(1 for r in results if r["expected_outcome"] == outcome)
        predicted = sum(1 for r in results if r["actual_outcome"] == outcome)
        true_positive = sum(1 for r in results if r["expected_outcome"] == outcome and r["actual_outcome"] == outcome)
        metrics[outcome] = {
            "expected": expected,
            "predicted": predicted,
            "true_positive": true_positive,
            "precision": round(true_positive / predicted, 4) if predicted else None,
            "recall": round(true_positive / expected, 4) if expected else None,
        }
    return metrics

