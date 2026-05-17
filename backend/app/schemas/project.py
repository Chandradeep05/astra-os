from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    project_type: str = "general"
    metadata: Optional[Dict[str, Any]] = None
    history: Optional[List[Dict[str, Any]]] = Field(default_factory=list)

class ProjectCreate(ProjectBase):
    pass

class Project(ProjectBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_accessed_at: datetime = Field(default_factory=datetime.utcnow)
    active: bool = True

    class Config:
        from_attributes = True

class ProjectUpdate(ProjectBase):
    name: Optional[str] = None
    project_type: Optional[str] = None
    active: Optional[bool] = None
    history: Optional[List[Dict[str, Any]]] = None
