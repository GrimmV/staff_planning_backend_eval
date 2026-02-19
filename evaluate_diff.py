from concurrent.futures import ThreadPoolExecutor
from typing import Dict
from calculate_diff import calculate_diff
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

model = "gpt-5"


def evaluate_diff(diff: Dict, new_mas: List[str]) -> Dict:

    setting_str = f"diff: {diff}, new_mas: {new_mas}"
    cached_result = retrieve_cached_result(setting_str)
    if cached_result is not None:
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
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            response_model=StatisticsSummary,
        )
        span.set_output(response.model_dump())
        span.set_status(StatusCode.OK)
        statistics_summary = response.model_dump()
    return statistics_summary

def get_assignments_summary(vorher, nachher) -> Dict:
    with tracer.start_as_current_span(
        "summary", openinference_span_kind="chain"
    ) as span:
        prompt = SUMMARY_PROMPT.format(
            plan_diff=f"vorher: {vorher}, nachher: {nachher}"
        )
        span.set_input(prompt)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            response_model=TabelleSummary,
        )
        span.set_output(response.model_dump())
        span.set_status(StatusCode.OK)
        summary = response.model_dump()
    return summary

def get_assessment(summary_änderungen, diff_stats) -> Dict:
    with tracer.start_as_current_span(
        "assessment", openinference_span_kind="chain"
    ) as span:
        prompt = ASSESSMENT_PROMPT.format(
            plan_diff=f"relevanteste Veränderungen: {summary_änderungen}, statistiken: {diff_stats}"
        )
        span.set_input(prompt)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            response_model=Assessment
        )
        span.set_output(response.model_dump())
        span.set_status(StatusCode.OK)
        assessment = response.model_dump()
    
    return assessment

if __name__ == "__main__":
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
