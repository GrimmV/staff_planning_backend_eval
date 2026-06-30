"""
LLM-as-a-judge divergence analysis for misaligned full-pipeline evaluations.

Compares cached diffs (ground truth) with LLM assessments where the generated
score does not match the silver label, and classifies the likely cause(s).
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Optional

from opentelemetry.trace import StatusCode

from alignment_analysis import (
    CACHE_DIFFS,
    CACHE_SILVER_LABELS,
    SCORE_ORDINAL,
    discover_model_slug,
    evaluation_dir,
    load_balanced_diff_keys,
    load_balanced_silver_label_records,
    load_json,
    save_json,
)
from llm.helper.cache import cache_result, retrieve_cached_result
from llm.helper.helper import get_model_name
from llm.helper.init_phoenix import init_phoenix
from llm.prompts.DivergenceJudgePrompt import DIVERGENCE_JUDGE_PROMPT
from llm.response_models.DivergenceAnalysis import DivergenceAnalysis

CACHE_ROOT = "cache_experiments"
OUTPUT_DIR = os.path.join(CACHE_ROOT, "analysis", "divergence_analysis")
EVALUATION_MODE = "full"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run LLM-as-a-judge divergence analysis on misaligned full evaluations."
        )
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model slug used in cache_evaluations (default: auto-detect).",
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help="Model for the judge LLM (default: MODEL_NAME env or evaluate_diff default).",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="OpenAI-compatible API base URL (overrides OPENAI_BASE_URL).",
    )
    parser.add_argument(
        "--output-dir",
        default=OUTPUT_DIR,
        help="Directory for per-case results and summary JSON.",
    )
    return parser.parse_args()


def is_misaligned(silver_label: str, assessment_score: str) -> bool:
    return SCORE_ORDINAL[silver_label] != SCORE_ORDINAL[assessment_score]


def judge_cache_key(
    judge_model: str, diff_key: str, silver_label: str, assessment_score: str
) -> str:
    return (
        f"divergence_judge:{EVALUATION_MODE}:{judge_model}:"
        f"{diff_key}:{silver_label}:{assessment_score}"
    )


def format_json_block(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_judge_prompt(
    silver_record: Dict[str, Any],
    diff_payload: Dict[str, Any],
    assessment: Dict[str, Any],
) -> str:
    diff = diff_payload["diff"]
    triggered_rules = silver_record.get("triggered_rules") or []
    return DIVERGENCE_JUDGE_PROMPT.format(
        silver_label=silver_record["silver_label"],
        triggered_rules=", ".join(triggered_rules) if triggered_rules else "(keine)",
        diff_stats=format_json_block(diff["stats"]),
        vorher=diff["vorher"],
        nachher=diff["nachher"],
        llm_assessment=format_json_block(assessment),
    )


def run_judge(
    client: Any,
    tracer: Any,
    judge_model: str,
    prompt: str,
    cache_key: str,
) -> Dict[str, Any]:
    cached = retrieve_cached_result(cache_key)
    if cached is not None:
        return cached

    with tracer.start_as_current_span(
        "divergence_judge", openinference_span_kind="chain"
    ) as span:
        span.set_input(prompt)
        response = client.chat.completions.create(
            model=judge_model,
            messages=[{"role": "user", "content": prompt}],
            response_model=DivergenceAnalysis,
            temperature=0.3,
            top_p=0.8,
            presence_penalty=1.0,
            extra_body={
                "top_k": 20,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
        result = response.model_dump()
        span.set_output(result)
        span.set_status(StatusCode.OK)

    cache_result(cache_key, result)
    return result


def collect_misaligned_cases(
    model_slug: str,
    silver_records: Dict[str, Dict[str, Any]],
    allowed_diff_keys: set[str],
) -> List[Dict[str, Any]]:
    mode_root = evaluation_dir(EVALUATION_MODE, model_slug)
    if not os.path.isdir(mode_root):
        raise FileNotFoundError(f"Missing evaluation mode directory: {mode_root}")

    cases: List[Dict[str, Any]] = []
    for diff_key, silver_record in silver_records.items():
        if diff_key not in allowed_diff_keys:
            continue
        eval_path = os.path.join(mode_root, diff_key.replace("/", os.sep))
        if not os.path.exists(eval_path):
            continue

        evaluation = load_json(eval_path)
        assessment_score = evaluation["assessment"]["score"]
        silver_label = silver_record["silver_label"]
        if not is_misaligned(silver_label, assessment_score):
            continue

        diff_path = os.path.join(CACHE_DIFFS, diff_key.replace("/", os.sep))
        if not os.path.exists(diff_path):
            continue

        cases.append(
            {
                "diff_key": diff_key,
                "silver_record": silver_record,
                "evaluation": evaluation,
                "diff_payload": load_json(diff_path),
                "silver_label": silver_label,
                "assessment_score": assessment_score,
                "ordinal_deviation": abs(
                    SCORE_ORDINAL[silver_label] - SCORE_ORDINAL[assessment_score]
                ),
            }
        )
    return cases


def result_path(output_dir: str, diff_key: str) -> str:
    return os.path.join(output_dir, diff_key.replace("/", os.sep))


def analyze_case(
    case: Dict[str, Any],
    client: Any,
    tracer: Any,
    judge_model: str,
    output_dir: str,
) -> Dict[str, Any]:
    out_path = result_path(output_dir, case["diff_key"])
    if os.path.exists(out_path):
        print(f"  cached: {case['diff_key']}")
        return load_json(out_path)

    prompt = build_judge_prompt(
        case["silver_record"],
        case["diff_payload"],
        case["evaluation"]["assessment"],
    )
    cache_key = judge_cache_key(
        judge_model,
        case["diff_key"],
        case["silver_label"],
        case["assessment_score"],
    )
    divergence = run_judge(client, tracer, judge_model, prompt, cache_key)

    result = {
        "diff_key": case["diff_key"],
        "evaluation_mode": EVALUATION_MODE,
        "evaluation_model": case["evaluation"]["model"],
        "judge_model": judge_model,
        "silver_label": case["silver_label"],
        "assessment_score": case["assessment_score"],
        "ordinal_deviation": case["ordinal_deviation"],
        "triggered_rules": case["silver_record"].get("triggered_rules", []),
        "diff_reference": case["silver_record"].get("diff_reference"),
        "divergence": divergence,
    }
    save_json(out_path, result)
    print(f"  judged: {case['diff_key']} -> {divergence['primary_divergence_type']}")
    return result


def summarize_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    primary_divergence_type_counts: Dict[str, int] = {}
    for result in results:
        primary_divergence_type_counts[result["divergence"]["primary_divergence_type"]] = primary_divergence_type_counts.get(result["divergence"]["primary_divergence_type"], 0) + 1

    return {
        "n_cases": len(results),
        "primary_divergence_type_counts": dict(sorted(primary_divergence_type_counts.items())),
        "cases": [
            {
                "diff_key": result["diff_key"],
                "silver_label": result["silver_label"],
                "assessment_score": result["assessment_score"],
                "ordinal_deviation": result["ordinal_deviation"],
                "primary_divergence_type": result["divergence"]["primary_divergence_type"],
                "secondary_divergence_type": result["divergence"]["secondary_divergence_type"],
            }
            for result in results
        ],
    }


def run_analysis(
    model_slug: str,
    judge_model: str,
    client: Any,
    tracer: Any,
    output_dir: str,
) -> Dict[str, Any]:
    allowed_diff_keys = load_balanced_diff_keys()
    silver_records = load_balanced_silver_label_records()
    if not silver_records:
        raise FileNotFoundError(f"No balanced silver labels found in {CACHE_SILVER_LABELS}")

    cases = collect_misaligned_cases(model_slug, silver_records, allowed_diff_keys)
    os.makedirs(output_dir, exist_ok=True)

    results: List[Dict[str, Any]] = []
    for case in cases:
        results.append(analyze_case(case, client, tracer, judge_model, output_dir))

    summary = {
        "evaluation_mode": EVALUATION_MODE,
        "evaluation_model_slug": model_slug,
        "judge_model": judge_model,
        "balanced_sample_n": len(allowed_diff_keys),
        **summarize_results(results),
    }
    summary_path = os.path.join(output_dir, "summary.json")
    save_json(summary_path, summary)
    summary["summary_json"] = summary_path.replace("\\", "/")
    return summary


def main() -> None:
    args = parse_args()
    model_slug = discover_model_slug(args.model, required_modes={EVALUATION_MODE})
    judge_model = args.judge_model or get_model_name() or "gpt-5.4"
    client, tracer = init_phoenix(
        project_name="staff-planning-divergence-analysis",
        base_url=args.base_url,
    )

    base_url_info = args.base_url or os.getenv("OPENAI_BASE_URL") or "default (OpenAI)"
    print(
        f"Running divergence analysis: evaluation={EVALUATION_MODE}__{model_slug}, "
        f"judge_model={judge_model}, base_url={base_url_info}"
    )

    summary = run_analysis(model_slug, judge_model, client, tracer, args.output_dir)
    print(f"\nDone. {summary['n_cases']} misaligned cases analyzed.")
    print(f"  summary: {summary['summary_json']}")
    if summary["primary_divergence_type_counts"]:
        print("  primary divergence type counts:")
        for divergence_type, count in summary["primary_divergence_type_counts"].items():
            print(f"    {divergence_type}: {count}")


if __name__ == "__main__":
    main()
