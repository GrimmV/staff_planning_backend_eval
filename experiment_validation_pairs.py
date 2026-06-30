"""Build input/output pairs for LLM output validation per evaluation mode."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional

from evaluate_experiment_diffs import EvaluationMode, simple_diff_tables

PipelineStep = Literal[
    "assignments_summary", "statistics_summary", "assessment", "direct_assessment"
]

ASSESSMENT_OUTPUT_KEYS = (
    "score",
    "general_assessment",
    "detail_level_1_assessment",
    "detail_level_2_assessment",
)


def format_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _assessment_output(assessment: Dict[str, Any]) -> Dict[str, Any]:
    return {key: assessment[key] for key in ASSESSMENT_OUTPUT_KEYS if key in assessment}


def _statistics_output(assessment: Dict[str, Any]) -> Dict[str, Any]:
    statistiken = assessment.get("statistiken", {})
    return {
        "relevant_changes": statistiken.get("relevant_changes", []),
        "effect": statistiken.get("effect"),
    }


def _simple_diff_input(simple_diff_payload: Dict[str, Any]) -> str:
    removed_md, added_md = simple_diff_tables(simple_diff_payload)
    return (
        f"entfernte Zuordnungen:\n{removed_md}\n\n"
        f"hinzugefügte Zuordnungen:\n{added_md}"
    )


def build_validation_pairs(
    mode: EvaluationMode,
    assessment: Dict[str, Any],
    diff_payload: Optional[Dict[str, Any]],
    simple_diff_payload: Optional[Dict[str, Any]],
) -> List[Dict[str, str]]:
    pairs: List[Dict[str, str]] = []

    if mode == "simple_direct":
        if simple_diff_payload is None:
            raise ValueError("simple_direct validation requires simple_diff_payload")
        pairs.append(
            {
                "step": "direct_assessment",
                "input": _simple_diff_input(simple_diff_payload),
                "output": format_json(_assessment_output(assessment)),
            }
        )
        return pairs

    if diff_payload is None:
        raise ValueError(f"{mode} validation requires diff_payload")

    diff = diff_payload["diff"]

    if mode == "full":
        assignments_input = f"vorher: {diff['vorher']}, nachher: {diff['nachher']}"
    else:
        if simple_diff_payload is None:
            raise ValueError("simple validation requires simple_diff_payload")
        assignments_input = _simple_diff_input(simple_diff_payload)

    pairs.append(
        {
            "step": "assignments_summary",
            "input": assignments_input,
            "output": format_json(assessment.get("änderungen", [])),
        }
    )

    pairs.append(
        {
            "step": "statistics_summary",
            "input": format_json(diff["stats"]),
            "output": format_json(_statistics_output(assessment)),
        }
    )

    relevant_changes = assessment.get("statistiken", {}).get("relevant_changes", [])
    assessment_input = (
        f"relevanteste Veränderungen: {assessment.get('änderungen', [])}, "
        f"statistiken: {relevant_changes}"
    )
    pairs.append(
        {
            "step": "assessment",
            "input": assessment_input,
            "output": format_json(_assessment_output(assessment)),
        }
    )
    return pairs
