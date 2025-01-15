import os
import logging

from director.agents.thumbnail import ThumbnailAgent
from director.agents.summarize_video import SummarizeVideoAgent
from director.agents.download import DownloadAgent
from director.agents.pricing import PricingAgent
from director.agents.upload import UploadAgent
from director.agents.search import SearchAgent
from director.agents.prompt_clip import PromptClipAgent
from director.agents.index import IndexAgent
from director.agents.brandkit import BrandkitAgent
from director.agents.profanity_remover import ProfanityRemoverAgent
from director.agents.image_generation import ImageGenerationAgent
from director.agents.audio_generation import AudioGenerationAgent
from director.agents.video_generation import VideoGenerationAgent
from director.agents.stream_video import StreamVideoAgent
from director.agents.subtitle import SubtitleAgent
from director.agents.slack_agent import SlackAgent
from director.agents.editing import EditingAgent
from director.agents.dubbing import DubbingAgent
from director.agents.text_to_movie import TextToMovieAgent
from director.agents.meme_maker import MemeMakerAgent
from director.agents.composio import ComposioAgent
from director.agents.transcription import TranscriptionAgent
from director.agents.comparison import ComparisonAgent
from director.agents.web_search_agent import WebSearchAgent
from director.agents.sales_prompt_extractor import SalesPromptExtractorAgent


from director.core.session import Session, InputMessage, MsgStatus
from director.core.reasoning import ReasoningEngine
from director.db.base import BaseDB
from director.db import load_db
from director.tools.videodb_tool import VideoDBTool

logger = logging.getLogger(__name__)


class ChatHandler:
    def __init__(self, db, **kwargs):
        self.db = db

        # Register the agents here
        self.agents = [
            ThumbnailAgent,
            SummarizeVideoAgent,
            DownloadAgent,
            PricingAgent,
            UploadAgent,
            SearchAgent,
            PromptClipAgent,
            IndexAgent,
            BrandkitAgent,
            ProfanityRemoverAgent,
            ImageGenerationAgent,
            AudioGenerationAgent,
            VideoGenerationAgent,
            StreamVideoAgent,
            SubtitleAgent,
            SlackAgent,
            EditingAgent,
            DubbingAgent,
            TranscriptionAgent,
            TextToMovieAgent,
            MemeMakerAgent,
            ComposioAgent,
            ComparisonAgent,
            WebSearchAgent,
            SalesPromptExtractorAgent,
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
            if input_message.agents and len(input_message.agents) == 1 and input_message.agents[0] == "sales_prompt_extractor":
                # Direct agent call for sales_prompt_extractor
                agent = agents_mapping["sales_prompt_extractor"]
                response = agent.run(
                    video_id=session.video_id,
                    collection_id=session.collection_id,
                    bypass_reasoning=True
                )
                session.output_message.content.append(response.data.get("analysis", ""))
                session.output_message.status = MsgStatus.success
                session.output_message.publish()
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
            session.output_message.update_status(MsgStatus.error)
            logger.exception(f"Error in chat handler: {e}")
            
            # Return error response
            return session.output_message.model_dump()


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
