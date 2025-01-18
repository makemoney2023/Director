"""Configuration for the API server."""

import os
from typing import Dict, Any

class Config:
    """Base configuration class"""
    
    def __init__(self):
        """Initialize configuration with environment variables"""
        self.debug = os.getenv("SERVER_DEBUG", "0") == "1"
        self.host = os.getenv("SERVER_HOST", "0.0.0.0") 
        self.port = int(os.getenv("SERVER_PORT", "8000"))
        
        # API Keys
        self.video_db_api_key = os.getenv("VIDEO_DB_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.bland_ai_api_key = os.getenv("BLAND_AI_API_KEY")
        
        # Database
        self.sqlite_path = os.getenv("SQLITE_DB_PATH", "director.db")
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary"""
        return {
            "debug": self.debug,
            "host": self.host,
            "port": self.port,
            "video_db_configured": bool(self.video_db_api_key),
            "openai_configured": bool(self.openai_api_key),
            "bland_ai_configured": bool(self.bland_ai_api_key),
            "db_configured": True  # SQLite is always configured
        } 