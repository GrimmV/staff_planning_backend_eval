from dotenv import load_dotenv
import os
from llm.chat.response_model.chat_response import ChatResponseModel
from llm.chat.prompt.chat_add import CHAT_ADD_PROMPT
from llm.helper.init_phoenix import init_phoenix
from opentelemetry.trace import StatusCode

client, tracer = init_phoenix(project_name="staff-planning-v2")

load_dotenv(override=True)

model_name = os.getenv("MODEL_NAME")

def chat(prompt):
    with tracer.start_as_current_span(
        "chat", openinference_span_kind="chain"
    ) as span:
        span.set_input(prompt)
        completion = client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {
                                "role": "system",
                                "content": f"Du bist ein Experte für die Personalplanung und versuchst die Anfragen des Personalmanagements so klar und direkt zu beantworten wie möglich. \n\n{CHAT_ADD_PROMPT}",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        response_model=ChatResponseModel,
                    )
        span.set_output(completion.model_dump())
        span.set_status(StatusCode.OK)
    return completion.response