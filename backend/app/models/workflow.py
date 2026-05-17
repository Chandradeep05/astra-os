from sqlmodel import SQLModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
import uuid

class WorkflowModel(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    project_id: str = Field(index=True)
    type: str = Field(default="automation") # e.g., 'summarization', 'analysis', 'report'
    trigger_type: str = Field(default="manual") # 'manual', 'event', 'cron'
    trigger_config: Optional[str] = None # JSON string for cron or event details
    status: str = Field(default="active") # 'active', 'paused', 'failed'
    steps_json: Optional[str] = Field(default="[]") # JSON list of strings
    last_run: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Optional metadata can be stored as JSON
    metadata_json: Optional[str] = None 
