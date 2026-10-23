"""
Database models and session management using SQLAlchemy.
"""
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import create_engine, Column, String, DateTime, Text, Integer, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from backend.config import get_settings

settings = get_settings()

# Create database engine
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {}
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


class Project(Base):
    """Project model representing a user's storyboard project."""
    __tablename__ = "projects"
    
    id = Column(String, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    title = Column(String, nullable=True)
    screenplay_text = Column(Text, nullable=True)
    screenplay_source = Column(String, nullable=True)  # file, text, voice, image
    structured_template = Column(Text, nullable=True)  # JSON
    characters_json = Column(Text, nullable=True)  # JSON list of characters
    shots_json = Column(Text, nullable=True)  # JSON list of shots
    
    def get_characters(self) -> List[Dict[str, Any]]:
        """Parse and return characters from JSON."""
        if self.characters_json:
            return json.loads(self.characters_json)
        return []
    
    def set_characters(self, characters: List[Dict[str, Any]]):
        """Serialize and store characters as JSON."""
        self.characters_json = json.dumps(characters)
    
    def get_shots(self) -> List[Dict[str, Any]]:
        """Parse and return shots from JSON."""
        if self.shots_json:
            return json.loads(self.shots_json)
        return []
    
    def set_shots(self, shots: List[Dict[str, Any]]):
        """Serialize and store shots as JSON."""
        self.shots_json = json.dumps(shots)


class Character(Base):
    """Character model with reference image and embeddings."""
    __tablename__ = "characters"
    
    id = Column(String, primary_key=True, index=True)
    project_id = Column(String, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    reference_type = Column(String)  # uploaded, generated, default
    reference_image_path = Column(String, nullable=True)
    embedding_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Shot(Base):
    """Shot model representing a single storyboard panel."""
    __tablename__ = "shots"
    
    id = Column(String, primary_key=True, index=True)
    project_id = Column(String, index=True)
    sequence_number = Column(Integer)
    shot_type = Column(String)  # wide, medium, close-up, etc.
    camera_angle = Column(String)  # eye-level, high-angle, low-angle, etc.
    characters_json = Column(Text)  # JSON list of character names
    action = Column(Text)
    mood = Column(String, nullable=True)
    image_path = Column(String, nullable=True)
    consistency_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_characters(self) -> List[str]:
        """Parse and return character names from JSON."""
        if self.characters_json:
            return json.loads(self.characters_json)
        return []
    
    def set_characters(self, characters: List[str]):
        """Serialize and store character names as JSON."""
        self.characters_json = json.dumps(characters)


class Export(Base):
    """Export model tracking generated exports."""
    __tablename__ = "exports"
    
    id = Column(String, primary_key=True, index=True)
    project_id = Column(String, index=True)
    format = Column(String)  # pdf, pptx
    file_path = Column(String)
    shareable_link = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Get database session for dependency injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
