import os
import logging
from datetime import datetime

from director.agents.thumbnail import ThumbnailAgent
from director.agents.summarize_video import SummarizeVideoAgent
from director.agents.download import DownloadAgent
# from director.agents.pricing import PricingAgent
from director.agents.upload import UploadAgent
from director.agents.search import SearchAgent
from director.agents.prompt_clip import PromptClipAgent
from director.agents.index import IndexAgent
from director.agents.brandkit import BrandkitAgent
# from director.agents.profanity_remover import ProfanityRemoverAgent
# from director.agents.image_generation import ImageGenerationAgent
from director.agents.audio_generation import AudioGenerationAgent
# from director.agents.video_generation import VideoGenerationAgent
from director.agents.stream_video import StreamVideoAgent
from director.agents.subtitle import SubtitleAgent
from director.agents.slack_agent import SlackAgent
from director.agents.editing import EditingAgent
from director.agents.dubbing import DubbingAgent
# from director.agents.text_to_movie import TextToMovieAgent
# from director.agents.meme_maker import MemeMakerAgent
from director.agents.composio import ComposioAgent
from director.agents.transcription import TranscriptionAgent
from director.agents.comparison import ComparisonAgent
from director.agents.web_search_agent import WebSearchAgent
from director.agents.sales_prompt_extractor import SalesPromptExtractorAgent
from director.agents.bland_ai_agent import BlandAI_Agent
from director.agents.base import AgentStatus


from director.core.session import Session, InputMessage, MsgStatus, TextContent
from director.core.reasoning import ReasoningEngine
from director.db.base import BaseDB
from director.db import load_db
from director.tools.videodb_tool import VideoDBTool

logger = logging.getLogger(__name__)


class ChatHandler:
    def __init__(self, db, **kwargs):
        self.db = db
        self.agents = [SalesPromptExtractorAgent, BlandAI_Agent]
        self.last_active_agent = None  # Track the last active agent

        # Register the agents here
        self.agents += [
            ThumbnailAgent,
            SummarizeVideoAgent,
            DownloadAgent,
            # PricingAgent,
            UploadAgent,
            SearchAgent,
            PromptClipAgent,
            IndexAgent,
            BrandkitAgent,
            # ProfanityRemoverAgent,
            # ImageGenerationAgent,
            AudioGenerationAgent,
            # VideoGenerationAgent,
            StreamVideoAgent,
            SubtitleAgent,
            SlackAgent,
            EditingAgent,
            DubbingAgent,
            TranscriptionAgent,
            # TextToMovieAgent,
            # MemeMakerAgent,
            ComposioAgent,
            ComparisonAgent,
            WebSearchAgent,
            # ProfanityRemoverAgent,
            # ImageGenerationAgent,
            # VideoGenerationAgent,
            # MemeMakerAgent,
        ]

    def add_videodb_state(self, session):
        from videodb import connect

        session.state["conn"] = connect(
            base_url=os.getenv("VIDEO_DB_BASE_URL", "https://api.videodb.io")
        )
        session.state["collection"] = session.state["conn"].get_collection(
            session.collection_id
        )
        if session.video_id:
            session.state["video"] = session.state["collection"].get_video(
                session.video_id
            )

    def agents_list(self):
        return [
            {
                "name": agent_instance.name,
                "description": agent_instance.agent_description,
            }
            for agent in self.agents
            for agent_instance in [agent(Session(db=self.db))]
        ]

    def chat(self, message):
        logger.info(f"ChatHandler input message: {message}")

        session = Session(db=self.db, **message)
        session.create()
        input_message = InputMessage(db=self.db, **message)
        input_message.publish()

        try:
            self.add_videodb_state(session)
            agents = [agent(session=session) for agent in self.agents]
            agents_mapping = {agent.name: agent for agent in agents}

            # Check if we should bypass reasoning engine
            if input_message.agents and len(input_message.agents) == 1:
                agent_name = input_message.agents[0]
                self.last_active_agent = agent_name  # Store the active agent
            elif self.last_active_agent and not input_message.agents:
                # If no agents specified but we have a last active agent, use it
                message["agents"] = [self.last_active_agent]
                input_message.agents = [self.last_active_agent]
                agent_name = self.last_active_agent
            else:
                agent_name = None

            if agent_name == "sales_prompt_extractor":
                # Direct agent call for sales_prompt_extractor
                agent = agents_mapping["sales_prompt_extractor"]
                response = agent.run(
                    video_id=session.video_id,
                    collection_id=session.collection_id,
                    bypass_reasoning=True
                )
                # Convert AgentResponse to OutputMessage format
                output_message = {
                    "status": "success" if response.status == AgentStatus.SUCCESS else "error",
                    "message": response.message,
                    "session_id": session.session_id,
                    "conv_id": session.conv_id,
                    "msg_type": "output",
                    "content": [
                        {
                            "type": "text",
                            "text": response.data.get("analysis", response.message),
                            "status": "success" if response.status == AgentStatus.SUCCESS else "error",
                            "status_message": response.message,
                            "agent_name": "sales_prompt_extractor",
                            "structured_data": response.data.get("structured_data", {}),
                            "voice_prompt": response.data.get("voice_prompt", "")
                        }
                    ],
                    "actions": [],
                    "agents": ["sales_prompt_extractor"],
                    "metadata": {
                        "timestamp": datetime.now().isoformat()
                    }
                }
                return output_message
            elif agent_name == "bland_ai":
                # Direct agent call for bland_ai
                agent = agents_mapping["bland_ai"]
                # Parse the command from the message text
                text = message.get("content", [{}])[0].get("text", "").strip()
                
                # Handle both direct @bland_ai commands and subsequent commands
                command = None
                if text.startswith("@bland_ai"):
                    # Extract command after @bland_ai
                    command = text[len("@bland_ai"):].strip()
                else:
                    # If no @bland_ai prefix but bland_ai is in agents list,
                    # treat the entire text as the command
                    command = text

                # If no command (empty string), show help message
                if not command:
                    help_message = (
                        "Available commands:\n"
                        "- create_empty name=\"Name\" description=\"Description\": Create a new empty pathway\n"
                        "- create name=\"Name\" description=\"Description\" analysis_id=\"ID\": Create pathway from analysis\n"
                        "- update pathway_id=\"ID\" [name=\"Name\"] [description=\"Description\"]: Update pathway\n"
                        "- get pathway_id=\"ID\": Get pathway details\n"
                        "- list: List all available pathways\n"
                        "- add_kb pathway_id=\"ID\" kb_id=\"ID\": Add knowledge base to pathway\n"
                        "- remove_kb pathway_id=\"ID\" kb_id=\"ID\": Remove knowledge base from pathway"
                    )
                    return {
                        "status": "success",
                        "message": "Help information provided",
                        "session_id": session.session_id,
                        "conv_id": session.conv_id,
                        "msg_type": "output",
                        "content": [{
                            "type": "text",
                            "text": help_message,
                            "status": "success",
                            "status_message": "Help information",
                            "agent_name": "bland_ai"
                        }],
                        "actions": [],
                        "agents": ["bland_ai"],
                        "metadata": {
                            "timestamp": datetime.now().isoformat()
                        }
                    }

                # Parse command and parameters
                parts = command.split()
                command = parts[0].lower()  # Convert to lowercase for case-insensitive matching
                
                # Handle common typos/variations
                command_map = {
                    "lst": "list",
                    "lis": "list",
                    "lists": "list",
                    "create-empty": "create_empty",
                    "createempty": "create_empty",
                    "add-kb": "add_kb",
                    "addkb": "add_kb",
                    "remove-kb": "remove_kb",
                    "removekb": "remove_kb"
                }
                command = command_map.get(command, command)  # Map common variations to correct command
                
                params = {}
                for part in parts[1:]:
                    if "=" in part:
                        key, value = part.split("=", 1)
                        # Remove quotes if present
                        value = value.strip('"\'')
                        params[key] = value

                # Run the agent with parsed parameters
                response = agent.run(
                    command=command,
                    **params
                )
                
                # Convert AgentResponse to OutputMessage format
                # Ensure content is properly serialized
                content = []
                if hasattr(session.output_message, 'content') and session.output_message.content:
                    for item in session.output_message.content:
                        if hasattr(item, 'model_dump'):
                            content.append(item.model_dump())
                        elif isinstance(item, dict):
                            content.append(item)
                        else:
                            content.append({
                                "type": "text",
                                "text": str(item),
                                "status": "success",
                                "status_message": response.message,
                                "agent_name": "bland_ai"
                            })
                
                return {
                    "status": "success" if response.status == AgentStatus.SUCCESS else "error",
                    "message": response.message,
                    "session_id": session.session_id,
                    "conv_id": session.conv_id,
                    "msg_type": "output",
                    "content": content,
                    "actions": session.output_message.actions if hasattr(session.output_message, 'actions') else [],
                    "agents": ["bland_ai"],
                    "metadata": {
                        "timestamp": datetime.now().isoformat()
                    }
                }
            else:
                # Use reasoning engine for all other cases
                res_eng = ReasoningEngine(input_message=input_message, session=session)
                if input_message.agents:
                    for agent_name in input_message.agents:
                        res_eng.register_agents([agents_mapping[agent_name]])
                else:
                    res_eng.register_agents(agents)
                res_eng.run()
            
            # Return successful response
            return session.output_message.model_dump()

        except Exception as e:
            logger.exception(f"Error in chat handler: {e}")
            
            # Create error response
            error_response = {
                "status": "error",
                "message": f"Error in chat handler: {str(e)}",
                "session_id": session.id,
                "conv_id": session.conv_id,
                "msg_type": "output",
                "content": [],
                "actions": [],
                "agents": [],
                "metadata": {
                    "timestamp": datetime.now().isoformat(),
                    "error_type": type(e).__name__
                }
            }
            
            # Return error response
            return error_response


class SessionHandler:
    def __init__(self, db: BaseDB, **kwargs):
        self.db = db

    def get_sessions(self):
        session = Session(db=self.db)
        return session.get_all()

    def get_session(self, session_id):
        session = Session(db=self.db, session_id=session_id)
        return session.get()

    def delete_session(self, session_id):
        session = Session(db=self.db, session_id=session_id)
        return session.delete()


class VideoDBHandler:
    def __init__(self, collection_id):
        self.videodb_tool = VideoDBTool(collection_id=collection_id)

    def upload(
        self, source, source_type="url", media_type="video", name=None
    ):
        return self.videodb_tool.upload(source, source_type, media_type, name)

    def get_collection(self):
        """Get a collection by ID."""
        return self.videodb_tool.get_collection()

    def get_collections(self):
        """Get all collections."""
        return self.videodb_tool.get_collections()

    def get_video(self, video_id):
        """Get a video by ID."""
        return self.videodb_tool.get_video(video_id)

    def get_videos(self):
        """Get all videos in a collection."""
        return self.videodb_tool.get_videos()


class ConfigHandler:
    def check(self):
        """Check the configuration of the server."""
        videodb_configured = True if os.getenv("VIDEO_DB_API_KEY") else False

        db = load_db(os.getenv("SERVER_DB_TYPE", "sqlite"))
        db_configured = db.health_check()
        return {
            "videodb_configured": videodb_configured,
            "llm_configured": True,
            "db_configured": db_configured,
        }
