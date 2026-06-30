"""
LLM-as-a-judge validation of generated evaluation outputs.

For each evaluation case and pipeline step, judges clarity (0–10) and
input/output coherence (0–10), each with a short explanation.
"""

from __future__ import annotations

import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Literal, Optional

from opentelemetry.trace import StatusCode

import evaluate_diff as evaluate_diff_module
from alignment_analysis import (
    CACHE_DIFFS,
    CACHE_SIMPLE_DIFFS,
    EVALUATION_MODES,
    discover_model_slug,
    evaluation_dir,
    load_balanced_diff_keys,
    load_json,
    save_json,
)
from experiment_validation_pairs import PipelineStep, build_validation_pairs
from llm.helper.cache import cache_result, retrieve_cached_result
from llm.helper.helper import get_model_name
from llm.helper.init_phoenix import init_phoenix
from llm.prompts.OutputValidationPrompt import (
    CLARITY_JUDGE_PROMPT,
    COHERENCE_JUDGE_PROMPT,
    STEP_CONTEXT,
)
from llm.response_models.OutputValidation import ClarityJudgment, CoherenceJudgment

CACHE_ROOT = "cache_experiments"
OUTPUT_DIR = os.path.join(CACHE_ROOT, "cache_validations")

JudgmentType = Literal["clarity", "coherence"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run LLM-as-a-judge validation on experiment evaluation outputs."
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Evaluation model slug in cache_evaluations (default: auto-detect).",
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help="Model for validation judges (default: MODEL_NAME env or evaluate_diff default).",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="OpenAI-compatible API base URL (overrides OPENAI_BASE_URL).",
    )
    parser.add_argument(
        "--output-dir",
        default=OUTPUT_DIR,
        help="Directory for per-case validation results and summary JSON.",
    )
    parser.add_argument(
        "--mode",
        choices=list(EVALUATION_MODES),
        action="append",
        dest="modes",
        help="Evaluation mode(s) to validate (default: all three).",
    )
    return parser.parse_args()


def validation_cache_key(
    judge_model: str,
    mode: str,
    diff_key: str,
    step: PipelineStep,
    judgment_type: JudgmentType,
) -> str:
    return (
        f"output_validation:{mode}:{judge_model}:{diff_key}:{step}:{judgment_type}"
    )


def build_judge_prompt(
    judgment_type: JudgmentType,
    step: PipelineStep,
    input_text: str,
    output_text: str,
) -> str:
    template = (
        CLARITY_JUDGE_PROMPT
        if judgment_type == "clarity"
        else COHERENCE_JUDGE_PROMPT
    )
    return template.format(
        step_context=STEP_CONTEXT[step],
        step_name=step,
        input_text=input_text,
        output_text=output_text,
    )


def run_judge(
    client: Any,
    tracer: Any,
    judge_model: str,
    judgment_type: JudgmentType,
    step: PipelineStep,
    input_text: str,
    output_text: str,
    cache_key: str,
) -> Dict[str, Any]:
    cached = retrieve_cached_result(cache_key)
    if cached is not None:
        return cached

    response_model = ClarityJudgment if judgment_type == "clarity" else CoherenceJudgment
    span_name = f"validation_{judgment_type}_{step}"
    prompt = build_judge_prompt(judgment_type, step, input_text, output_text)

    with tracer.start_as_current_span(span_name, openinference_span_kind="chain") as span:
        span.set_input(prompt)
        response, token_usage = evaluate_diff_module.create_structured_completion(
            model=judge_model,
            messages=[{"role": "user", "content": prompt}],
            response_model=response_model,
            temperature=0.3,
            top_p=0.8,
            presence_penalty=1.0,
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


def validate_pair(
    client: Any,
    tracer: Any,
    judge_model: str,
    mode: str,
    diff_key: str,
    pair: Dict[str, str],
) -> Dict[str, Any]:
    step = pair["step"]
    input_text = pair["input"]
    output_text = pair["output"]

    def judge(judgment_type: JudgmentType) -> Dict[str, Any]:
        cache_key = validation_cache_key(
            judge_model, mode, diff_key, step, judgment_type
        )
        return run_judge(
            client,
            tracer,
            judge_model,
            judgment_type,
            step,
            input_text,
            output_text,
            cache_key,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        clarity_future = executor.submit(judge, "clarity")
        coherence_future = executor.submit(judge, "coherence")
        return {
            "step": step,
            "input": input_text,
            "output": output_text,
            "clarity": clarity_future.result(),
            "coherence": coherence_future.result(),
        }


def result_path(output_dir: str, mode: str, diff_key: str) -> str:
    return os.path.join(output_dir, mode, diff_key.replace("/", os.sep))


def validate_case(
    mode: str,
    diff_key: str,
    evaluation: Dict[str, Any],
    diff_payload: Dict[str, Any],
    simple_diff_payload: Optional[Dict[str, Any]],
    client: Any,
    tracer: Any,
    judge_model: str,
    output_dir: str,
) -> Dict[str, Any]:
    out_path = result_path(output_dir, mode, diff_key)
    if os.path.exists(out_path):
        print(f"  [{mode}] cached: {diff_key}")
        return load_json(out_path)

    pairs = build_validation_pairs(
        mode, evaluation["assessment"], diff_payload, simple_diff_payload
    )
    step_results = [
        validate_pair(client, tracer, judge_model, mode, diff_key, pair)
        for pair in pairs
    ]

    result = {
        "diff_key": diff_key,
        "evaluation_mode": mode,
        "evaluation_model": evaluation["model"],
        "judge_model": judge_model,
        "diff_reference": evaluation.get("diff_reference"),
        "simple_diff_reference": evaluation.get("simple_diff_reference"),
        "steps": {item["step"]: item for item in step_results},
    }
    save_json(out_path, result)
    clarity_scores = [item["clarity"]["score"] for item in step_results]
    coherence_scores = [item["coherence"]["score"] for item in step_results]
    print(
        f"  [{mode}] validated: {diff_key} "
        f"(clarity avg={sum(clarity_scores)/len(clarity_scores):.1f}, "
        f"coherence avg={sum(coherence_scores)/len(coherence_scores):.1f})"
    )
    return result


def iter_evaluation_cases(
    model_slug: str,
    modes: List[str],
    allowed_diff_keys: set[str],
) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    for mode in modes:
        mode_root = evaluation_dir(mode, model_slug)
        if not os.path.isdir(mode_root):
            raise FileNotFoundError(f"Missing evaluation mode directory: {mode_root}")

        for diff_key in sorted(allowed_diff_keys):
            eval_path = os.path.join(mode_root, diff_key.replace("/", os.sep))
            if not os.path.exists(eval_path):
                continue

            diff_path = os.path.join(CACHE_DIFFS, diff_key.replace("/", os.sep))
            if not os.path.exists(diff_path):
                continue

            simple_diff_path = os.path.join(
                CACHE_SIMPLE_DIFFS, diff_key.replace("/", os.sep)
            )
            cases.append(
                {
                    "mode": mode,
                    "diff_key": diff_key,
                    "evaluation": load_json(eval_path),
                    "diff_payload": load_json(diff_path),
                    "simple_diff_payload": (
                        load_json(simple_diff_path)
                        if os.path.exists(simple_diff_path)
                        else None
                    ),
                }
            )
    return cases


def summarize_mode_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    clarity_scores: List[int] = []
    coherence_scores: List[int] = []
    step_scores: Dict[str, Dict[str, List[int]]] = {}

    for result in results:
        for step_name, step_data in result["steps"].items():
            step_bucket = step_scores.setdefault(
                step_name, {"clarity": [], "coherence": []}
            )
            clarity = step_data["clarity"]["score"]
            coherence = step_data["coherence"]["score"]
            clarity_scores.append(clarity)
            coherence_scores.append(coherence)
            step_bucket["clarity"].append(clarity)
            step_bucket["coherence"].append(coherence)

    def mean(values: List[int]) -> Optional[float]:
        return round(sum(values) / len(values), 2) if values else None

    return {
        "n_cases": len(results),
        "mean_clarity": mean(clarity_scores),
        "mean_coherence": mean(coherence_scores),
        "by_step": {
            step: {
                "mean_clarity": mean(scores["clarity"]),
                "mean_coherence": mean(scores["coherence"]),
                "n": len(scores["clarity"]),
            }
            for step, scores in sorted(step_scores.items())
        },
    }


def run_validation(
    model_slug: str,
    judge_model: str,
    modes: List[str],
    client: Any,
    tracer: Any,
    output_dir: str,
) -> Dict[str, Any]:
    allowed_diff_keys = load_balanced_diff_keys()
    cases = iter_evaluation_cases(model_slug, modes, allowed_diff_keys)
    os.makedirs(output_dir, exist_ok=True)

    results_by_mode: Dict[str, List[Dict[str, Any]]] = {mode: [] for mode in modes}
    for case in cases:
        result = validate_case(
            case["mode"],
            case["diff_key"],
            case["evaluation"],
            case["diff_payload"],
            case["simple_diff_payload"],
            client,
            tracer,
            judge_model,
            output_dir,
        )
        results_by_mode[case["mode"]].append(result)

    summary = {
        "evaluation_model_slug": model_slug,
        "judge_model": judge_model,
        "balanced_sample_n": len(allowed_diff_keys),
        "modes": {
            mode: summarize_mode_results(results_by_mode[mode]) for mode in modes
        },
        "total_validations": sum(len(results_by_mode[mode]) for mode in modes),
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
        project_name="staff-planning-output-validation",
        base_url=args.base_url,
    )
    evaluate_diff_module.client = client
    evaluate_diff_module.tracer = tracer
    evaluate_diff_module.model = judge_model

    base_url_info = args.base_url or os.getenv("OPENAI_BASE_URL") or "default (OpenAI)"
    print(
        f"Running output validation: evaluation={model_slug}, "
        f"judge_model={judge_model}, modes={modes}, base_url={base_url_info}"
    )

    summary = run_validation(
        model_slug, judge_model, modes, client, tracer, args.output_dir
    )
    print(f"\nDone. {summary['total_validations']} case validations written.")
    print(f"  summary: {summary['summary_json']}")
    for mode, mode_summary in summary["modes"].items():
        print(
            f"  [{mode}] n={mode_summary['n_cases']}, "
            f"clarity={mode_summary['mean_clarity']}, "
            f"coherence={mode_summary['mean_coherence']}"
        )


if __name__ == "__main__":
    main()
