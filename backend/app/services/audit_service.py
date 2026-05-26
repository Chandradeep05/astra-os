import logging
from sqlmodel import Session
from app.db import engine
from app.models.audit import AuditLogModel
from datetime import datetime

logger = logging.getLogger(__name__)

class AuditService:
    def log_action(self, action_type: str, details: str, project_id: str = "default"):
        """Logs an action securely into the local SQLite database for compliance auditing."""
        try:
            with Session(engine) as session:
                log_entry = AuditLogModel(
                    project_id=project_id,
                    action_type=action_type,
                    details=details,
                    created_at=datetime.utcnow()
                )
                session.add(log_entry)
                session.commit()
        except Exception as e:
            logger.error(f"Audit Log failed: {e}")

    def log_approval(self, tool_name: str, approved: bool, task_id: str = "", project_id: str = "default"):
        """Log a tool approval/rejection event into the audit trail."""
        status = "APPROVED" if approved else "REJECTED"
        details = f"Tool '{tool_name}' {status.lower()} by user"
        if task_id:
            details += f" (task_id: {task_id})"
        self.log_action(
            action_type="TOOL_APPROVAL",
            details=details,
            project_id=project_id,
        )

audit_service = AuditService()
