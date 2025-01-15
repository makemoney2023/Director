import logging
from typing import Dict, List, Optional, Any
from pydantic import BaseModel

from director.agents.base import BaseAgent, AgentResponse, AgentStatus
from director.core.session import TextContent, MsgStatus, OutputMessage, Session
from director.llm import get_default_llm
from director.llm.base import LLMResponseStatus

logger = logging.getLogger(__name__)

class VoicePromptContent(TextContent):
    """Content type for voice prompt results"""
    prompt_data: Dict = {}
    
    def __init__(self, prompt_data: Dict = None, **kwargs):
        super().__init__(**kwargs)
        self.prompt_data = prompt_data if prompt_data is not None else {}

    def to_dict(self) -> Dict:
        base_dict = super().to_dict()
        base_dict.update({
            "prompt_data": self.prompt_data
        })
        return base_dict

class SalesVoicePromptAgent(BaseAgent):
    """Agent for generating AI voice agent prompts from sales analysis"""
    
    def __init__(self, session: Session, **kwargs):
        self.agent_name = "sales_voice_prompt"
        self.description = "Generates AI voice agent prompts from sales analysis"
        self.parameters = self.get_parameters()
        super().__init__(session=session, **kwargs)
        self.llm = get_default_llm()

    def get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "analysis_data": {
                    "type": "object",
                    "description": "The sales analysis data to generate prompts from",
                    "required": ["structured_analysis"]
                }
            },
            "required": ["analysis_data"],
            "description": "Generates AI voice agent prompts from sales analysis"
        }

    def _get_system_prompt(self, analysis_data: dict) -> str:
        """Generate system prompt for the AI voice agent."""
        prompt = """You are an AI sales agent trained to engage in natural, empathetic, and effective sales conversations. Your responses should be guided by the following framework:

ROLE AND PERSONA:
- You are a professional, friendly, and knowledgeable sales consultant
- You focus on understanding customer needs before proposing solutions
- You maintain a balanced approach between being helpful and goal-oriented

COMMUNICATION STYLE:
- Use clear, concise, and professional language
- Practice active listening and ask clarifying questions
- Mirror the customer's communication style while maintaining professionalism
- Show genuine interest in helping customers solve their problems

KEY OBJECTIVES:
1. Build trust and rapport with customers
2. Understand customer needs through effective questioning
3. Present relevant solutions based on customer requirements
4. Address concerns and objections professionally
5. Guide conversations toward positive outcomes

ETHICAL GUIDELINES:
1. Always be truthful and transparent
2. Never pressure customers into decisions
3. Respect customer privacy and confidentiality
4. Only make promises you can keep
5. Prioritize customer needs over immediate sales

AVAILABLE TECHNIQUES AND STRATEGIES:

Sales Techniques:
{techniques}

Communication Strategies:
{strategies}

Objection Handling:
{objections}

Closing Techniques:
{closing}

IMPLEMENTATION GUIDELINES:
1. Start conversations by building rapport and understanding needs
2. Use appropriate sales techniques based on the conversation context
3. Address objections using the provided strategies
4. Apply closing techniques naturally when customer shows interest
5. Maintain a helpful and consultative approach throughout

Remember to stay natural and conversational while implementing these guidelines."""

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

    def run(
        self,
        analysis_data: Dict[str, Any],
        *args,
        **kwargs
    ) -> AgentResponse:
        """Generate voice prompts from sales analysis data"""
        try:
            if not analysis_data or not isinstance(analysis_data, dict):
                raise ValueError("analysis_data must be a non-empty dictionary")
            
            if "structured_analysis" not in analysis_data:
                raise ValueError("analysis_data must contain structured_analysis")

            # Initialize content
            text_content = VoicePromptContent(
                prompt_data={},
                agent_name=self.agent_name,
                status=MsgStatus.progress,
                status_message="Generating voice prompts...",
                text="Processing analysis data..."
            )
            self.output_message.add_content(text_content)
            self.output_message.actions.append("Starting voice prompt generation...")
            self.output_message.push_update()
            
            logger.info("Generating system prompt from analysis data")
            system_prompt = self._get_system_prompt(analysis_data)
            
            # Store results
            text_content.text = system_prompt
            text_content.prompt_data = {
                "system_prompt": system_prompt,
                "analysis_data": analysis_data
            }
            text_content.status = MsgStatus.success
            text_content.status_message = "Voice prompts generated"
            
            self.output_message.actions.append("Voice prompts generated")
            self.output_message.push_update()
            
            logger.info("Voice prompts generated successfully")
            return AgentResponse(
                status=AgentStatus.SUCCESS,
                message="Voice prompts generated",
                data=text_content.prompt_data
            )
            
        except Exception as e:
            logger.error(f"Error generating voice prompts: {str(e)}", exc_info=True)
            if 'text_content' in locals():
                text_content.status = MsgStatus.error
                text_content.status_message = f"Failed to generate voice prompts: {str(e)}"
                self.output_message.push_update()
            return AgentResponse(
                status=AgentStatus.ERROR,
                message=str(e),
                data={"error": str(e)}
            ) 