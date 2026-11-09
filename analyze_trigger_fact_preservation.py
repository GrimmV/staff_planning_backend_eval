"""
LLM-as-a-judge analysis of trigger-fact preservation in planner-facing explanations.

For each balanced evaluation case, the script maps `triggered_rules` from the silver-label
policy to must-mention facts and asks a judge LLM whether those facts are explicitly
communicated in the planner-facing explanation layer:
    - general_assessment
    - detail_level_1_assessment
    - detail_level_2_assessment
"""

from __future__ import annotations

import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Literal, Optional, TypedDict

from opentelemetry.trace import StatusCode

import evaluate_diff as evaluate_diff_module
from alignment_analysis import (
    CACHE_SILVER_LABELS,
    EVALUATION_MODES,
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
from llm.prompts.TriggerFactJudgePrompt import TRIGGER_FACT_JUDGE_PROMPT
from llm.response_models.TriggerFactJudgment import TriggerFactJudgment

CACHE_ROOT = "cache_experiments"
OUTPUT_DIR = os.path.join(CACHE_ROOT, "analysis", "trigger_fact_preservation")

Severity = Literal["hard", "caution"]


class MustMentionFact(TypedDict):
    fact_id: str
    rule_name: str
    severity: Severity
    statement: str


RULE_TO_FACT: Dict[str, MustMentionFact] = {
    "high_priority_client_unassigned": {
        "fact_id": "high_priority_client_unassigned",
        "rule_name": "high_priority_client_unassigned",
        "severity": "hard",
        "statement": (
            "The change causes at least one high-priority client to become unassigned "
            "or to lose coverage."
        ),
    },
    "severe_coverage_loss": {
        "fact_id": "severe_coverage_loss",
        "rule_name": "severe_coverage_loss",
        "severity": "hard",
        "statement": (
            "The change leads to a severe loss of coverage or substantially fewer "
            "covered assignments overall."
        ),
    },
    "experience_drop_substantial": {
        "fact_id": "experience_drop_substantial",
        "rule_name": "experience_drop_substantial",
        "severity": "caution",
        "statement": (
            "Client or school familiarity decreases substantially for at least one "
            "relevant assignment."
        ),
    },
    "commute_above_50_minutes": {
        "fact_id": "commute_above_50_minutes",
        "rule_name": "commute_above_50_minutes",
        "severity": "caution",
        "statement": (
            "At least one added assignment creates a long commute above the relevant "
            "threshold."
        ),
    },
    "high_priority_früher_goes_down": {
        "fact_id": "high_priority_früher_goes_down",
        "rule_name": "high_priority_früher_goes_down",
        "severity": "caution",
        "statement": (
            "The timing or availability situation worsens for high-priority clients."
        ),
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate whether silver-label trigger facts survive into planner-facing "
            "LLM explanations."
        )
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Evaluation model slug used in cache_evaluations (default: auto-detect).",
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help="Model for the trigger-fact judge (default: MODEL_NAME env or evaluate_diff default).",
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
    parser.add_argument(
        "--mode",
        choices=list(EVALUATION_MODES),
        action="append",
        dest="modes",
        help="Evaluation mode(s) to analyze (default: all three).",
    )
    parser.add_argument(
        "--overwrite-cache",
        action="store_true",
        help=(
            "Ignore cached trigger-fact analyses and cached LLM judge results, "
            "rerun all requested cases, and overwrite existing output files."
        ),
    )
    return parser.parse_args()


def result_path(output_dir: str, mode: str, diff_key: str) -> str:
    return os.path.join(output_dir, mode, diff_key.replace("/", os.sep))


def trigger_fact_cache_key(
    judge_model: str,
    mode: str,
    diff_key: str,
    fact_id: str,
) -> str:
    return f"trigger_fact:{mode}:{judge_model}:{diff_key}:{fact_id}"


def explanation_fields(assessment: Dict[str, Any]) -> Dict[str, str]:
    return {
        "general_assessment": assessment.get("general_assessment", ""),
        "detail_level_1_assessment": assessment.get("detail_level_1_assessment", ""),
        "detail_level_2_assessment": assessment.get("detail_level_2_assessment", ""),
    }


def must_mention_facts(triggered_rules: List[str]) -> List[MustMentionFact]:
    facts: List[MustMentionFact] = []
    for rule_name in triggered_rules:
        fact = RULE_TO_FACT.get(rule_name)
        if fact is not None:
            facts.append(fact)
    return facts


def build_judge_prompt(fact: MustMentionFact, assessment: Dict[str, Any]) -> str:
    fields = explanation_fields(assessment)
    return TRIGGER_FACT_JUDGE_PROMPT.format(
        fact_id=fact["fact_id"],
        severity=fact["severity"],
        rule_name=fact["rule_name"],
        fact_statement=fact["statement"],
        general_assessment=fields["general_assessment"] or "(empty)",
        detail_level_1_assessment=fields["detail_level_1_assessment"] or "(empty)",
        detail_level_2_assessment=fields["detail_level_2_assessment"] or "(empty)",
    )


def run_fact_judge(
    client: Any,
    tracer: Any,
    judge_model: str,
    mode: str,
    diff_key: str,
    fact: MustMentionFact,
    assessment: Dict[str, Any],
    overwrite_cache: bool = False,
) -> Dict[str, Any]:
    cache_key = trigger_fact_cache_key(judge_model, mode, diff_key, fact["fact_id"])
    cached = None if overwrite_cache else retrieve_cached_result(cache_key)
    if cached is not None:
        return cached

    prompt = build_judge_prompt(fact, assessment)
    with tracer.start_as_current_span(
        "trigger_fact_judge", openinference_span_kind="chain"
    ) as span:
        span.set_input(prompt)
        response, token_usage = evaluate_diff_module.create_structured_completion(
            model=judge_model,
            messages=[{"role": "user", "content": prompt}],
            response_model=TriggerFactJudgment,
            temperature=0.2,
            top_p=0.8,
            presence_penalty=0.5,
            extra_body={
                "top_k": 20,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
        result = response.model_dump()
        if token_usage is not None:
            result["token_usage"] = token_usage
        span.set_output(result)
        span.set_status(StatusCode.OK)

    cache_result(cache_key, result)
    return result


def collect_cases(
    model_slug: str,
    modes: List[str],
    allowed_diff_keys: set[str],
    silver_records: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    for mode in modes:
        mode_root = evaluation_dir(mode, model_slug)
        if not os.path.isdir(mode_root):
            raise FileNotFoundError(f"Missing evaluation mode directory: {mode_root}")

        for diff_key in sorted(allowed_diff_keys):
            silver_record = silver_records.get(diff_key)
            if silver_record is None:
                continue
            triggered_rules = silver_record.get("triggered_rules") or []
            facts = must_mention_facts(triggered_rules)
            if not facts:
                continue

            eval_path = os.path.join(mode_root, diff_key.replace("/", os.sep))
            if not os.path.exists(eval_path):
                continue

            evaluation = load_json(eval_path)
            cases.append(
                {
                    "mode": mode,
                    "diff_key": diff_key,
                    "evaluation": evaluation,
                    "silver_record": silver_record,
                    "facts": facts,
                }
            )
    return cases


def analyze_case(
    case: Dict[str, Any],
    client: Any,
    tracer: Any,
    judge_model: str,
    output_dir: str,
    overwrite_cache: bool = False,
) -> Dict[str, Any]:
    mode = case["mode"]
    diff_key = case["diff_key"]
    out_path = result_path(output_dir, mode, diff_key)
    if os.path.exists(out_path) and not overwrite_cache:
        print(f"  [{mode}] cached: {diff_key}")
        return load_json(out_path)
    if os.path.exists(out_path):
        print(f"  [{mode}] overwriting cache: {diff_key}")

    assessment = case["evaluation"]["assessment"]

    def judge_one(fact: MustMentionFact) -> Dict[str, Any]:
        judgment = run_fact_judge(
            client,
            tracer,
            judge_model,
            mode,
            diff_key,
            fact,
            assessment,
            overwrite_cache=overwrite_cache,
        )
        return {
            **fact,
            "judgment": judgment,
            "correctly_preserved": bool(
                judgment.get("mentioned") and judgment.get("polarity_correct")
            ),
        }

    with ThreadPoolExecutor(max_workers=max(1, len(case["facts"]))) as executor:
        fact_results = list(executor.map(judge_one, case["facts"]))

    preserved_count = sum(1 for item in fact_results if item["correctly_preserved"])
    result = {
        "diff_key": diff_key,
        "evaluation_mode": mode,
        "evaluation_model": case["evaluation"]["model"],
        "judge_model": judge_model,
        "silver_label": case["silver_record"]["silver_label"],
        "triggered_rules": case["silver_record"].get("triggered_rules", []),
        "diff_reference": case["silver_record"].get("diff_reference"),
        "planner_facing_fields": explanation_fields(assessment),
        "facts": fact_results,
        "n_trigger_facts": len(fact_results),
        "n_correctly_preserved": preserved_count,
        "all_trigger_facts_preserved": preserved_count == len(fact_results),
        "no_trigger_facts_preserved": preserved_count == 0,
    }
    save_json(out_path, result)
    print(
        f"  [{mode}] judged: {diff_key} "
        f"({preserved_count}/{len(fact_results)} facts preserved)"
    )
    return result


def safe_rate(numerator: int, denominator: int) -> Optional[float]:
    if denominator == 0:
        return None
    return numerator / denominator


def summarize_mode_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    n_cases = len(results)
    n_facts = sum(result["n_trigger_facts"] for result in results)
    n_preserved = sum(result["n_correctly_preserved"] for result in results)
    n_complete = sum(1 for result in results if result["all_trigger_facts_preserved"])
    n_zero = sum(1 for result in results if result["no_trigger_facts_preserved"])

    severity_counts: Dict[Severity, Dict[str, int]] = {
        "hard": {"facts": 0, "preserved": 0},
        "caution": {"facts": 0, "preserved": 0},
    }
    rule_counts: Dict[str, Dict[str, int]] = {}

    for result in results:
        for fact in result["facts"]:
            severity = fact["severity"]
            severity_counts[severity]["facts"] += 1
            if fact["correctly_preserved"]:
                severity_counts[severity]["preserved"] += 1

            rule_bucket = rule_counts.setdefault(
                fact["fact_id"], {"facts": 0, "preserved": 0}
            )
            rule_bucket["facts"] += 1
            if fact["correctly_preserved"]:
                rule_bucket["preserved"] += 1

    return {
        "n_cases_with_triggers": n_cases,
        "n_trigger_facts": n_facts,
        "trigger_fact_recall": safe_rate(n_preserved, n_facts),
        "complete_trigger_preservation": safe_rate(n_complete, n_cases),
        "critical_omission_rate": safe_rate(n_zero, n_cases),
        "hard_trigger_recall": safe_rate(
            severity_counts["hard"]["preserved"], severity_counts["hard"]["facts"]
        ),
        "caution_trigger_recall": safe_rate(
            severity_counts["caution"]["preserved"],
            severity_counts["caution"]["facts"],
        ),
        "counts": {
            "preserved_facts": n_preserved,
            "complete_cases": n_complete,
            "critical_omission_cases": n_zero,
            "severity": severity_counts,
            "by_fact": {
                fact_id: {
                    "facts": bucket["facts"],
                    "preserved": bucket["preserved"],
                    "recall": safe_rate(bucket["preserved"], bucket["facts"]),
                }
                for fact_id, bucket in sorted(rule_counts.items())
            },
        },
        "cases": [
            {
                "diff_key": result["diff_key"],
                "silver_label": result["silver_label"],
                "triggered_rules": result["triggered_rules"],
                "n_trigger_facts": result["n_trigger_facts"],
                "n_correctly_preserved": result["n_correctly_preserved"],
                "all_trigger_facts_preserved": result["all_trigger_facts_preserved"],
                "no_trigger_facts_preserved": result["no_trigger_facts_preserved"],
            }
            for result in results
        ],
    }


def run_analysis(
    model_slug: str,
    judge_model: str,
    modes: List[str],
    client: Any,
    tracer: Any,
    output_dir: str,
    overwrite_cache: bool = False,
) -> Dict[str, Any]:
    allowed_diff_keys = load_balanced_diff_keys()
    silver_records = load_balanced_silver_label_records()
    if not silver_records:
        raise FileNotFoundError(f"No balanced silver labels found in {CACHE_SILVER_LABELS}")

    cases = collect_cases(model_slug, modes, allowed_diff_keys, silver_records)
    os.makedirs(output_dir, exist_ok=True)

    results_by_mode: Dict[str, List[Dict[str, Any]]] = {mode: [] for mode in modes}
    for case in cases:
        result = analyze_case(
            case,
            client,
            tracer,
            judge_model,
            output_dir,
            overwrite_cache=overwrite_cache,
        )
        results_by_mode[case["mode"]].append(result)

    summary = {
        "evaluation_model_slug": model_slug,
        "judge_model": judge_model,
        "balanced_sample_n": len(allowed_diff_keys),
        "explanation_scope": [
            "general_assessment",
            "detail_level_1_assessment",
            "detail_level_2_assessment",
        ],
        "method_note": (
            "The trigger-fact analysis was applied to the planner-facing explanation "
            "fields rather than to all intermediate summaries, because the purpose was "
            "to assess whether critical what-if evidence survives into the explanation "
            "layer that is visible as decision orientation."
        ),
        "fact_definitions": RULE_TO_FACT,
        "modes": {
            mode: summarize_mode_results(results_by_mode[mode]) for mode in modes
        },
        "total_case_evaluations": sum(len(results_by_mode[mode]) for mode in modes),
    }
    summary_path = os.path.join(output_dir, "summary.json")
    save_json(summary_path, summary)
    summary["summary_json"] = summary_path.replace("\\", "/")
    return summary


def main() -> None:
    args = parse_args()
    modes = args.modes or list(EVALUATION_MODES)
    model_slug = discover_model_slug(args.model, required_modes=set(modes))
    judge_model = args.judge_model or get_model_name() or evaluate_diff_module.model

    client, tracer = init_phoenix(
        project_name="staff-planning-trigger-fact-preservation",
        base_url=args.base_url,
    )
    evaluate_diff_module.client = client
    evaluate_diff_module.tracer = tracer
    evaluate_diff_module.model = judge_model

    base_url_info = args.base_url or os.getenv("OPENAI_BASE_URL") or "default (OpenAI)"
    print(
        f"Running trigger-fact preservation analysis: evaluation={model_slug}, "
        f"judge_model={judge_model}, modes={modes}, base_url={base_url_info}, "
        f"overwrite_cache={args.overwrite_cache}"
    )

    summary = run_analysis(
        model_slug,
        judge_model,
        modes,
        client,
        tracer,
        args.output_dir,
        overwrite_cache=args.overwrite_cache,
    )
    print(f"\nDone. {summary['total_case_evaluations']} case evaluations written.")
    print(f"  summary: {summary['summary_json']}")
    for mode, mode_summary in summary["modes"].items():
        print(
            f"  [{mode}] n_cases={mode_summary['n_cases_with_triggers']}, "
            f"recall={mode_summary['trigger_fact_recall']}, "
            f"complete={mode_summary['complete_trigger_preservation']}, "
            f"omission={mode_summary['critical_omission_rate']}"
        )


if __name__ == "__main__":
    main()
