from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    """Application settings"""
    app_name: str = "Stock Trading API"
    debug: bool = True
    api_v1_str: str = "/api/v1"
    
    # Database
    database_url: Optional[str] = None
    
    # CORS
    backend_cors_origins: list = ["http://localhost:3000", "http://localhost:5173"]
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
