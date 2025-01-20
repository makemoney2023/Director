"""Base class for Edge Functions."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

class BaseEdgeFunction(ABC):
    """Base class for all Edge Functions."""

    def __init__(self, session):
        """Initialize the Edge Function.
        
        Args:
            session: The current session object
        """
        self.session = session

    @abstractmethod
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the Edge Function.
        
        Args:
            input_data: Input data for the function
            
        Returns:
            Dict containing the function results
        """
        pass

    @abstractmethod
    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate the input data.
        
        Args:
            input_data: Input data to validate
            
        Returns:
            True if valid, False otherwise
        """
        pass

    def store_result(self, video_id: str, result: Dict[str, Any], output_type: str) -> Optional[str]:
        """Store the function result in the database.
        
        Args:
            video_id: ID of the video being processed
            result: Function result to store
            output_type: Type of output being stored
            
        Returns:
            ID of the stored result or None if storage failed
        """
        try:
            from uuid import uuid4
            output_id = str(uuid4())
            
            self.session.db.add_generated_output(
                id=output_id,
                video_id=video_id,
                output_type=output_type,
                content=str(result),
                metadata={"source": self.__class__.__name__}
            )
            
            return output_id
        except Exception as e:
            self.session.logger.error(f"Error storing edge function result: {str(e)}")
            return None 