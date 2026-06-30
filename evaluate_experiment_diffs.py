"""
LLM evaluation of experiment diffs in three settings:

1. full          – cache_diffs (stats + vorher/nachher markdown), full evaluate_diff pipeline
2. simple        – assignment tables from cache_simple_diffs + stats from cache_diffs
3. simple_direct – cache_simple_diffs only, assessment without intermediate summaries
"""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Literal, Optional, Tuple

import evaluate_diff as evaluate_diff_module
from opentelemetry.trace import StatusCode

from evaluate_diff import evaluate_diff
from alignment_analysis import load_balanced_diff_keys
from llm.helper.cache import cache_result, retrieve_cached_result
from llm.helper.init_phoenix import init_phoenix
from llm.prompts.AssessmentPrompt import ASSESSMENT_PROMPT
from llm.response_models.Assessment import Assessment
from llm_formatting.assignment_simple import assignments_to_markdown
from utils.float_to_time import float_to_time

CACHE_ROOT = "cache_experiments"
CACHE_DIFFS = os.path.join(CACHE_ROOT, "cache_diffs")
CACHE_SIMPLE_DIFFS = os.path.join(CACHE_ROOT, "cache_simple_diffs")
CACHE_EVALUATIONS = os.path.join(CACHE_ROOT, "cache_evaluations")

EvaluationMode = Literal["full", "simple", "simple_direct"]
EVALUATION_MODES: Tuple[EvaluationMode, ...] = ("full", "simple", "simple_direct")

client = evaluate_diff_module.client
tracer = evaluate_diff_module.tracer
model = evaluate_diff_module.model


def configure_llm(
    base_url: Optional[str] = None, model_name: Optional[str] = None
) -> None:
    global client, tracer, model

    new_client, new_tracer = init_phoenix(
        project_name="staff-planning-experiments", base_url=base_url
    )
    client = new_client
    tracer = new_tracer
    evaluate_diff_module.client = new_client
    evaluate_diff_module.tracer = new_tracer

    if model_name:
        model = model_name
        evaluate_diff_module.model = model_name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run LLM evaluation on experiment diffs."
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help=(
            "OpenAI-compatible API base URL for self-hosted models "
            "(overrides OPENAI_BASE_URL env var)."
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name to use (overrides MODEL_NAME env var and evaluate_diff default).",
    )
    return parser.parse_args()


def load_json(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def sanitize_model_name(model_name: str) -> str:
    return model_name.replace(".", "_").replace("/", "_")


def parse_diff_filename(filename: str) -> Optional[Tuple[int, int]]:
    stem = os.path.splitext(filename)[0]
    parts = stem.split("_to_")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def recommendation_to_assignment(recommendation: Dict[str, Any]) -> Dict[str, Any]:
    ma = recommendation["mitarbeiter"]
    client = recommendation["klient"]
    schule = client["schule"]

    klient_erfahrung = next(
        (
            item["tage"]
            for item in ma.get("klient_erfahrung", [])
            if item["name"] == client["name"]
        ),
        None,
    )
    schule_erfahrung = next(
        (
            item["tage"]
            for item in ma.get("schule_erfahrung", [])
            if item["name"] == schule
        ),
        None,
    )

    return {
        "klient_name": client["name"],
        "klient_benötigte_qualifikationen": client["qualifikationen"],
        "klient_tag_bis": float_to_time(client["anwesenheit"][1]),
        "klient_prioritaet": client["prioritaet"],
        "klient_nicht_vertreten_bis": client["nicht_vertreten_bis"],
        "mitarbeiter_name": ma["name"],
        "mitarbeiter_qualifikationen": ma["qualifikationen"],
        "mitarbeiter_tag_bis": float_to_time(ma["zeitfenster"][1]),
        "mitarbeiter_kann_vertreten_bis": ma["verfuegbar_bis"],
        "mitarbeiter_fahrtzeit": ma["schulen"][schule],
        "mitarbeiter_erfahrung_mit_dem_klienten": (
            f"{klient_erfahrung} Tage" if klient_erfahrung is not None else "Keine"
        ),
        "mitarbeiter_erfahrung_mit_der_schule": (
            f"{schule_erfahrung} Tage" if schule_erfahrung is not None else "Keine"
        ),
    }


def recommendations_to_markdown(recommendations: List[Dict[str, Any]]) -> str:
    if not recommendations:
        return "(keine Zuordnungen)"
    assignments = [recommendation_to_assignment(rec) for rec in recommendations]
    return assignments_to_markdown(assignments)


def simple_diff_tables(simple_diff_payload: Dict[str, Any]) -> Tuple[str, str]:
    changed = simple_diff_payload["changed_assignments"]
    removed_md = recommendations_to_markdown(changed.get("removed", []))
    added_md = recommendations_to_markdown(changed.get("added", []))
    return removed_md, added_md


def experiment_cache_key(mode: EvaluationMode, diff_path: str, extra: str = "") -> str:
    return f"experiment:{mode}:{model}:{diff_path}:{extra}"


def get_direct_assessment(plan_diff: str) -> Dict[str, Any]:
    with tracer.start_as_current_span(
        "direct_assessment", openinference_span_kind="chain"
    ) as span:
        prompt = ASSESSMENT_PROMPT.format(plan_diff=plan_diff)
        span.set_input(prompt)
        response, token_usage = evaluate_diff_module.create_structured_completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_model=Assessment,
            temperature=0.7,
            top_p=0.8,
            presence_penalty=1.5,
            extra_body={
                "top_k": 20,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
        response_payload = response.model_dump()
        if token_usage is not None:
            response_payload[evaluate_diff_module.LLM_CALLS_KEY] = {
                "direct_assessment": {
                    "call_name": "direct_assessment",
                    **token_usage,
                }
            }
        span.set_output(response_payload)
        span.set_status(StatusCode.OK)
        return response_payload


def evaluate_full_diff(diff_payload: Dict[str, Any], diff_path: str) -> Dict[str, Any]:
    diff = diff_payload["diff"]
    new_mas = diff_payload.get("new_mas", [])
    cache_key = experiment_cache_key("full", diff_path)
    cached = retrieve_cached_result(cache_key)
    if cached is not None and evaluate_diff_module.has_llm_calls(cached):
        return cached

    assessment = evaluate_diff(diff, new_mas)
    cache_result(cache_key, assessment)
    return assessment


def evaluate_simple_diff(
    diff_payload: Dict[str, Any],
    simple_diff_payload: Dict[str, Any],
    diff_path: str,
) -> Dict[str, Any]:
    cache_key = experiment_cache_key("simple", diff_path)
    cached = retrieve_cached_result(cache_key)
    if cached is not None and evaluate_diff_module.has_llm_calls(cached):
        return cached

    diff = diff_payload["diff"]
    removed_md, added_md = simple_diff_tables(simple_diff_payload)

    with ThreadPoolExecutor(max_workers=2) as executor:
        stats_future = executor.submit(
            evaluate_diff_module.get_statistics_summary, diff["stats"]
        )
        summary_future = executor.submit(
            evaluate_diff_module.get_assignments_summary, removed_md, added_md
        )
        statistics_summary = stats_future.result()
        summary = summary_future.result()

    assessment = evaluate_diff_module.get_assessment(
        summary["änderungen"], statistics_summary["relevant_changes"]
    )
    assessment["änderungen"] = summary["änderungen"]
    assessment["statistiken"] = statistics_summary
    evaluate_diff_module.add_llm_calls(
        assessment,
        statistics_summary=evaluate_diff_module.pop_llm_call(
            statistics_summary, "statistics_summary"
        ),
        assignments_summary=evaluate_diff_module.pop_llm_call(
            summary, "assignments_summary"
        ),
        assessment=evaluate_diff_module.pop_llm_call(assessment, "assessment"),
    )

    cache_result(cache_key, assessment)
    return assessment


def evaluate_simple_diff_direct(
    simple_diff_payload: Dict[str, Any], diff_path: str
) -> Dict[str, Any]:
    removed_md, added_md = simple_diff_tables(simple_diff_payload)
    plan_diff = (
        f"entfernte Zuordnungen:\n{removed_md}\n\n"
        f"hinzugefügte Zuordnungen:\n{added_md}"
    )
    cache_key = experiment_cache_key("simple_direct", diff_path)
    cached = retrieve_cached_result(cache_key)
    if cached is not None and evaluate_diff_module.has_llm_calls(cached):
        return cached

    assessment = get_direct_assessment(plan_diff)
    cache_result(cache_key, assessment)
    return assessment


def output_path(
    mode: EvaluationMode, date_folder: str, filename: str, model_name: str = model
) -> str:
    model_slug = sanitize_model_name(model_name)
    return os.path.join(CACHE_EVALUATIONS, f"{mode}__{model_slug}", date_folder, filename)


def build_result(
    mode: EvaluationMode,
    date_folder: str,
    parent_index: int,
    child_index: int,
    diff_path: str,
    simple_diff_path: Optional[str],
    assessment: Dict[str, Any],
) -> Dict[str, Any]:
    relative_diff_ref = os.path.join(
        CACHE_ROOT, "cache_diffs", date_folder, os.path.basename(diff_path)
    ).replace("\\", "/")
    result: Dict[str, Any] = {
        "date": date_folder,
        "recommendation_index": child_index,
        "parent_index": parent_index,
        "diff_reference": relative_diff_ref,
        "evaluation_mode": mode,
        "model": model,
        "assessment": assessment,
    }
    if simple_diff_path is not None:
        result["simple_diff_reference"] = os.path.join(
            CACHE_ROOT,
            "cache_simple_diffs",
            date_folder,
            os.path.basename(simple_diff_path),
        ).replace("\\", "/")
    return result


def iter_diff_files(allowed_diff_keys: set[str] | None = None) -> List[Tuple[str, str]]:
    entries: List[Tuple[str, str]] = []
    if not os.path.isdir(CACHE_DIFFS):
        return entries

    for date_folder in sorted(os.listdir(CACHE_DIFFS)):
        date_path = os.path.join(CACHE_DIFFS, date_folder)
        if not os.path.isdir(date_path):
            continue
        for filename in sorted(os.listdir(date_path)):
            if not filename.endswith(".json"):
                continue
            diff_key = f"{date_folder}/{filename}"
            if allowed_diff_keys is not None and diff_key not in allowed_diff_keys:
                continue
            entries.append((date_folder, os.path.join(date_path, filename)))
    return entries


def run_evaluation(mode: EvaluationMode, diff_path: str, date_folder: str) -> Dict[str, Any]:
    filename = os.path.basename(diff_path)
    out_path = output_path(mode, date_folder, filename)
    if os.path.exists(out_path):
        cached_result = load_json(out_path)
        if evaluate_diff_module.has_llm_calls(cached_result.get("assessment", {})):
            print(f"  [{mode}] cached: {date_folder}/{filename}")
            return cached_result
        print(f"  [{mode}] refreshing tokens: {date_folder}/{filename}")

    indices = parse_diff_filename(filename)
    if indices is None:
        raise ValueError(f"Unrecognized diff filename: {filename}")

    parent_index, child_index = indices
    diff_payload = load_json(diff_path)
    simple_diff_path = os.path.join(CACHE_SIMPLE_DIFFS, date_folder, filename)
    simple_diff_payload = (
        load_json(simple_diff_path) if os.path.exists(simple_diff_path) else None
    )

    if mode == "full":
        assessment = evaluate_full_diff(diff_payload, diff_path)
        simple_ref = simple_diff_path if os.path.exists(simple_diff_path) else None
    elif mode == "simple":
        if simple_diff_payload is None:
            raise FileNotFoundError(f"Missing simple diff for {diff_path}")
        assessment = evaluate_simple_diff(diff_payload, simple_diff_payload, diff_path)
        simple_ref = simple_diff_path
    else:
        if simple_diff_payload is None:
            raise FileNotFoundError(f"Missing simple diff for {diff_path}")
        assessment = evaluate_simple_diff_direct(simple_diff_payload, diff_path)
        simple_ref = simple_diff_path

    result = build_result(
        mode,
        date_folder,
        parent_index,
        child_index,
        diff_path,
        simple_ref,
        assessment,
    )
    save_json(out_path, result)
    print(f"  [{mode}] evaluated: {date_folder}/{filename}")
    return result


def evaluate_all_experiment_diffs() -> Dict[str, Any]:
    allowed_diff_keys = load_balanced_diff_keys()
    summary: Dict[str, Any] = {
        "model": model,
        "modes": list(EVALUATION_MODES),
        "balanced_sample_n": len(allowed_diff_keys),
        "dates": {},
        "total_evaluations": 0,
    }

    for date_folder, diff_path in iter_diff_files(allowed_diff_keys):
        if date_folder not in summary["dates"]:
            summary["dates"][date_folder] = {mode: 0 for mode in EVALUATION_MODES}

        for mode in EVALUATION_MODES:
            with tracer.start_as_current_span(
                f"evaluate_experiment_{mode}", openinference_span_kind="agent"
            ) as span:
                span.set_input({"diff_path": diff_path, "mode": mode})
                try:
                    result = run_evaluation(mode, diff_path, date_folder)
                    span.set_output(result["assessment"])
                    span.set_status(StatusCode.OK)
                    summary["dates"][date_folder][mode] += 1
                    summary["total_evaluations"] += 1
                except Exception as exc:
                    span.set_status(StatusCode.ERROR, str(exc))
                    print(f"  [{mode}] ERROR {date_folder}/{os.path.basename(diff_path)}: {exc}")

    save_json(os.path.join(CACHE_EVALUATIONS, "summary.json"), summary)
    return summary


def main() -> None:
    args = parse_args()
    configure_llm(base_url=args.base_url, model_name=args.model)

    os.makedirs(CACHE_EVALUATIONS, exist_ok=True)
    base_url_info = args.base_url or os.getenv("OPENAI_BASE_URL") or "default (OpenAI)"
    allowed_diff_keys = load_balanced_diff_keys()
    print(
        f"Evaluating experiment diffs with model={model}, base_url={base_url_info}, "
        f"balanced_sample_n={len(allowed_diff_keys)}"
    )
    summary = evaluate_all_experiment_diffs()
    print(
        f"\nDone. {summary['total_evaluations']} evaluations written to "
        f"{CACHE_EVALUATIONS}/"
    )


if __name__ == "__main__":
    main()