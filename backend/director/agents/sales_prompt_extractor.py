import logging
import sys
import codecs
from typing import Dict, List, Optional, Any, Literal
import json
import re
from datetime import datetime
from pydantic import BaseModel
import time

from director.agents.base import BaseAgent, AgentResponse, AgentStatus
from director.agents.transcription import TranscriptionAgent
from director.agents.summarize_video import SummarizeVideoAgent
from director.agents.sales_voice_prompt_agent import SalesVoicePromptAgent
from director.agents.sales_conversation_agent import SalesConversationAgent
from director.core.session import (
    Session,
    TextContent,
    MsgStatus,
    ContextMessage,
    RoleTypes,
    OutputMessage,
)
from director.llm import get_default_llm
from director.tools.anthropic_tool import AnthropicTool
from director.llm.openai import OpenAI, OpenaiConfig, OpenAIChatModel
from director.llm.base import LLMResponseStatus

# Configure UTF-8 encoding for stdout
if sys.stdout.encoding != 'utf-8':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Configure logging with UTF-8 encoding and file output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sales_prompt_extractor.log', encoding='utf-8'),
        logging.StreamHandler(codecs.getwriter('utf-8')(sys.stdout.buffer) if hasattr(sys.stdout, 'buffer') else sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def _clean_text_for_logging(text: str) -> str:
    """Clean text for logging by replacing problematic Unicode characters"""
    return (text.replace('→', '->') 
            .replace('←', '<-')
            .replace('⇒', '=>')
            .replace('⇐', '<=')
            .encode('ascii', 'replace')
            .decode('ascii'))

SALES_PROMPT_PARAMETERS = {
    "type": "object",
    "properties": {
        "video_id": {
            "type": "string",
            "description": "The ID of the video to analyze"
        },
        "collection_id": {
            "type": "string", 
            "description": "The ID of the collection containing the video"
        },
        "analysis_type": {
            "type": "string",
            "enum": ["sales_techniques", "communication", "full"],
            "default": "full",
            "description": "Type of analysis to perform"
        },
        "output_format": {
            "type": "string",
            "enum": ["structured", "text", "both"],
            "default": "both",
            "description": "Format of the analysis output"
        }
    },
    "required": ["video_id", "collection_id"],
    "description": "Analyzes sales techniques and generates AI voice agent prompts",
    "bypass_reasoning": True,
    "example_queries": [
        "@sales_prompt_extractor analyze video_id=123 collection_id=456",
        "@sales_prompt_extractor"
    ]
}

class AnthropicResponse(BaseModel):
    """Model for storing Anthropic responses"""
    content: str
    timestamp: datetime
    status: str
    metadata: Dict = {}

class SalesAnalysisContent(TextContent):
    """Content type for sales analysis results"""
    analysis_data: Dict = {}
    anthropic_response: Optional[AnthropicResponse] = None
    
    def __init__(self, analysis_data: Dict = None, anthropic_response: Dict = None, **kwargs):
        super().__init__(**kwargs)
        self.analysis_data = analysis_data if analysis_data is not None else {}
        self.anthropic_response = AnthropicResponse(**anthropic_response) if anthropic_response else None

    def to_dict(self) -> Dict:
        base_dict = super().to_dict()
        base_dict.update({
            "analysis_data": self.analysis_data,
            "anthropic_response": self.anthropic_response.dict() if self.anthropic_response else None
        })
        return base_dict

    def store_anthropic_response(self, content: str, status: str = "success", metadata: Dict = None):
        """Store Anthropic response with metadata"""
        self.anthropic_response = AnthropicResponse(
            content=content,
            timestamp=datetime.now(),
            status=status,
            metadata=metadata or {}
        )

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

class SalesPromptExtractorAgent(BaseAgent):
    """Agent for extracting sales concepts and generating AI voice agent prompts"""
    
    def __init__(self, session: Session, **kwargs):
        self.agent_name = "sales_prompt_extractor"
        self.description = "Analyzes sales techniques and generates AI voice agent prompts"
        self.parameters = SALES_PROMPT_PARAMETERS
        super().__init__(session=session, **kwargs)
        
        # Initialize dependent agents
        self.transcription_agent = TranscriptionAgent(session)
        self.summarize_agent = SummarizeVideoAgent(session)
        
        # Initialize LLMs
        self.llm = get_default_llm()
        self.analysis_llm = kwargs.get('analysis_llm') or AnthropicTool()
        self.max_retries = 3
        self.retry_delay = 2  # seconds

    def _get_analysis_prompt(self, transcript: str, analysis_type: str) -> List[Dict[str, str]]:
        """Generate appropriate prompt based on analysis type"""
        try:
            logger.info("=== Generating Analysis Prompt ===")
            messages = [
                {
                    "role": "system",
                    "content": """You are an expert sales analyst. Your task is to analyze sales conversations and provide clear, actionable insights.
Focus on identifying:
1. Effective sales techniques used
2. Communication strategies
3. Objection handling approaches
4. Voice agent guidelines

Provide your analysis in a clear, structured format using bullet points and sections."""
                },
                {
                    "role": "user",
                    "content": f"""Please analyze this sales conversation transcript and provide detailed insights in the following areas:

1. Sales Techniques Used
• Identify specific techniques demonstrated
• Provide brief examples from the transcript
• Note when each technique is most effective

2. Communication Strategies
• Key patterns and approaches used
• Notable phrases and responses
• Tone and style observations
• Effectiveness of different approaches

3. Objection Handling
• How objections were addressed
• Successful response strategies
• Examples of effective handling

4. Voice Agent Guidelines
• Recommended phrases to use
• Response templates
• Communication style recommendations
• Best practices identified

Please analyze the following transcript:

{transcript}

Format your response with clear sections and bullet points for easy reading."""
                }
            ]
            logger.info("Analysis prompt generated successfully")
            return messages
        except Exception as e:
            logger.error(f"Error generating analysis prompt: {str(e)}", exc_info=True)
            raise

    def _store_analysis_response(self, content: str, status: str = "success", metadata: Dict = None) -> None:
        """Store analysis response in the database"""
        try:
            # Get the current content or create new if doesn't exist
            if not self.output_message.content:
                text_content = SalesAnalysisContent(
                    agent_name=self.agent_name,
                    status=MsgStatus.progress,
                    status_message="Storing analysis..."
                )
                self.output_message.content.append(text_content)
            else:
                # Ensure we're working with a SalesAnalysisContent object
                text_content = self.output_message.content[-1]
                if not isinstance(text_content, SalesAnalysisContent):
                    text_content = SalesAnalysisContent(
                        agent_name=self.agent_name,
                        status=MsgStatus.progress,
                        status_message="Storing analysis..."
                    )
                    self.output_message.content[-1] = text_content

            # Store the response
            text_content.anthropic_response = AnthropicResponse(
                content=content,
                timestamp=datetime.now(),
                status=status,
                metadata=metadata or {}
            )
            
            # Update message status
            text_content.status = MsgStatus.success if status == "success" else MsgStatus.error
            text_content.status_message = "Analysis stored successfully" if status == "success" else "Error storing analysis"
            text_content.text = content  # Set the text content for display
            
            # Push update to database
            self.output_message.push_update()
            logger.info(f"Analysis response stored with status: {status}")
            
        except Exception as e:
            logger.error(f"Error storing analysis response: {str(e)}", exc_info=True)
            raise

    def run(
        self,
        video_id: str = None,
        collection_id: str = None,
        analysis_type: str = "full",
        bypass_reasoning: bool = True,
        *args,
        **kwargs,
    ) -> AgentResponse:
        """Run the sales prompt extractor agent."""
        try:
            # Initialize content holder
            text_content = SalesAnalysisContent(
                agent_name=self.agent_name,
                status=MsgStatus.progress,
                status_message="Starting analysis..."
            )
            self.output_message.content.append(text_content)
            
            # Get transcript
            self.output_message.actions.append("Getting transcript...")
            self.output_message.push_update(progress=0.1)
            
            if not collection_id:
                raise Exception("collection_id is required to get transcript")
            
            transcript_response = self.transcription_agent.run(
                collection_id=collection_id,
                video_id=video_id
            )
            
            if transcript_response.status != AgentStatus.SUCCESS:
                raise Exception(f"Failed to get transcript: {transcript_response.message}")
            
            transcript = transcript_response.data.get("transcript")
            if not transcript:
                raise Exception("No transcript found in response")
            
            self.output_message.actions.append("Analyzing sales content...")
            self.output_message.push_update(progress=0.3)
            
            # Get analysis with proper error handling and retries
            retry_count = 0
            last_error = None
            
            while retry_count < self.max_retries:
                try:
                    # Format messages for analysis
                    messages = self._get_analysis_prompt(transcript, analysis_type)
                    
                    logger.info("=== Starting Anthropic API Request ===")
                    logger.info("Sending analysis request...")
                    self.output_message.actions.append("Processing analysis...")
                    self.output_message.push_update(progress=0.4)
                    
                    # Make API call directly to Anthropic
                    response = self.analysis_llm.chat_completions(
                        messages=messages,
                        temperature=0.7,
                        max_tokens=8192
                    )
                    
                    if not response or not response.content:
                        raise Exception("No response received from Anthropic API")
                    
                    # Store the response immediately
                    self._store_analysis_response(
                        content=response.content,
                        status="success",
                        metadata={
                            "attempt": retry_count + 1,
                            "timestamp": datetime.now().isoformat(),
                            "bypass_reasoning": bypass_reasoning
                        }
                    )

                    # Generate structured output using OpenAI
                    self.output_message.actions.append("Generating structured output...")
                    self.output_message.push_update(progress=0.6)
                    
                    structured_data = self._generate_structured_output(response.content)
                    
                    # Generate voice agent prompt
                    self.output_message.actions.append("Generating voice agent prompt...")
                    self.output_message.push_update(progress=0.8)
                    
                    voice_prompt = self._generate_voice_prompt(structured_data)
                    
                    # Format final response with markdown
                    final_response = f"""
{response.content}

## Voice Agent Prompt
```
{voice_prompt}
```

## Structured Data
```json
{json.dumps(structured_data, indent=2)}
```
"""
                    
                    # Update the stored content with all data
                    text_content = self.output_message.content[-1]
                    text_content.text = final_response
                    text_content.analysis_data = structured_data
                    self.output_message.push_update()
                    
                    # Process and return the response
                    return AgentResponse(
                        status=AgentStatus.SUCCESS,
                        message="Analysis completed successfully",
                        data={
                            "analysis": response.content,
                            "voice_prompt": voice_prompt,
                            "structured_data": structured_data
                        }
                    )
                    
                except Exception as e:
                    last_error = str(e)
                    logger.error(f"Attempt {retry_count + 1} failed: {last_error}", exc_info=True)
                    retry_count += 1
                    if retry_count < self.max_retries:
                        time.sleep(self.retry_delay * retry_count)  # Exponential backoff
                    
                    # Store failed attempt
                    self._store_analysis_response(
                        content="",
                        status="error",
                        metadata={
                            "error": last_error,
                            "attempt": retry_count,
                            "timestamp": datetime.now().isoformat(),
                            "bypass_reasoning": bypass_reasoning
                        }
                    )
            
            # If we get here, all retries failed
            raise Exception(f"Failed after {self.max_retries} attempts. Last error: {last_error}")
            
        except Exception as e:
            logger.error(f"Error in sales prompt extractor: {str(e)}", exc_info=True)
            return AgentResponse(
                status=AgentStatus.ERROR,
                message=str(e),
                data=None
            )

    def _format_output(self, content: str) -> str:
        """Format the analysis output for better readability."""
        try:
            # Clean and normalize the content
            content = content.strip()
            content = re.sub(r'\n{3,}', '\n\n', content)  # Remove excessive newlines
            content = _clean_text_for_logging(content)
            return content
        except Exception as e:
            logger.error(f"Error formatting output: {str(e)}", exc_info=True)
            return content

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

Voice Agent Guidelines:
{guidelines}

IMPLEMENTATION GUIDELINES:
1. Start conversations by building rapport and understanding needs
2. Use appropriate sales techniques based on the conversation context
3. Address objections using the provided strategies
4. Apply closing techniques naturally when customer shows interest
5. Maintain a helpful and consultative approach throughout

Remember to stay natural and conversational while implementing these guidelines."""

        # Format techniques section
        techniques = "\n".join([
            f"- {t.get('description', '')}"
            for t in analysis_data.get("sales_techniques", [])
        ])
        
        # Format strategies section
        strategies = "\n".join([
            f"- {s.get('type', 'Strategy')}: {s.get('description', '')}"
            for s in analysis_data.get("communication_strategies", [])
        ])
        
        # Format objections section
        objections = "\n".join([
            f"- {o.get('description', '')}"
            for o in analysis_data.get("objection_handling", [])
        ])
        
        # Format guidelines section
        guidelines = "\n".join([
            f"- {g.get('description', '')}"
            for g in analysis_data.get("voice_agent_guidelines", [])
        ])
        
        return prompt.format(
            techniques=techniques or "No specific techniques provided",
            strategies=strategies or "No specific strategies provided",
            objections=objections or "No specific objection handling provided",
            guidelines=guidelines or "No specific guidelines provided"
        )

    def _get_fallback_conversations(self) -> list:
        """Return default fallback conversations if generation fails."""
        return [
            {
                "title": "Basic Product Inquiry",
                "scenario": "Customer inquiring about product features and pricing",
                "techniques_used": ["Active Listening", "Feature-Benefit Selling", "Consultative Approach"],
                "conversation": [
                    {
                        "role": "user",
                        "content": "I'm interested in learning more about your product."
                    },
                    {
                        "role": "assistant",
                        "content": "I'd be happy to help you learn more. To ensure I provide the most relevant information, could you tell me what specific needs or challenges you're looking to address?"
                    },
                    {
                        "role": "user",
                        "content": "Well, I'm mainly concerned about the cost and whether it's worth the investment."
                    },
                    {
                        "role": "assistant",
                        "content": "I understand cost is an important factor. Let's look at how our solution can provide value for your specific situation. Could you share more about your current process and what improvements you're hoping to achieve?"
                    }
                ]
            }
        ]

    def _generate_structured_output(self, analysis_text: str) -> Dict:
        """Convert Anthropic analysis into structured data using OpenAI"""
        try:
            prompt = f"""
            Convert this sales conversation analysis into structured data. Extract key information into these categories:

            1. Sales Techniques: List of techniques with descriptions
            2. Communication Strategies: List of strategies with types and descriptions
            3. Objection Handling: List of approaches with descriptions
            4. Voice Agent Guidelines: List of specific guidelines with descriptions

            Analysis text:
            {analysis_text}

            Return ONLY a JSON object with this structure:
            {{
                "sales_techniques": [
                    {{"name": "technique name", "description": "detailed description"}}
                ],
                "communication_strategies": [
                    {{"type": "strategy type", "description": "detailed description"}}
                ],
                "objection_handling": [
                    {{"name": "approach name", "description": "detailed description"}}
                ],
                "voice_agent_guidelines": [
                    {{"name": "guideline name", "description": "detailed description"}}
                ]
            }}
            """

            # Use OpenAI for structured extraction
            openai_config = OpenaiConfig(
                model=OpenAIChatModel.gpt_4_1106_preview,
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            openai = OpenAI(config=openai_config)
            
            response = openai.chat_completions(
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            if not response or not response.content:
                raise Exception("No structured data received from OpenAI")
                
            return json.loads(response.content)
            
        except Exception as e:
            logger.error(f"Error generating structured output: {str(e)}", exc_info=True)
            # Return a basic structure if processing fails
            return {
                "sales_techniques": [],
                "communication_strategies": [],
                "objection_handling": [],
                "voice_agent_guidelines": []
            }

    def _generate_voice_prompt(self, analysis_data: Dict) -> str:
        """Generate a detailed voice agent prompt from the structured analysis data"""
        try:
            prompt = """SALES CONVERSATION GUIDELINES

CORE OBJECTIVES:
1. Build genuine rapport with customers
2. Understand customer needs and pain points
3. Present relevant solutions effectively
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

Voice Agent Guidelines:
{guidelines}

IMPLEMENTATION GUIDELINES:
1. Start conversations by building rapport and understanding needs
2. Use appropriate sales techniques based on the conversation context
3. Address objections using the provided strategies
4. Apply closing techniques naturally when customer shows interest
5. Maintain a helpful and consultative approach throughout

Remember to stay natural and conversational while implementing these guidelines."""

            # Format techniques section
            techniques = "\n".join([
                f"- {t.get('name', '')}: {t.get('description', '')}"
                for t in analysis_data.get("sales_techniques", [])
            ])
            
            # Format strategies section
            strategies = "\n".join([
                f"- {s.get('type', '')}: {s.get('description', '')}"
                for s in analysis_data.get("communication_strategies", [])
            ])
            
            # Format objections section
            objections = "\n".join([
                f"- {o.get('name', '')}: {o.get('description', '')}"
                for o in analysis_data.get("objection_handling", [])
            ])
            
            # Format guidelines section
            guidelines = "\n".join([
                f"- {g.get('name', '')}: {g.get('description', '')}"
                for g in analysis_data.get("voice_agent_guidelines", [])
            ])
            
            return prompt.format(
                techniques=techniques or "No specific techniques provided",
                strategies=strategies or "No specific strategies provided",
                objections=objections or "No specific objection handling provided",
                guidelines=guidelines or "No specific guidelines provided"
            )
            
        except Exception as e:
            logger.error(f"Error generating voice prompt: {str(e)}", exc_info=True)
            return "Error generating voice prompt. Please check the logs for details."