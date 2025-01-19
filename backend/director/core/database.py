"""Tools module for Director."""

from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

Base = declarative_base()

class Analysis(Base):
    """Model for storing raw analysis data"""
    __tablename__ = 'analysis'
    
    id = Column(Integer, primary_key=True)
    video_id = Column(String(255), nullable=False)
    collection_id = Column(String(255), nullable=False)
    transcript = Column(Text)
    raw_analysis = Column(Text)
    status = Column(String(50), default='pending')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    meta_data = Column(JSON)
    
    # Relationships
    structured_data = relationship("StructuredData", back_populates="analysis", uselist=False)
    yaml_config = relationship("YAMLConfig", back_populates="analysis", uselist=False)
    voice_prompt = relationship("VoicePrompt", back_populates="analysis", uselist=False)

class StructuredData(Base):
    """Model for storing structured analysis data"""
    __tablename__ = 'structured_data'
    
    id = Column(Integer, primary_key=True)
    analysis_id = Column(Integer, ForeignKey('analysis.id'))
    data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    analysis = relationship("Analysis", back_populates="structured_data")

class YAMLConfig(Base):
    """Model for storing YAML configuration"""
    __tablename__ = 'yaml_config'
    
    id = Column(Integer, primary_key=True)
    analysis_id = Column(Integer, ForeignKey('analysis.id'))
    config = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    analysis = relationship("Analysis", back_populates="yaml_config")

class VoicePrompt(Base):
    """Model for storing generated voice prompts"""
    __tablename__ = 'voice_prompt'
    
    id = Column(Integer, primary_key=True)
    analysis_id = Column(Integer, ForeignKey('analysis.id'))
    prompt = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    analysis = relationship("Analysis", back_populates="voice_prompt")

# Database setup
def init_db(db_url=None):
    """Initialize database connection"""
    if db_url is None:
        db_url = os.getenv('DATABASE_URL', 'sqlite:///director.db')
    
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)  # This will create any missing tables/columns
    Session.configure(bind=engine)
    return Session

# Create Session class - but don't bind it yet
Session = sessionmaker()

# Initialize the database and bind session on import
engine = create_engine(
    os.getenv('DATABASE_URL', 'sqlite:///director.db'),
    connect_args={'check_same_thread': False},  # Allow SQLite to be used with multiple threads
    pool_size=20,  # Set a reasonable pool size
    max_overflow=0,  # Prevent pool overflow
    pool_pre_ping=True,  # Enable connection health checks
    pool_recycle=3600  # Recycle connections after 1 hour
)
Base.metadata.create_all(engine)
Session.configure(bind=engine) 