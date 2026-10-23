"""
Configuration management using environment variables.
"""
import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Keys
    groq_api_key: str = ""        # kept for reference; unused when ollama_enabled=True
    sarvam_api_key: str = ""

    # OCR Configuration
    ocr_backend: str = "tesseract"  # Options: tesseract, paddleocr
    tesseract_languages: str = "tam+eng"

    # LLM Configuration — Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096
    
    # Image Generation
    sd_model: str = "runwayml/stable-diffusion-v1-5"
    use_fp16: bool = True
    enable_attention_slicing: bool = True
    safety_checker_enabled: bool = False
    
    # Database
    database_url: str = "sqlite:///./storyboard.db"
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    
    # File Storage
    upload_dir: Path = Path("./uploads")
    output_dir: Path = Path("./outputs")
    static_dir: Path = Path("./static")
    
    # Session
    session_cookie_name: str = "storyboard_session"
    session_max_age: int = 86400  # 24 hours
    
    # Export
    pdf_page_size: str = "A4"
    pptx_slide_size: str = "16:9"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Create directories if they don't exist
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.static_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings
