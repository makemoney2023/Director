"""
Initialize the app

Create an application factory function, which will be used to create a new app instance.

docs: https://flask.palletsprojects.com/en/2.3.x/patterns/appfactories/
"""

from flask_cors import CORS
from flask import Flask
from flask_socketio import SocketIO
from logging.config import dictConfig

from director.entrypoint.api.routes import (
    agent_bp, session_bp, videodb_bp, config_bp, bland_ai_bp
)
from director.entrypoint.api.socket_io import ChatNamespace

from dotenv import load_dotenv

load_dotenv()

socketio = SocketIO()

def create_app(app_config=None):
    """
    Create a Flask app using the app factory pattern.

    :param app_config: The configuration object to use.
    :return: A Flask app.
    """
    app = Flask(__name__)

    if app_config:
        app.config.from_object(app_config)

    # Initialize SocketIO with threading
    socketio.init_app(
        app,
        async_mode='threading',
        cors_allowed_origins="*",
        logger=True,
        engineio_logger=True,
        ping_timeout=60
    )
    app.socketio = socketio

    # Enable CORS
    CORS(app)

    # Set the logging config
    dictConfig(app.config["LOGGING_CONFIG"])

    with app.app_context():
        from director.entrypoint.api import errors

    # register blueprints
    app.register_blueprint(agent_bp)
    app.register_blueprint(session_bp)
    app.register_blueprint(videodb_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(bland_ai_bp)

    # register socket namespaces
    socketio.on_namespace(ChatNamespace("/chat"))

    return app
