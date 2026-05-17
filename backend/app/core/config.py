import os
import secrets
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "ASTRA OS"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENV: str = "development"
    
    # LLM Settings
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    DEFAULT_MODEL: str = "qwen2.5:3b"
    
    # Database (Supabase / Postgres)
    DATABASE_URL: str = "sqlite:///./astra_os.db"
    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None
    
    # Vector DB / Context
    CHROMA_DB_PATH: str = "./chroma_db"
    
    # Security
    ALLOWED_ORIGINS: str = "http://localhost:3000"
    SECRET_KEY: str = secrets.token_urlsafe(64)  # Auto-generate if not in .env
    
    # External APIs
    SERPER_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    
    # System
    LOG_LEVEL: str = "INFO"
    PORT: int = 8000
    MAX_UPLOAD_SIZE_MB: int = 100

    
    model_config = SettingsConfigDict(
        env_file=".env", 
        case_sensitive=False,
        extra="allow",
        env_ignore_empty=True
    )

    from pydantic import model_validator
    
    @model_validator(mode="after")
    def check_security_config(self):
        if self.SECRET_KEY == "CHANGE_ME_TO_A_RANDOM_64_CHAR_STRING":
            raise ValueError("Insecure SECRET_KEY detected in .env file! App startup blocked.")
        if self.ALLOWED_ORIGINS == "*":
            raise ValueError("Insecure ALLOWED_ORIGINS='*' detected! Provide specific domains.")
        return self

settings = Settings()
