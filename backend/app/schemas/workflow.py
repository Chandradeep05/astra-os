from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

class WorkflowBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    project_id: str
    type: str = "automation"
    trigger_type: str = "manual"
    trigger_config: Optional[str] = None
    status: str = "active"
    steps: Optional[List[str]] = Field(default_factory=list) # List of natural language directives

class WorkflowCreate(WorkflowBase):
    pass

class Workflow(WorkflowBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_run: Optional[datetime] = None

    class Config:
        from_attributes = True

class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_config: Optional[str] = None
