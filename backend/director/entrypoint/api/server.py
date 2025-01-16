import os
import sys
import logging
import logging.config
from dotenv import load_dotenv
from director.entrypoint.api import create_app
from director.entrypoint.api.config import configs
from director.core.database import init_db
from flask import Flask
from flask_socketio import SocketIO

load_dotenv()

# Configure logging
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

logging.config.dictConfig(DEFAULT_LOGGING_CONFIG)
logger = logging.getLogger(__name__)

# Create the Flask application
app = create_app(app_config=configs[os.getenv("SERVER_ENV", "local")])

if __name__ == "__main__":
    socketio = app.socketio
    socketio.run(
        app,
        host=os.getenv("SERVER_HOST", app.config["HOST"]),
        port=os.getenv("SERVER_PORT", app.config["PORT"]),
        debug=app.config["DEBUG"],
        use_reloader=True
    )
