"""Base agent class for all agents in the system."""

from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod

from director.core.session import Session, OutputMessage

class AgentResponse:
    """Response from an agent's execution"""
    def __init__(self, output_message: OutputMessage):
        self.output_message = output_message

class Agent(ABC):
    """Base class for all agents"""
    
    def __init__(self, session: Session):
        """Initialize the agent
        
        Args:
            session: The session this agent is running in
        """
        self.session = session
        self.output_message = OutputMessage(
            session_id=session.session_id,
            conv_id=session.current_conv_id,
            agents=[self.name]
        )
        
    @property
    @abstractmethod
    def name(self) -> str:
        """Get the name of the agent"""
        pass
        
    @property
    @abstractmethod
    def description(self) -> str:
        """Get the description of the agent"""
        pass
        
    @abstractmethod
    async def run(self, **kwargs) -> AgentResponse:
        """Run the agent with the given parameters
        
        Args:
            **kwargs: Parameters for the agent
            
        Returns:
            AgentResponse containing the output message
        """
        pass 