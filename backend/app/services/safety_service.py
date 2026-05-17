import re
import logging

logger = logging.getLogger(__name__)

class SafetyService:
    def __init__(self):
        # Basic patterns for MVP PII redaction (Enterprise Tier 3 Requirement)
        self.patterns = {
            "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
            "CREDIT_CARD": r"\b(?:\d{4}[ -]?){3}\d{4}\b",
        }
        
    def check_and_redact(self, text: str) -> str:
        """
        Scans input for sensitive local data before routing strings.
        Redacts them to prevent models from learning or exposing PII.
        """
        redacted_text = text
        for pii_type, pattern in self.patterns.items():
            if re.search(pattern, redacted_text):
                logger.warning(f"PII Detected and Redacted: {pii_type}")
                redacted_text = re.sub(pattern, f"[REDACTED_{pii_type}]", redacted_text)
                
        return redacted_text

safety_service = SafetyService()
