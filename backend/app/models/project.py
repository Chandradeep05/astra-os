from sqlmodel import SQLModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
import uuid

class ProjectModel(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    project_type: str = Field(default="general")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_accessed_at: datetime = Field(default_factory=datetime.utcnow)
    active: bool = Field(default=True)
    
    # JSON-encoded string for chat history persistence
    history_json: Optional[str] = Field(default="[]")
    metadata_json: Optional[str] = None 
