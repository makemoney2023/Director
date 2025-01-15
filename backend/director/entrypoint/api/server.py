import logging
import logging.config
import os
from dotenv import load_dotenv
from director.entrypoint.api import create_app
from director.entrypoint.api.config import configs

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

# By default, the server is configured to run in development mode. To run in production mode, set the `SERVER_ENV` environment variable to `production`.
app = create_app(app_config=configs[os.getenv("SERVER_ENV", "local")])

if __name__ == "__main__":
    socketio = app.socketio
    socketio.run(
        app,
        host=os.getenv("SERVER_HOST", app.config["HOST"]),
        port=os.getenv("SERVER_PORT", app.config["PORT"]),
        debug=app.config["DEBUG"]
    )
