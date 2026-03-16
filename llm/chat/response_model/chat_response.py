from pydantic import BaseModel

class ChatResponseModel(BaseModel):
    response: str