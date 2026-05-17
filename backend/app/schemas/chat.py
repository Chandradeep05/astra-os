from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class ChatMessage(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant|system)$", description="Message role")
    content: str = Field(..., min_length=1, max_length=32000, description="Message content")

class ChatRequest(BaseModel):
    model_name: Optional[str] = "qwen2.5:3b"
    messages: List[ChatMessage]
    project_id: Optional[str] = None
    stream: Optional[bool] = False

class ChatResponse(BaseModel):
    content: str
    model: str
    usage: Optional[Dict[str, Any]] = None
