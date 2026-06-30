from openai import OpenAI
import instructor
from phoenix.otel import register
from opentelemetry.instrumentation.openai import OpenAIInstrumentor
from .helper import get_openai_api_key, get_openai_base_url, get_phoenix_endpoint


def init_phoenix(project_name: str = "staff-planning-v1", base_url: str | None = None):
    openai_api_key = get_openai_api_key()
    resolved_base_url = base_url or get_openai_base_url()

    client_kwargs: dict = {}
    if openai_api_key:
        client_kwargs["api_key"] = openai_api_key
    if resolved_base_url:
        client_kwargs["base_url"] = resolved_base_url

    client = instructor.from_openai(OpenAI(**client_kwargs))

    PROJECT_NAME = project_name

    PHOENIX_ENDPOINT = get_phoenix_endpoint()


    tracer_provider = register(
        project_name=PROJECT_NAME,
        endpoint= PHOENIX_ENDPOINT + "v1/traces",
        
    )

    OpenAIInstrumentor().instrument(tracer_provider = tracer_provider)

    tracer = tracer_provider.get_tracer(__name__)
    
    return client, tracer
