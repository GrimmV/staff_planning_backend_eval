from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional, Tuple
from llm.helper.helper import get_model_name
from llm.helper.init_phoenix import init_phoenix
from llm.prompts.AssessmentPrompt import ASSESSMENT_PROMPT
from llm.response_models.Assessment import Assessment
from typing import List
from opentelemetry.trace import StatusCode
from llm.helper.cache import retrieve_cached_result, cache_result
from llm.response_models.Summary import TabelleSummary
from llm.prompts.Summary import SUMMARY_PROMPT
from llm.prompts.StatisticsSummary import STATISTICS_SUMMARY_PROMPT
from llm.response_models.StatisticsSummary import StatisticsSummary

client, tracer = init_phoenix(project_name="staff-planning-v2")

model = get_model_name() or "gpt-5.4"
LLM_CALLS_KEY = "llm_calls"
LLM_CALL_KEY = "_llm_call"


def extract_token_usage(response: Any = None, completion: Any = None) -> Optional[Dict[str, int]]:
    usage = getattr(completion, "usage", None)
    if usage is None and response is not None:
        usage = getattr(response, "usage", None)
    if usage is None and response is not None:
        raw_response = getattr(response, "_raw_response", None)
        usage = getattr(raw_response, "usage", None) if raw_response is not None else None
    if usage is None:
        return None

    input_tokens = getattr(usage, "prompt_tokens", None)
    output_tokens = getattr(usage, "completion_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)
    if input_tokens is None or output_tokens is None:
        return None

    token_usage = {
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
    }
    if total_tokens is not None:
        token_usage["total_tokens"] = int(total_tokens)
    return token_usage


def create_structured_completion(**kwargs: Any) -> Tuple[Any, Optional[Dict[str, int]]]:
    create_with_completion = getattr(
        client.chat.completions, "create_with_completion", None
    )
    if callable(create_with_completion):
        response, completion = create_with_completion(**kwargs)
        return response, extract_token_usage(response=response, completion=completion)

    response = client.chat.completions.create(**kwargs)
    return response, extract_token_usage(response=response)


def has_llm_calls(payload: Dict[str, Any]) -> bool:
    llm_calls = payload.get(LLM_CALLS_KEY)
    return isinstance(llm_calls, dict) and bool(llm_calls)


def pop_llm_call(payload: Dict[str, Any], call_name: str) -> Optional[Dict[str, Any]]:
    llm_call = payload.pop(LLM_CALL_KEY, None)
    if llm_call is None:
        return None
    return {"call_name": call_name, **llm_call}


def add_llm_calls(payload: Dict[str, Any], **calls: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload[LLM_CALLS_KEY] = {
        name: call_payload for name, call_payload in calls.items() if call_payload is not None
    }
    return payload

def evaluate_diff(diff: Dict, new_mas: List[str]) -> Dict:

    setting_str = f"diff: {diff}, new_mas: {new_mas}"
    cached_result = retrieve_cached_result(setting_str)
    if cached_result is not None and has_llm_calls(cached_result):
        print(f"Cached result found")
        return cached_result

    vorher = diff["vorher"]
    nachher = diff["nachher"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        stats_future = executor.submit(get_statistics_summary, diff["stats"])
        summary_future = executor.submit(get_assignments_summary, vorher, nachher)
        statistics_summary = stats_future.result()
        summary = summary_future.result()

    assessment = get_assessment(summary["änderungen"], statistics_summary["relevant_changes"])
    
    assessment["änderungen"] = summary["änderungen"]
    assessment["statistiken"] = statistics_summary
    add_llm_calls(
        assessment,
        statistics_summary=pop_llm_call(statistics_summary, "statistics_summary"),
        assignments_summary=pop_llm_call(summary, "assignments_summary"),
        assessment=pop_llm_call(assessment, "assessment"),
    )

    cache_result(setting_str, assessment)
    return assessment

def get_statistics_summary(diff_stats) -> Dict:
    with tracer.start_as_current_span(
        "statistics_summary", openinference_span_kind="chain"
    ) as span:
        prompt = STATISTICS_SUMMARY_PROMPT.format(
            diff_stats=diff_stats
        )
        span.set_input(prompt)
        response, token_usage = create_structured_completion(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            response_model=StatisticsSummary,
            temperature=0.7,
            top_p=0.8,
            presence_penalty=1.5,
            extra_body={
                "top_k": 20,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
        span.set_output(response.model_dump())
        span.set_status(StatusCode.OK)
        statistics_summary = response.model_dump()
        if token_usage is not None:
            statistics_summary[LLM_CALL_KEY] = token_usage
    return statistics_summary

def get_assignments_summary(vorher, nachher) -> Dict:
    with tracer.start_as_current_span(
        "summary", openinference_span_kind="chain"
    ) as span:
        prompt = SUMMARY_PROMPT.format(
            plan_diff=f"vorher: {vorher}, nachher: {nachher}"
        )
        span.set_input(prompt)
        response, token_usage = create_structured_completion(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            response_model=TabelleSummary,
            temperature=0.7,
            top_p=0.8,
            presence_penalty=1.5,
            extra_body={
                "top_k": 20,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
        span.set_output(response.model_dump())
        span.set_status(StatusCode.OK)
        summary = response.model_dump()
        if token_usage is not None:
            summary[LLM_CALL_KEY] = token_usage
    return summary

def get_assessment(summary_änderungen, diff_stats) -> Dict:
    with tracer.start_as_current_span(
        "assessment", openinference_span_kind="chain"
    ) as span:
        prompt = ASSESSMENT_PROMPT.format(
            plan_diff=f"relevanteste Veränderungen: {summary_änderungen}, statistiken: {diff_stats}"
        )
        span.set_input(prompt)
        response, token_usage = create_structured_completion(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            response_model=Assessment,
            temperature=0.7,
            top_p=0.8,
            presence_penalty=1.5,
            extra_body={
                "top_k": 20,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
        span.set_output(response.model_dump())
        span.set_status(StatusCode.OK)
        assessment = response.model_dump()
        if token_usage is not None:
            assessment[LLM_CALL_KEY] = token_usage
    
    return assessment

if __name__ == "__main__":
    from calculate_diff import calculate_diff

    diff, new_mas = calculate_diff(
        "dc4f6682-5418-4e69-b08e-eded0d66b060", "f3bf2472-89c6-4bd0-bd31-b092a48a89c3"
    )
    with tracer.start_as_current_span(
        "evaluate_diff", openinference_span_kind="agent"
    ) as span:
        span.set_input(diff)
        assessment = evaluate_diff(diff, new_mas)
        span.set_output(assessment)
        span.set_status(StatusCode.OK)
    print(assessment)
