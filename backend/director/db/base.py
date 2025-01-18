from abc import ABC, abstractmethod
from typing import List, Dict, Optional


class BaseDB(ABC):
    """Interface for all databases. It provides a common interface for all databases to follow."""

    @abstractmethod
    def create_session(
        self, session_id: str, video_id: str = None, collection_id: str = None
    ) -> None:
        """Create a new session."""
        pass

    @abstractmethod
    def get_session(self, session_id: str) -> dict:
        """Get a session by session_id."""
        pass

    @abstractmethod
    def get_sessions(self) -> list:
        """Get all sessions."""
        pass

    @abstractmethod
    def add_or_update_msg_to_conv() -> None:
        """Add a new message (input or output) to the conversation."""
        pass

    @abstractmethod
    def get_conversations(self, session_id: str) -> list:
        """Get all conversations for a given session."""
        pass

    @abstractmethod
    def get_context_messages(self, session_id: str) -> list:
        """Get context messages for a session."""
        pass

    @abstractmethod
    def add_or_update_context_msg(
        self, session_id: str, context_messages: list
    ) -> None:
        """Update context messages for a session."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the database is healthy."""
        pass

    @abstractmethod
    def add_analysis_result(
        self,
        analysis_id: str,
        session_id: str,
        video_id: str,
        analysis_type: str,
        sales_techniques: List[dict],
        objection_handling: List[dict],
        voice_prompts: List[str],
        training_pairs: List[dict],
        summary: str,
        created_at: int = None,
        updated_at: int = None,
        metadata: dict = {},
    ) -> None:
        """Add or update an analysis result."""
        pass

    @abstractmethod
    def get_analysis_result(self, analysis_id: str) -> Optional[Dict]:
        """Get an analysis result by ID."""
        pass

    @abstractmethod
    def get_session_analysis_results(self, session_id: str) -> List[Dict]:
        """Get all analysis results for a session."""
        pass

    @abstractmethod
    def delete_analysis_result(self, analysis_id: str) -> bool:
        """Delete an analysis result."""
        pass
