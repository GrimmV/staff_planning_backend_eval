from typing import Dict
from calculate_diff import calculate_diff
from llm.helper.init_phoenix import init_phoenix
from llm.prompts.AssessmentPrompt import ASSESSMENT_PROMPT
from llm.response_models.Assessment import Assessment

def evaluate_diff(diff: Dict) -> Dict:
    
    client, tracer = init_phoenix(project_name="staff-planning-v2")
    
    with tracer.start_as_current_span(
        "assessment", openinference_span_kind="agent"
    ) as span:
        span.set_input(diff)
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {
                    "role": "user",
                    "content": ASSESSMENT_PROMPT.format(
                        plan_diff=f"hinzugefügt: {diff['hinzugefügt']}, entfernt: {diff['entfernt']}"
                    ),
                }
            ],
            response_model=Assessment,
        )
        span.set_output(response.model_dump())
        assessment = response.model_dump()
    
    return assessment

if __name__ == "__main__":
    diff = calculate_diff("dc4f6682-5418-4e69-b08e-eded0d66b060", "f3bf2472-89c6-4bd0-bd31-b092a48a89c3")
    assessment = evaluate_diff(diff)
    print(assessment)