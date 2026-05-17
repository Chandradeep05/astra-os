from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class AuditLogModel(SQLModel, table=True):
    __tablename__ = "audit_logs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: str = Field(default="default", index=True)
    action_type: str = Field(..., index=True) # E.g., 'CHAT', 'TOOL_EXECUTION', 'FILE_INGESTION'
    details: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
