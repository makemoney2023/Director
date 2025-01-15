import logging
from typing import Dict, List, Optional, Literal, Any
from pydantic import BaseModel

from director.agents.base import BaseAgent, AgentResponse, AgentStatus
from director.core.session import TextContent, MsgStatus, OutputMessage, Session
from director.llm.openai import OpenAI, OpenaiConfig, OpenAIChatModel
from director.llm.base import LLMResponseStatus

logger = logging.getLogger(__name__)

class ConversationMessage(BaseModel):
    """A single message in a conversation"""
    role: Literal["user", "assistant"]
    content: str

class Conversation(BaseModel):
    """A complete conversation example"""
    title: str
    scenario: str
    techniques_used: List[str]
    conversation: List[ConversationMessage]

class ConversationResponse(BaseModel):
    """The complete response structure for conversation generation"""
    explanation: str
    conversations: List[Conversation]

class ConversationContent(TextContent):
    """Content type for example conversations"""
    conversation_data: Dict = {}
    
    def __init__(self, conversation_data: Dict = None, **kwargs):
        super().__init__(**kwargs)
        self.conversation_data = conversation_data if conversation_data is not None else {}

    def to_dict(self) -> Dict:
        base_dict = super().to_dict()
        base_dict.update({
            "conversation_data": self.conversation_data
        })
        return base_dict

class SalesConversationAgent(BaseAgent):
    """Agent for generating example sales conversations"""
    
    def __init__(self, session: Session, **kwargs):
        self.agent_name = "sales_conversation"
        self.description = "Generates example sales conversations"
        self.parameters = self.get_parameters()
        super().__init__(session=session, **kwargs)
        
        # Initialize OpenAI for conversation generation with structured outputs
        openai_config = kwargs.get('openai_config') or OpenaiConfig(
            chat_model=OpenAIChatModel.GPT4o,
            max_tokens=4096
        )
        self.conversation_llm = kwargs.get('conversation_llm') or OpenAI(config=openai_config)

    def get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "analysis_data": {
                    "type": "object",
                    "description": "The sales analysis data to generate conversations from",
                    "required": ["structured_analysis"]
                }
            },
            "required": ["analysis_data"],
            "description": "Generates example sales conversations"
        }

    def _get_conversation_prompt(self, analysis_data: dict) -> str:
        """Generate prompt for example conversations."""
        prompt = """Create 3 example sales conversations that demonstrate the effective use of the provided sales techniques.
        Each conversation should show a different scenario and combination of techniques.
        
        Your response must follow this exact structure:
        {
            "explanation": "Brief explanation of how these conversations demonstrate the sales techniques",
            "conversations": [
                {
                    "title": "Title describing the conversation scenario",
                    "scenario": "Detailed description of the scenario",
                    "techniques_used": ["List of techniques demonstrated"],
                    "conversation": [
                        {
                            "role": "user",
                            "content": "Customer message"
                        },
                        {
                            "role": "assistant",
                            "content": "Sales agent response"
                        }
                    ]
                }
            ]
        }
        
        REQUIREMENTS:
        1. Generate exactly 3 conversations
        2. Each conversation must demonstrate different techniques
        3. Keep responses natural and realistic
        4. Show proper handling of objections
        5. Demonstrate effective closing techniques
        6. Include a mix of different techniques in each conversation
        7. Keep responses concise but effective
        
        Available Techniques:
        {techniques}
        
        Communication Strategies:
        {strategies}
        
        Objection Handling:
        {objections}
        
        Closing Techniques:
        {closing}"""

        # Format techniques section
        techniques = "\n".join([
            f"- {t.get('name', 'Technique')}: {t.get('description', '')}"
            for t in analysis_data.get("sales_techniques", [])
        ])
        
        # Format strategies section
        strategies = "\n".join([
            f"- {s.get('type', 'Strategy')}: {s.get('description', '')}"
            for s in analysis_data.get("communication_strategies", [])
        ])
        
        # Format objections section
        objections = "\n".join([
            f"- When hearing '{o.get('objection_type', 'Objection')}': {o.get('recommended_response', o.get('description', ''))}"
            for o in analysis_data.get("objection_handling", [])
        ])
        
        # Format closing section
        closing = "\n".join([
            f"- {c.get('name', 'Technique')}: {c.get('description', '')}"
            for c in analysis_data.get("closing_techniques", [])
        ])
        
        return prompt.format(
            techniques=techniques or "No specific techniques provided",
            strategies=strategies or "No specific strategies provided",
            objections=objections or "No specific objection handling provided",
            closing=closing or "No specific closing techniques provided"
        )

    def _get_fallback_conversations(self) -> List[Dict]:
        """Return fallback conversation examples if generation fails."""
        return [{
            "title": "Basic Sales Consultation",
            "scenario": "A potential customer inquiring about services",
            "techniques_used": ["Active Listening", "Building Rapport", "Value Proposition"],
            "conversation": [
                {
                    "role": "user",
                    "content": "Hi, I'm interested in learning more about your services."
                },
                {
                    "role": "assistant",
                    "content": "Welcome! I'd love to help you learn more about what we offer. Could you tell me what specific needs you're looking to address?"
                },
                {
                    "role": "user",
                    "content": "I'm looking for something that can help improve my team's productivity."
                },
                {
                    "role": "assistant",
                    "content": "I understand you want to boost team productivity. Our solutions have helped many teams achieve significant improvements. Would you like me to explain how our specific features can help your team?"
                }
            ]
        }]

    def run(
        self,
        analysis_data: Dict[str, Any],
        *args,
        **kwargs
    ) -> AgentResponse:
        """Generate example conversations from sales analysis data"""
        try:
            if not analysis_data or not isinstance(analysis_data, dict):
                raise ValueError("analysis_data must be a non-empty dictionary")
            
            if "structured_analysis" not in analysis_data:
                raise ValueError("analysis_data must contain structured_analysis")
                
            # Initialize content
            text_content = ConversationContent(
                conversation_data={},
                agent_name=self.agent_name,
                status=MsgStatus.progress,
                status_message="Generating example conversations...",
                text="Processing analysis data..."
            )
            self.output_message.add_content(text_content)
            self.output_message.actions.append("Starting conversation generation...")
            self.output_message.push_update()
            
            logger.info("Generating conversation prompt")
            conversation_prompt = self._get_conversation_prompt(analysis_data)
            
            # Generate conversations with OpenAI
            logger.info("Requesting conversations from OpenAI")
            response = self.conversation_llm.chat_completions(
                messages=[{
                    "role": "user",
                    "content": conversation_prompt
                }],
                response_format={"type": "json_object"}
            )
            
            if response.status == LLMResponseStatus.ERROR:
                logger.warning("OpenAI request failed, using fallback conversations")
                conversations = self._get_fallback_conversations()
            else:
                try:
                    # Parse the JSON response
                    conversation_data = ConversationResponse.parse_raw(response.content)
                    conversations = conversation_data.conversations
                except Exception as e:
                    logger.error(f"Failed to parse conversation response: {e}")
                    conversations = self._get_fallback_conversations()
            
            # Store results
            text_content.text = "Example conversations generated successfully"
            text_content.conversation_data = {
                "conversations": [conv.dict() for conv in conversations],
                "analysis_data": analysis_data
            }
            
            # Update status
            text_content.status = MsgStatus.success
            text_content.status_message = "Example conversations generated"
            self.output_message.actions.append("Conversations generated")
            self.output_message.push_update()
            
            logger.info("Example conversations generated successfully")
            return AgentResponse(
                status=AgentStatus.SUCCESS,
                message="Example conversations generated",
                data=text_content.conversation_data
            )
            
        except Exception as e:
            logger.error(f"Error generating conversations: {str(e)}", exc_info=True)
            if 'text_content' in locals():
                text_content.status = MsgStatus.error
                text_content.status_message = f"Failed to generate conversations: {str(e)}"
                self.output_message.push_update()
            return AgentResponse(
                status=AgentStatus.ERROR,
                message=str(e),
                data={"error": str(e)}
            ) 