"""Configuration for the API server.

This module contains the configuration classes for the API server. The configuration
can be modified using environment variables with the prefix SERVER_. For example,
to change the port, set the environment variable SERVER_PORT=8001.
"""

# Default logging configuration
DEFAULT_LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
    },
    'handlers': {
        'default': {
            'level': 'INFO',
            'formatter': 'standard',
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['default'],
        'level': 'INFO',
    }
}

class BaseAppConfig:
    """Base configuration for the app.
    
    All configuration values can be overridden using environment variables
    with the prefix SERVER_. For example, to change the port:
    SERVER_PORT=8001
    """
    DEBUG: bool = True
    """Enable/disable debug mode"""
    
    TESTING: bool = True
    """Enable/disable testing mode"""
    
    SECRET_KEY: str = "secret"
    """Secret key for session management"""
    
    DB_TYPE: str = "sqlite"
    """Database type (sqlite, postgres, etc.)"""
    
    HOST: str = "0.0.0.0"
    """Host to bind the server to"""
    
    PORT: int = 8000
    """Port to bind the server to"""
    
    ENV_PREFIX: str = "SERVER"
    """Prefix for environment variables"""
    
    LOGGING_CONFIG: dict = DEFAULT_LOGGING_CONFIG
    """Logging configuration"""


class LocalAppConfig(BaseAppConfig):
    """Local development configuration.
    
    Inherits from BaseAppConfig and overrides some values for local development.
    """
    TESTING: bool = False


class ProductionAppConfig(BaseAppConfig):
    """Production configuration.
    
    Inherits from BaseAppConfig and overrides values for production deployment.
    """
    DEBUG: bool = False
    TESTING: bool = False
    SECRET_KEY: str = "production"


configs = {
    "local": LocalAppConfig,
    "production": ProductionAppConfig
} 