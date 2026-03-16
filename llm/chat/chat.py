from openai import OpenAI
from dotenv import load_dotenv
import instructor
import os
from .response_model.chat_response import ChatResponseModel
from .prompt.chat_add import CHAT_ADD_PROMPT

load_dotenv(override=True)

API_KEY = os.getenv("OPENAI_API_KEY")
client = instructor.from_openai(OpenAI(api_key=API_KEY))

model_name = os.getenv("MODEL_NAME")

def chat(prompt):

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
    return completion.response