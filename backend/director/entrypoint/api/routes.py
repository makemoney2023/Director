import os

from flask import Blueprint, request, current_app as app
from werkzeug.utils import secure_filename

from director.db import load_db
from director.handler import ChatHandler, SessionHandler, VideoDBHandler, ConfigHandler
from director.agents.sales_prompt_extractor import SalesPromptExtractorAgent
from director.core.session import Session
from director.integrations.bland_ai.handler import BlandAIIntegrationHandler


agent_bp = Blueprint("agent", __name__, url_prefix="/agent")
session_bp = Blueprint("session", __name__, url_prefix="/session")
videodb_bp = Blueprint("videodb", __name__, url_prefix="/videodb")
config_bp = Blueprint("config", __name__, url_prefix="/config")
bland_ai_bp = Blueprint("bland-ai", __name__, url_prefix="/api/v1/bland-ai")


@agent_bp.route("/", methods=["GET"], strict_slashes=False)
def agent():
    """
    Handle the agent request
    """
    chat_handler = ChatHandler(
        db=load_db(os.getenv("SERVER_DB_TYPE", app.config["DB_TYPE"]))
    )
    return chat_handler.agents_list()


@agent_bp.route("/sales-prompt", methods=["POST"], strict_slashes=False)
async def analyze_sales_video():
    """
    Analyze a video for sales techniques and generate prompts
    """
    data = request.get_json()
    video_id = data.get("video_id")
    analysis_type = data.get("analysis_type", "full")
    output_format = data.get("output_format", "both")

    # Create a new session for this analysis
    session = Session()
    
    # Initialize the agent directly
    agent = SalesPromptExtractorAgent(session)

    # If no video_id, return initial response
    if not video_id:
        result = await agent.run(video_id=None)
        return {
            "status": result.status,
            "message": result.message,
            "data": result.data,
            "session_id": session.id
        }

    # Validate parameters
    valid_analysis_types = ["sales_techniques", "communication", "full"]
    valid_output_formats = ["structured", "text", "both"]

    if analysis_type not in valid_analysis_types:
        return {
            "message": f"Invalid analysis_type. Must be one of: {', '.join(valid_analysis_types)}"
        }, 400

    if output_format not in valid_output_formats:
        return {
            "message": f"Invalid output_format. Must be one of: {', '.join(valid_output_formats)}"
        }, 400

    # Run the analysis and return the raw agent response
    result = await agent.run(
        video_id=video_id, 
        analysis_type=analysis_type, 
        output_format=output_format
    )
    
    # Return the raw agent response without reasoning engine processing
    return {
        "status": result.status,
        "message": result.message,
        "data": result.data,
        "session_id": session.id
    }


@session_bp.route("/", methods=["GET"], strict_slashes=False)
def get_sessions():
    """
    Get all the sessions
    """
    session_handler = SessionHandler(
        db=load_db(os.getenv("SERVER_DB_TYPE", app.config["DB_TYPE"]))
    )
    return session_handler.get_sessions()


@session_bp.route("/<session_id>", methods=["GET", "DELETE"])
def get_session(session_id):
    """
    Get or delete the session details
    """
    if not session_id:
        return {"message": f"Please provide {session_id}."}, 400

    session_handler = SessionHandler(
        db=load_db(os.getenv("SERVER_DB_TYPE", app.config["DB_TYPE"]))
    )
    session = session_handler.get_session(session_id)
    if not session:
        return {"message": "Session not found."}, 404

    if request.method == "GET":
        return session
    elif request.method == "DELETE":
        success, failed_components = session_handler.delete_session(session_id)
        if success:
            return {"message": "Session deleted successfully."}, 200
        else:
            return {
                "message": f"Failed to delete the entry for following components: {', '.join(failed_components)}"
            }, 500


@videodb_bp.route("/collection", defaults={"collection_id": None}, methods=["GET"])
@videodb_bp.route("/collection/<collection_id>", methods=["GET"])
def get_collection_or_all(collection_id):
    """Get a collection by ID or all collections."""
    videodb = VideoDBHandler(collection_id)
    if collection_id:
        return videodb.get_collection()
    else:
        return videodb.get_collections()


@videodb_bp.route(
    "/collection/<collection_id>/video", defaults={"video_id": None}, methods=["GET"]
)
@videodb_bp.route("/collection/<collection_id>/video/<video_id>", methods=["GET"])
def get_video_or_all(collection_id, video_id):
    """Get a video by ID or all videos in a collection."""
    videodb = VideoDBHandler(collection_id)
    if video_id:
        return videodb.get_video(video_id)
    else:
        return videodb.get_videos()


@videodb_bp.route("/collection/<collection_id>/upload", methods=["POST"])
def upload_video(collection_id):
    """Upload a video to a collection."""
    try:
        videodb = VideoDBHandler(collection_id)

        if "file" in request.files:
            file = request.files["file"]
            file_bytes = file.read()
            safe_filename = secure_filename(file.filename)
            if not safe_filename:
                return {"message": "Invalid filename"}, 400
            file_name = os.path.splitext(safe_filename)[0]
            media_type = file.content_type.split("/")[0]
            return videodb.upload(
                source=file_bytes,
                source_type="file",
                media_type=media_type,
                name=file_name,
            )
        elif "source" in request.json:
            source = request.json["source"]
            source_type = request.json["source_type"]
            return videodb.upload(source=source, source_type=source_type)
        else:
            return {"message": "No valid source provided"}, 400
    except Exception as e:
        return {"message": str(e)}, 500


@config_bp.route("/check", methods=["GET"])
def config_check():
    config_handler = ConfigHandler()
    return config_handler.check()


@bland_ai_bp.route("/process-recording", methods=["POST"])
async def process_recording():
    """Process a sales recording and create a new Bland AI pathway"""
    try:
        data = request.get_json()
        handler = BlandAIIntegrationHandler(app.config)
        result = await handler.process_sales_recording(recording_data=data)
        return result
    except Exception as e:
        return {"message": str(e)}, 500


@bland_ai_bp.route("/update-pathway", methods=["POST"])
async def update_pathway():
    """Update an existing Bland AI pathway with new sales recording data"""
    try:
        data = request.get_json()
        handler = BlandAIIntegrationHandler(app.config)
        result = await handler.process_sales_recording(
            recording_data=data["recording_data"],
            update_existing=True,
            pathway_id=data["pathway_id"]
        )
        return result
    except Exception as e:
        return {"message": str(e)}, 500


@bland_ai_bp.route("/pathways", methods=["GET"])
async def list_pathways():
    """Get list of available Bland AI pathways"""
    try:
        handler = BlandAIIntegrationHandler(app.config)
        pathways = await handler.list_available_pathways()
        return pathways
    except Exception as e:
        return {"message": str(e)}, 500


@bland_ai_bp.route("/pathways/<pathway_id>/stats", methods=["GET"])
async def get_pathway_stats(pathway_id):
    """Get statistics about a specific pathway"""
    try:
        handler = BlandAIIntegrationHandler(app.config)
        stats = await handler.get_pathway_stats(pathway_id)
        return stats
    except Exception as e:
        return {"message": str(e)}, 500
