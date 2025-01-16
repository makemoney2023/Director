import logging
import sys
import codecs
from typing import Dict, List, Optional, Any, Literal
import json
import re
from datetime import datetime
from pydantic import BaseModel
import time
import os
from sqlalchemy.orm import Session as SQLAlchemySession
from contextlib import contextmanager

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
from director.agents.voice_prompt_generation_agent import VoicePromptGenerationAgent
from director.agents.structured_data_agent import StructuredDataAgent
from director.agents.yaml_configuration_agent import YAMLConfigurationAgent
from director.core.database import Analysis, StructuredData, YAMLConfig, VoicePrompt, Session as DBSession

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
    voice_prompt: Optional[str] = None
    
    def __init__(self, analysis_data: Dict = None, anthropic_response: Dict = None, voice_prompt: str = None, **kwargs):
        super().__init__(**kwargs)
        self.analysis_data = analysis_data if analysis_data is not None else {}
        self.anthropic_response = AnthropicResponse(**anthropic_response) if anthropic_response else None
        self.voice_prompt = voice_prompt

    def to_dict(self) -> Dict:
        base_dict = super().to_dict()
        base_dict.update({
            "analysis_data": self.analysis_data,
            "anthropic_response": self.anthropic_response.dict() if self.anthropic_response else None,
            "voice_prompt": self.voice_prompt
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

@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = DBSession()
    try:
        yield session
        session.commit()
    except Exception as e:
        logger.error(f"Database error in session scope: {str(e)}")
        session.rollback()
        raise
    finally:
        session.close()

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
        self.voice_prompt_agent = VoicePromptGenerationAgent(session)
        self.structured_data_agent = StructuredDataAgent(session)
        self.yaml_config_agent = YAMLConfigurationAgent(session)
        
    def _get_db_session(self):
        """Get a new database session for thread-safe operations"""
        return DBSession()

    def _get_analysis_prompt(self, transcript: str, analysis_type: str) -> List[Dict[str, str]]:
        """Generate appropriate prompt based on analysis type"""
        try:
            logger.info("=== Generating Analysis Prompt ===")
            messages = [
                {
                    "role": "system",
                    "content": """You are an expert sales analyst. Your task is to analyze sales conversations and provide clear, actionable insights.
Your analysis must include:
1. A clear summary of the video content and key takeaways
2. Specific sales techniques with examples from the transcript
3. Communication strategies with actual phrases used
4. Objection handling approaches demonstrated
5. Voice agent guidelines based on successful patterns

Format your response with clear sections and specific examples."""
                },
                {
                    "role": "user", 
                    "content": f"""Analyze this sales conversation transcript and provide detailed insights in these specific areas:

SUMMARY:
• Provide a brief overview of what the video/conversation is about
• List the main topics covered
• Identify the key learning objectives
• Note any unique or particularly effective approaches demonstrated

DETAILED ANALYSIS:

1. Sales Techniques Used
• List each specific technique identified
• Include exact quotes or examples from the transcript
• Explain when and why each technique was effective
• Note the context and timing of each technique

2. Communication Strategies
• Document specific phrases and approaches used
• Include exact quotes showing each strategy
• Analyze tone, pacing, and style choices
• Note which strategies were most effective and why

3. Objection Handling
• List each objection encountered
• Document exactly how each was addressed
• Include specific phrases and responses used
• Analyze why the handling was effective or not

4. Voice Agent Guidelines
• Provide specific phrases to use or avoid
• Include exact response templates from successful exchanges
• Document tone and style recommendations
• List specific do's and don'ts with examples

Transcript to analyze:
{transcript}

For each section, include:
- Specific techniques/strategies by name
- Exact quotes and examples from the transcript
- When and why each approach works best
- Clear guidelines for implementation"""
                }
            ]
            logger.info("Analysis prompt generated successfully")
            return messages
        except Exception as e:
            logger.error(f"Error generating analysis prompt: {str(e)}", exc_info=True)
            raise

    def _store_analysis_response(self, content: str, status: str = "success", metadata: Dict = None, 
                               structured_data: Dict = None, voice_prompt: str = None, yaml_config: Dict = None) -> None:
        """Store analysis response and related data in the database"""
        try:
            with session_scope() as db_session:
                # Create or update Analysis record
                analysis = db_session.query(Analysis).filter_by(
                    video_id=self.video_id,
                    collection_id=self.collection_id
                ).first()
                
                if not analysis:
                    analysis = Analysis(
                        video_id=self.video_id,
                        collection_id=self.collection_id,
                        raw_analysis=content,
                        status=status,
                        meta_data=metadata or {}
                    )
                    db_session.add(analysis)
                else:
                    analysis.raw_analysis = content
                    analysis.status = status
                    analysis.meta_data = metadata or {}
                
                # Store structured data if provided
                if structured_data:
                    if not analysis.structured_data:
                        analysis.structured_data = StructuredData(data=structured_data)
                    else:
                        analysis.structured_data.data = structured_data
                
                # Store YAML config if provided
                if yaml_config:
                    if not analysis.yaml_config:
                        analysis.yaml_config = YAMLConfig(config=yaml_config)
                    else:
                        analysis.yaml_config.config = yaml_config
                
                # Store voice prompt if provided
                if voice_prompt:
                    if not analysis.voice_prompt:
                        analysis.voice_prompt = VoicePrompt(prompt=voice_prompt)
                    else:
                        analysis.voice_prompt.prompt = voice_prompt
                
                # Commit changes to database
                db_session.commit()
                
                # Update output message for UI
                if not self.output_message.content:
                    text_content = SalesAnalysisContent(
                        agent_name=self.agent_name,
                        status=MsgStatus.progress,
                        status_message="Analysis stored in database..."
                    )
                    self.output_message.content.append(text_content)
                else:
                    text_content = self.output_message.content[-1]
                
                text_content.text = content
                text_content.status = MsgStatus.success if status == "success" else MsgStatus.error
                text_content.status_message = "Analysis stored successfully" if status == "success" else "Error storing analysis"
                
                # Push update to UI
                self.output_message.push_update()
                logger.info(f"Analysis response and related data stored with status: {status}")
                
        except Exception as e:
            logger.error(f"Error storing analysis response: {str(e)}", exc_info=True)
            raise

    def _save_markdown_analysis(self, analysis_content: str, structured_data: Dict, voice_prompt: str, yaml_config: Dict, video_id: str) -> str:
        """Save the analysis as a markdown file."""
        try:
            # Create analysis directory if it doesn't exist
            analysis_dir = os.path.join(os.getcwd(), 'analysis')
            os.makedirs(analysis_dir, exist_ok=True)
            
            # Create filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'analysis_{video_id}_{timestamp}.md'
            filepath = os.path.join(analysis_dir, filename)
            
            # Format content
            markdown_content = f"""# Sales Conversation Analysis

## Raw Analysis
{analysis_content}

## YAML Configuration
```yaml
{yaml_config}
```

## Voice Agent Prompt
```
{voice_prompt}
```

## Structured Data
```json
{json.dumps(structured_data, indent=2)}
```
"""
            
            # Write to file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
                
            logger.info(f"Analysis saved to markdown file: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error saving markdown analysis: {str(e)}", exc_info=True)
            return None

    def _delete_existing_analysis(self, video_id: str, collection_id: str) -> None:
        """Delete existing analysis for the given video and collection."""
        try:
            with session_scope() as db_session:
                existing = db_session.query(Analysis).filter(
                    Analysis.video_id == video_id,
                    Analysis.collection_id == collection_id
                ).first()
                if existing:
                    db_session.delete(existing)
                    db_session.commit()
                    logger.info(f"Deleted existing analysis for video {video_id}")
        except Exception as e:
            logger.error(f"Error deleting existing analysis: {str(e)}", exc_info=True)
            raise

    def run(self, video_id: str = None, collection_id: str = None, force_refresh: bool = False, *args, **kwargs) -> OutputMessage:
        """Run the sales prompt extractor agent"""
        # Initialize output message and text content first
        self.output_message = OutputMessage(
            session_id=self.session.session_id,
            conv_id=self.session.conv_id,
            db=self.session.db
        )
        text_content = TextContent(
            status=MsgStatus.progress,
            status_message="Initializing...",
            agent_name=self.name
        )
        self.output_message.content.append(text_content)
        self.output_message.actions.append("Starting analysis...")
        self.output_message.push_update()
        
        try:
            # Validate required parameters
            if not video_id:
                raise ValueError("video_id is required")
            if not collection_id:
                raise ValueError("collection_id is required")
            
            # Store collection_id and video_id
            self.collection_id = collection_id
            self.video_id = video_id

            # If force_refresh is True, delete existing analysis
            if force_refresh:
                self._delete_existing_analysis(video_id, collection_id)
                text_content.status_message = "Deleted existing analysis, starting fresh analysis..."
                self.output_message.push_update()
            
            with session_scope() as db_session:
                # Check for existing analysis
                existing_analysis = db_session.query(Analysis).filter(
                    Analysis.video_id == video_id,
                    Analysis.collection_id == collection_id
                ).first()
                
                if existing_analysis and existing_analysis.status == 'success' and not force_refresh:
                    # Use existing analysis
                    text_content.status_message = "Found existing analysis"
                    self.output_message.push_update()
                    return self._process_existing_analysis(existing_analysis, text_content)
                
                # Get transcript
                transcript = self._get_transcript(video_id)
                
                # Create new analysis entry or update existing one
                if existing_analysis:
                    existing_analysis.status = 'processing'
                    analysis = existing_analysis
                else:
                    analysis = Analysis(
                        video_id=video_id,
                        collection_id=collection_id,
                        status='processing'
                    )
                    db_session.add(analysis)
                db_session.commit()
                
                # Continue with analysis process...
                return self._process_new_analysis(transcript, analysis, text_content)
                
        except ValueError as ve:
            logger.error(f"Validation error: {str(ve)}")
            text_content.status = MsgStatus.error
            text_content.status_message = f"Analysis failed: {str(ve)}"
            self.output_message.push_update()
            return self.output_message
        except Exception as e:
            logger.error(f"Error in analysis: {str(e)}")
            text_content.status = MsgStatus.error
            text_content.status_message = f"Analysis failed: {str(e)}"
            self.output_message.push_update()
            return self.output_message

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

    def _generate_structured_output(self, analysis_text: str, voice_prompt: str) -> Dict:
        """Convert Anthropic analysis into structured data using OpenAI"""
        try:
            # Initialize structured data with more comprehensive structure
            structured_data = {
                "summary": {
                    "overview": "",
                    "topics": [],
                    "learning_objectives": [],
                    "unique_approaches": []
                },
                "sales_techniques": [],
                "communication_strategies": [],
                "objection_handling": [],
                "voice_agent_guidelines": [],
                "script_templates": [],
                "key_phrases": [],
                "closing_techniques": []
            }
            
            # Split analysis into sections using markdown headers
            sections = re.split(r'\n##? ', analysis_text)
            current_section = None
            current_item = None
            
            for section in sections:
                section = section.strip()
                
                # Process SUMMARY section
                if section.startswith("SUMMARY") or "Summary" in section:
                    current_section = "summary"
                    lines = section.split("\n")
                    overview = []
                    topics = []
                    objectives = []
                    approaches = []
                    
                    for line in lines[1:]:  # Skip header
                        line = line.strip()
                        if line.startswith("•") or line.startswith("-"):
                            if "topic" in line.lower():
                                topics.append(line.strip("•- "))
                            elif "objective" in line.lower():
                                objectives.append(line.strip("•- "))
                            elif "approach" in line.lower():
                                approaches.append(line.strip("•- "))
                            else:
                                overview.append(line.strip("•- "))
                    
                    structured_data["summary"].update({
                        "overview": " ".join(overview),
                        "topics": topics,
                        "learning_objectives": objectives,
                        "unique_approaches": approaches
                    })
                    continue
                
                # Process Sales Techniques
                elif any(x in section for x in ["Sales Techniques", "SALES TECHNIQUES"]):
                    current_section = "sales_techniques"
                    techniques = re.split(r'\n(?=[a-z]\)|\d\.)', section)
                    
                    for technique in techniques[1:]:  # Skip header
                        lines = technique.split("\n")
                        if not lines:
                            continue
                            
                        name = re.sub(r'^[a-z]\)|^\d\.', '', lines[0]).strip()
                        description = ""
                        examples = []
                        effectiveness = ""
                        
                        for line in lines[1:]:
                            line = line.strip()
                            if line.startswith("- Quote:") or line.startswith("Example:"):
                                examples.append(line.split(":", 1)[1].strip().strip('"'))
                            elif line.startswith("- Effect:") or line.startswith("Effectiveness:"):
                                effectiveness = line.split(":", 1)[1].strip()
                            elif line.startswith("-"):
                                if not description:
                                    description = line.strip("- ")
                                else:
                                    effectiveness += " " + line.strip("- ")
                        
                        structured_data["sales_techniques"].append({
                            "name": name,
                            "description": description,
                            "examples": examples,
                            "effectiveness": effectiveness
                        })
                    continue
                
                # Process Communication Strategies
                elif any(x in section for x in ["Communication Strategies", "COMMUNICATION"]):
                    current_section = "communication_strategies"
                    strategies = re.split(r'\n(?=[a-z]\)|\d\.)', section)
                    
                    for strategy in strategies[1:]:  # Skip header
                        lines = strategy.split("\n")
                        if not lines:
                            continue
                            
                        strategy_type = re.sub(r'^[a-z]\)|^\d\.', '', lines[0]).strip()
                        description = ""
                        examples = []
                        effectiveness = ""
                        
                        for line in lines[1:]:
                            line = line.strip()
                            if line.startswith("- Quote:") or line.startswith("Example:"):
                                examples.append(line.split(":", 1)[1].strip().strip('"'))
                            elif line.startswith("- Effect:") or line.startswith("Effectiveness:"):
                                effectiveness = line.split(":", 1)[1].strip()
                            elif line.startswith("-"):
                                if not description:
                                    description = line.strip("- ")
                                else:
                                    effectiveness += " " + line.strip("- ")
                        
                        structured_data["communication_strategies"].append({
                            "type": strategy_type,
                            "description": description,
                            "examples": examples,
                            "effectiveness": effectiveness
                        })
                    continue
                
                # Process Objection Handling
                elif any(x in section for x in ["Objection Handling", "OBJECTIONS"]):
                    current_section = "objection_handling"
                    objections = re.split(r'\n(?=[a-z]\)|\d\.)', section)
                    
                    for objection in objections[1:]:  # Skip header
                        lines = objection.split("\n")
                        if not lines:
                            continue
                            
                        objection_text = re.sub(r'^[a-z]\)|^\d\.', '', lines[0]).strip().strip('"')
                        response = ""
                        examples = []
                        effectiveness = ""
                        
                        for line in lines[1:]:
                            line = line.strip()
                            if line.startswith("Response:"):
                                response = line.split(":", 1)[1].strip().strip('"')
                            elif line.startswith("Example:"):
                                examples.append(line.split(":", 1)[1].strip().strip('"'))
                            elif line.startswith("- Effect:") or line.startswith("Effectiveness:"):
                                effectiveness = line.split(":", 1)[1].strip()
                            elif line.startswith("-"):
                                if not response:
                                    response = line.strip("- ")
                                else:
                                    effectiveness += " " + line.strip("- ")
                        
                        structured_data["objection_handling"].append({
                            "objection": objection_text,
                            "response": response,
                            "examples": examples,
                            "effectiveness": effectiveness
                        })
                    continue
                
                # Process Voice Agent Guidelines
                elif any(x in section for x in ["Voice Agent Guidelines", "GUIDELINES"]):
                    current_section = "voice_agent_guidelines"
                    
                    # Split into Do's and Don'ts sections
                    do_section = ""
                    dont_section = ""
                    
                    if "DO's:" in section:
                        parts = section.split("DO's:", 1)
                        if len(parts) > 1:
                            do_section = parts[1].split("DON'T's:")[0] if "DON'T's:" in parts[1] else parts[1]
                    
                    if "DON'T's:" in section:
                        dont_section = section.split("DON'T's:", 1)[1]
                    
                    # Process Do's
                    for line in do_section.split("\n"):
                        if line.strip().startswith("-"):
                            structured_data["voice_agent_guidelines"].append({
                                "type": "do",
                                "description": line.strip("- "),
                                "context": "Best practice guideline"
                            })
                    
                    # Process Don'ts
                    for line in dont_section.split("\n"):
                        if line.strip().startswith("-"):
                            structured_data["voice_agent_guidelines"].append({
                                "type": "dont",
                                "description": line.strip("- "),
                                "context": "Practice to avoid"
                            })
                    continue
                
                # Process Closing Techniques
                elif any(x in section for x in ["Closing", "CLOSING"]):
                    current_section = "closing_techniques"
                    techniques = re.split(r'\n(?=[a-z]\)|\d\.)', section)
                    
                    for technique in techniques[1:]:  # Skip header
                        lines = technique.split("\n")
                        if not lines:
                            continue
                            
                        name = re.sub(r'^[a-z]\)|^\d\.', '', lines[0]).strip()
                        description = ""
                        examples = []
                        
                        for line in lines[1:]:
                            line = line.strip()
                            if line.startswith("Example:") or line.startswith("- Quote:"):
                                examples.append(line.split(":", 1)[1].strip().strip('"'))
                            elif line.startswith("-"):
                                if not description:
                                    description = line.strip("- ")
                                else:
                                    description += " " + line.strip("- ")
                        
                        structured_data["closing_techniques"].append({
                            "name": name,
                            "description": description,
                            "examples": examples
                        })
                    continue
                
                # Process Script Templates
                elif "Script Template:" in section:
                    template = section.split("Script Template:", 1)[1].strip()
                    context = "Main outbound call script"
                    if ":" in template:
                        context, template = template.split(":", 1)
                    structured_data["script_templates"].append({
                        "template": template.strip(),
                        "context": context.strip()
                    })
                    continue
                
                # Process Key Phrases
                elif "Key Phrases" in section:
                    for line in section.split("\n"):
                        if line.strip().startswith("-"):
                            phrase = line.strip("- ").strip('"')
                            if phrase:
                                structured_data["key_phrases"].append(phrase)
            
            return structured_data
            
        except Exception as e:
            logger.error(f"Error generating structured output: {str(e)}", exc_info=True)
            return {
                "summary": {"overview": "", "topics": [], "learning_objectives": [], "unique_approaches": []},
                "sales_techniques": [],
                "communication_strategies": [],
                "objection_handling": [],
                "voice_agent_guidelines": [],
                "script_templates": [],
                "key_phrases": [],
                "closing_techniques": [],
                "raw_analysis": analysis_text,
                "error": str(e)
            }

    def _extract_behavioral_patterns(self, analysis_data: Dict) -> Dict:
        """Extract behavioral patterns from analysis data"""
        patterns = {
            "customer_signals": [],
            "agent_responses": [],
            "interaction_flows": [],
            "success_patterns": []
        }
        
        # Extract from sales techniques
        for technique in analysis_data.get("sales_techniques", []):
            if technique.get("effectiveness"):
                patterns["success_patterns"].append({
                    "technique": technique["name"],
                    "context": technique["description"],
                    "effectiveness": technique["effectiveness"],
                    "examples": technique.get("examples", [])
                })
            
            # Look for customer interaction patterns
            for example in technique.get("examples", []):
                if any(signal in example.lower() for signal in ["when customer", "if prospect", "customer says"]):
                    patterns["customer_signals"].append({
                        "context": technique["name"],
                        "signal": example,
                        "response_type": technique["description"]
                    })

        # Extract from communication strategies
        for strategy in analysis_data.get("communication_strategies", []):
            if strategy.get("examples"):
                patterns["agent_responses"].append({
                    "context": strategy["type"],
                    "responses": strategy["examples"],
                    "effectiveness": strategy.get("effectiveness", "")
                })
            
            # Look for interaction patterns
            if strategy.get("description"):
                patterns["interaction_flows"].append({
                    "type": strategy["type"],
                    "flow": strategy["description"],
                    "examples": strategy.get("examples", [])
                })

        return patterns

    def _identify_success_markers(self, analysis_data: Dict) -> Dict:
        """Identify success markers and indicators from analysis"""
        markers = {
            "positive_indicators": [],
            "engagement_signals": [],
            "conversion_points": [],
            "risk_factors": []
        }
        
        # Extract from summary
        if "summary" in analysis_data:
            summary = analysis_data["summary"]
            if "unique_approaches" in summary:
                for approach in summary["unique_approaches"]:
                    markers["positive_indicators"].append({
                        "type": "approach",
                        "description": approach
                    })
        
        # Extract from objection handling
        for objection in analysis_data.get("objection_handling", []):
            if objection.get("effectiveness"):
                if "success" in objection["effectiveness"].lower() or "positive" in objection["effectiveness"].lower():
                    markers["conversion_points"].append({
                        "context": "objection_handled",
                        "trigger": objection.get("objection", ""),
                        "response": objection.get("response", ""),
                        "effectiveness": objection["effectiveness"]
                    })
            else:
                markers["risk_factors"].append({
                    "type": "objection",
                    "description": objection.get("objection", ""),
                    "mitigation": objection.get("response", "")
                })

        # Extract from voice agent guidelines
        for guideline in analysis_data.get("voice_agent_guidelines", []):
            if guideline.get("type") == "do":
                markers["engagement_signals"].append({
                    "type": "best_practice",
                    "description": guideline["description"],
                    "context": guideline.get("context", "")
                })
            else:
                markers["risk_factors"].append({
                    "type": "guideline",
                    "description": guideline["description"],
                    "context": guideline.get("context", "")
                })

        return markers

    def _map_conversation_pathways(self, analysis_data: Dict) -> List[Dict]:
        """Map different conversation pathways based on analysis"""
        pathways = []
        
        # Extract standard pathway
        standard_path = {
            "type": "standard",
            "stages": [
                {"name": "opening", "techniques": []},
                {"name": "discovery", "techniques": []},
                {"name": "solution", "techniques": []},
                {"name": "closing", "techniques": []}
            ],
            "transitions": []
        }
        
        # Map techniques to stages
        for technique in analysis_data.get("sales_techniques", []):
            technique_name = technique["name"].lower()
            if any(x in technique_name for x in ["open", "greet", "introduction"]):
                standard_path["stages"][0]["techniques"].append(technique)
            elif any(x in technique_name for x in ["question", "discover", "probe"]):
                standard_path["stages"][1]["techniques"].append(technique)
            elif any(x in technique_name for x in ["present", "solution", "value"]):
                standard_path["stages"][2]["techniques"].append(technique)
            elif any(x in technique_name for x in ["close", "commit", "next steps"]):
                standard_path["stages"][3]["techniques"].append(technique)
        
        pathways.append(standard_path)
        
        # Extract objection pathway
        objection_path = {
            "type": "objection_handling",
            "trigger_points": [],
            "responses": [],
            "recovery_paths": []
        }
        
        for objection in analysis_data.get("objection_handling", []):
            objection_path["trigger_points"].append({
                "objection": objection.get("objection", ""),
                "context": objection.get("context", "")
            })
            objection_path["responses"].append({
                "objection": objection.get("objection", ""),
                "response": objection.get("response", ""),
                "effectiveness": objection.get("effectiveness", "")
            })
        
        pathways.append(objection_path)
        
        return pathways

    def _generate_voice_prompt(self, analysis_data: Dict) -> str:
        """Generate a detailed voice agent prompt from the structured analysis data"""
        try:
            # Extract key components from structured data
            sales_techniques = analysis_data.get("sales_techniques", [])
            
            # Build context section
            context_section = """CONTEXT & OBJECTIVES:
This is a sales training focused on building confidence, handling objections, and mastering closing techniques. The emphasis is on transforming sales professionals into confident closers through proven psychological techniques and systematic response preparation.

Key Techniques:
- Identity Shifting: Creating a confident sales persona
- Value Anchoring: Connecting price to long-term value
- Emotional Connection: Speaking to desires rather than logic
- Hypothetical Questioning: Bypassing initial resistance"""

            # Build identity section using identity shifting technique
            identity_section = """IDENTITY & PERSONA:
- Embody a confident, professional sales identity (like the Goggins example)
- Project unwavering confidence while maintaining authenticity
- Adapt tone and pace to match customer while staying authoritative
- Demonstrate deep product knowledge and genuine desire to help
- Maintain strong eye contact and assured presence"""

            # Extract and format techniques by category
            opening_techniques = [t for t in sales_techniques if "open" in t.get("name", "").lower()]
            discovery_techniques = [t for t in sales_techniques if any(x in t.get("name", "").lower() for x in ["question", "discovery", "hypothetical"])]
            presentation_techniques = [t for t in sales_techniques if any(x in t.get("name", "").lower() for x in ["value", "present", "emotional"])]
            objection_techniques = [t for t in sales_techniques if "objection" in t.get("name", "").lower()]
            closing_techniques = [t for t in sales_techniques if "clos" in t.get("name", "").lower()]

            # Build conversation framework with specific techniques
            conversation_framework = f"""CONVERSATION FRAMEWORK:

1. OPENING (First 30 seconds):
- Create a strong first impression with confident presence
- Establish professional yet warm rapport
- Set clear expectations for the conversation
{chr(10).join(f'- {t["description"]}' for t in opening_techniques if t.get("description"))}

2. DISCOVERY (2-3 minutes):
- Use hypothetical questioning to bypass resistance
- Ask targeted, emotionally-focused questions
- Listen actively and validate concerns
{chr(10).join(f'- {t["description"]}' for t in discovery_techniques if t.get("description"))}

3. VALUE PRESENTATION:
- Connect features to emotional benefits
- Use value anchoring to justify investment
- Paint vivid pictures of positive outcomes
{chr(10).join(f'- {t["description"]}' for t in presentation_techniques if t.get("description"))}

4. OBJECTION HANDLING:
- Redirect from price to value
- Isolate real concerns behind objections
- Use emotional connection to overcome resistance
{chr(10).join(f'- {t["description"]}' for t in objection_techniques if t.get("description"))}

5. CLOSING:
- Maintain unwavering confidence
- Use assumptive closing techniques
- Set clear next steps with urgency
{chr(10).join(f'- {t["description"]}' for t in closing_techniques if t.get("description"))}"""

            # Build techniques section with examples
            techniques_section = """CORE TECHNIQUES:

1. Identity Shifting:
- Create and maintain a confident sales persona
- Separate personal from professional identity
- Project unwavering confidence in delivery
Example: "When I'm in someone's home...I've already decided it's not David Goggins, it's Goggins"

2. Value Anchoring:
- Connect price to long-term value/consequences
- Focus on lifetime benefits over immediate cost
- Use concrete examples and metaphors
Example: "These trees out here that took 30 years to grow take a day to tear down"

3. Hypothetical Questioning:
- Bypass initial resistance with indirect approach
- Create mental ownership and commitment
- Guide customer through decision process
Example: "Hypothetically, if you did talk to her and she said let's go, would we do it?"

4. Emotional Connection Building:
- Speak to emotional desires over logical concerns
- Paint vivid pictures of positive outcomes
- Link features to personal benefits
Example: "Nancy, you've envisioned in your head what this backyard is going to look like..."

5. Objection Resolution:
- Redirect from price to value
- Isolate real concerns behind objections
- Use emotional connection to overcome resistance
Example: "What part of the proposal today are you wanting to think about?"""

            # Build power phrases section
            power_phrases = """POWER PHRASES:

Opening:
- "Let me ask you a question..."
- "I totally understand..."
- "What would that be worth to you?"
- "I won't let you down"

Value Building:
- "These trees took 30 years to grow..."
- "Imagine your family enjoying..."
- "What's that peace of mind worth?"

Objection Handling:
- "Let's look at it this way..."
- "What part specifically concerns you?"
- "If we could address that concern..."

Closing:
- "When would you like to get started?"
- "Let's take care of this today"
- "You're already spending the money..."
"""

            # Build behavioral guidelines
            behavioral_section = """BEHAVIORAL GUIDELINES:

Do's:
- Maintain unwavering confidence in delivery
- Practice responses until they're automatic
- Use strong eye contact during closes
- Speak with conviction and authority
- Stay emotionally connected with customer

Don'ts:
- Show uncertainty in pricing
- Let customer see you thinking about responses
- Allow long pauses in objection handling
- Break character or lose confidence
- Focus on logic over emotion"""

            # Build meta instructions
            meta_instructions = """META INSTRUCTIONS:
1. Maintain your confident sales identity throughout
2. Adapt responses based on emotional signals
3. Use strategic silence for impact
4. Mirror customer's speech pattern while staying authoritative
5. Break complex information into digestible segments
6. Always maintain control of the conversation
7. Use value anchoring in every phase
8. Keep emotional connection as primary focus

ETHICAL FRAMEWORK:
1. Always prioritize customer's best interests
2. Never make false or exaggerated claims
3. Respect privacy and confidentiality
4. Be transparent about limitations
5. Maintain professional boundaries

Remember: Success comes from unwavering confidence, emotional connection, and systematic response preparation. Build trust through authenticity while maintaining your strong sales identity."""

            # Combine all sections
            prompt = f"""You are an advanced AI voice sales agent, trained in high-performance sales techniques and emotional intelligence. Your goal is to engage in natural, persuasive sales conversations while maintaining unwavering confidence and authenticity.

{context_section}

{identity_section}

{conversation_framework}

{techniques_section}

{power_phrases}

{behavioral_section}

{meta_instructions}"""

            return prompt
            
        except Exception as e:
            logger.error(f"Error generating voice prompt: {str(e)}", exc_info=True)
            return "Error generating voice prompt. Please check the logs for details."

    def _format_behavioral_patterns(self, patterns: Dict) -> str:
        """Format behavioral patterns into prompt section"""
        formatted = "Key Interaction Patterns:\n"
        
        # Add customer signals
        if patterns["customer_signals"]:
            formatted += "\nCustomer Signal Patterns:\n"
            for signal in patterns["customer_signals"][:3]:  # Limit to top 3
                formatted += f"- When: {signal['signal']}\n  Response: {signal['response_type']}\n"
        
        # Add agent responses
        if patterns["agent_responses"]:
            formatted += "\nProven Response Patterns:\n"
            for response in patterns["agent_responses"][:3]:  # Limit to top 3
                formatted += f"- Context: {response['context']}\n  Approaches: {', '.join(response['responses'][:2])}\n"
        
        return formatted

    def _format_conversation_flows(self, flows: List[Dict]) -> str:
        """Format conversation flows into prompt section"""
        formatted = "Available Conversation Paths:\n"
        
        for flow in flows:
            if flow["type"] == "standard":
                formatted += "\nStandard Path:\n"
                for stage in flow["stages"]:
                    if stage["techniques"]:
                        formatted += f"- {stage['name'].title()}:\n"
                        for technique in stage["techniques"][:2]:  # Limit to top 2
                            formatted += f"  * {technique['name']}: {technique['description']}\n"
            elif flow["type"] == "objection_handling":
                formatted += "\nObjection Handling Paths:\n"
                for trigger in flow["trigger_points"][:3]:  # Limit to top 3
                    formatted += f"- On: {trigger['objection']}\n"
        
        return formatted

    def _format_success_markers(self, markers: Dict) -> str:
        """Format success markers into prompt section"""
        formatted = "Key Success Indicators:\n"
        
        if markers["positive_indicators"]:
            formatted += "\nPositive Signals:\n"
            for indicator in markers["positive_indicators"][:3]:
                formatted += f"- {indicator['description']}\n"
        
        if markers["conversion_points"]:
            formatted += "\nConversion Triggers:\n"
            for point in markers["conversion_points"][:3]:
                formatted += f"- When: {point['trigger']}\n  Success Response: {point['response']}\n"
        
        return formatted

    def _format_adaptation_rules(self, patterns: Dict, markers: Dict) -> str:
        """Format adaptation rules into prompt section"""
        formatted = "Dynamic Adaptation Guidelines:\n"
        
        # Add interaction-based rules
        if patterns["interaction_flows"]:
            formatted += "\nInteraction Adjustments:\n"
            for flow in patterns["interaction_flows"][:3]:
                formatted += f"- When using {flow['type']}:\n  {flow['flow']}\n"
        
        # Add success-based rules
        if markers["engagement_signals"]:
            formatted += "\nEngagement Rules:\n"
            for signal in markers["engagement_signals"][:3]:
                formatted += f"- {signal['description']}\n"
        
        return formatted

    def _format_techniques_for_stage(self, flows: List[Dict], stage: str) -> str:
        """Format techniques for a specific conversation stage"""
        formatted = ""
        
        for flow in flows:
            if flow["type"] == "standard":
                for s in flow["stages"]:
                    if s["name"] == stage and s["techniques"]:
                        for technique in s["techniques"][:3]:  # Limit to top 3
                            formatted += f"- {technique['name']}:\n"
                            formatted += f"  Purpose: {technique['description']}\n"
                            if technique.get("examples"):
                                formatted += f"  Example: {technique['examples'][0]}\n"
        
        return formatted or "Use standard best practices for this stage"

    def _format_objection_handling(self, flows: List[Dict]) -> str:
        """Format objection handling patterns"""
        formatted = ""
        
        for flow in flows:
            if flow["type"] == "objection_handling":
                for response in flow["responses"][:3]:  # Limit to top 3
                    formatted += f"- When hearing: {response['objection']}\n"
                    formatted += f"  Respond with: {response['response']}\n"
                    if response.get("effectiveness"):
                        formatted += f"  Effectiveness: {response['effectiveness']}\n"
        
        return formatted or "Follow standard objection handling practices"

    def _format_customer_signals(self, signals: List[Dict]) -> str:
        """Format customer signals section"""
        formatted = "Watch for these customer indicators:\n"
        
        for signal in signals[:5]:  # Limit to top 5
            formatted += f"- Signal: {signal['signal']}\n"
            formatted += f"  Context: {signal['context']}\n"
            formatted += f"  Response: {signal['response_type']}\n"
        
        return formatted

    def _format_response_patterns(self, patterns: List[Dict]) -> str:
        """Format response patterns section"""
        formatted = "Proven response patterns:\n"
        
        for pattern in patterns[:5]:  # Limit to top 5
            formatted += f"- Context: {pattern['context']}\n"
            if pattern["responses"]:
                formatted += f"  Examples:\n"
                for response in pattern["responses"][:2]:
                    formatted += f"    * {response}\n"
        
        return formatted

    def _get_transcript(self, video_id: str) -> str:
        """Get transcript for a video."""
        try:
            if not video_id:
                logger.error("No video_id provided")
                raise ValueError("video_id is required")
            
            if not hasattr(self, 'collection_id') or not self.collection_id:
                logger.error("No collection_id available")
                raise ValueError("collection_id is required")
            
            logger.info(f"Getting transcript for video {video_id} in collection {self.collection_id}")
            
            # Get transcript using transcription agent
            response = self.transcription_agent.run(
                video_id=video_id,
                collection_id=self.collection_id
            )
            
            if response.status != AgentStatus.SUCCESS:
                logger.error(f"Failed to get transcript: {response.message}")
                raise Exception(f"Transcription failed: {response.message}")
            
            transcript = response.data.get("transcript")
            if not transcript:
                logger.error("No transcript in response data")
                raise Exception("No transcript received")
            
            return transcript
            
        except Exception as e:
            logger.error(f"Error getting transcript: {str(e)}", exc_info=True)
            raise

    def _process_existing_analysis(self, analysis: Analysis, text_content: TextContent) -> OutputMessage:
        """Process an existing analysis"""
        try:
            if analysis.status == 'success':
                # Format complete response with all components
                complete_response = f"""Here's my detailed analysis:

{analysis.raw_analysis}

STRUCTURED DATA:
```json
{json.dumps(analysis.structured_data.data if analysis.structured_data else {}, indent=2)}
```

YAML CONFIGURATION:
```yaml
{analysis.yaml_config.config if analysis.yaml_config else ''}
```

VOICE PROMPT:
```
{analysis.voice_prompt.prompt if analysis.voice_prompt else ''}
```
"""
                text_content.text = complete_response
                text_content.status = MsgStatus.success
                text_content.status_message = "Retrieved existing analysis"
                self.output_message.push_update()
                return self.output_message
            
            # If not successful, treat as new analysis
            return self._process_new_analysis(self._get_transcript(analysis.video_id), analysis, text_content)
        except Exception as e:
            logger.error(f"Error processing existing analysis: {str(e)}", exc_info=True)
            text_content.status = MsgStatus.error
            text_content.status_message = f"Error processing analysis: {str(e)}"
            self.output_message.push_update()
            return self.output_message

    def _process_new_analysis(self, transcript: str, analysis: Analysis, text_content: TextContent) -> OutputMessage:
        """Process a new analysis"""
        try:
            with session_scope() as db_session:
                # Merge the analysis object into the current session
                analysis = db_session.merge(analysis)
                
                # Analyze content
                self.output_message.actions.append("Analyzing sales content...")
                self.output_message.push_update()
                analysis_content = self._analyze_content(transcript)
                
                # Update analysis with initial content
                analysis.raw_analysis = analysis_content
                analysis.status = 'processing'
                db_session.commit()
                
                try:
                    # Generate structured data first
                    self.output_message.actions.append("Generating structured data...")
                    self.output_message.push_update()
                    structured_data = self._generate_structured_output(analysis_content, "")
                    
                    # Generate YAML configuration with structured data
                    self.output_message.actions.append("Generating YAML configuration...")
                    self.output_message.push_update()
                    yaml_response = self.yaml_config_agent.run(
                        analysis=analysis_content,
                        structured_data=structured_data
                    )
                    # Access the YAML config from the response data
                    yaml_config = yaml_response.data.get('yaml_config') if yaml_response and yaml_response.data else None
                    
                    # Generate voice prompt
                    self.output_message.actions.append("Generating voice prompt...")
                    self.output_message.push_update()
                    voice_prompt = self._generate_voice_prompt(structured_data)
                    
                    # Format complete response with all components
                    complete_response = f"""Here's my detailed analysis:

{analysis_content}

STRUCTURED DATA:
```json
{json.dumps(structured_data, indent=2)}
```

YAML CONFIGURATION:
```yaml
{yaml_config if yaml_config else ''}
```

VOICE PROMPT:
```
{voice_prompt}
```
"""
                    
                    # Update analysis with final results
                    analysis.raw_analysis = analysis_content
                    analysis.status = 'success'
                    analysis.meta_data = {
                        "structured_data": structured_data,
                        "yaml_config": yaml_config,
                        "voice_prompt": voice_prompt
                    }
                    
                    # Store the components
                    if not analysis.structured_data:
                        analysis.structured_data = StructuredData(data=structured_data)
                    else:
                        analysis.structured_data.data = structured_data
                    
                    if not analysis.yaml_config and yaml_config:
                        analysis.yaml_config = YAMLConfig(config=yaml_config)
                    elif yaml_config:
                        analysis.yaml_config.config = yaml_config
                    
                    if not analysis.voice_prompt:
                        analysis.voice_prompt = VoicePrompt(prompt=voice_prompt)
                    else:
                        analysis.voice_prompt.prompt = voice_prompt
                    
                    db_session.commit()
                    
                    # Update output message
                    text_content.text = complete_response
                    text_content.status = MsgStatus.success
                    text_content.status_message = "Analysis completed successfully"
                    self.output_message.actions.append("Analysis completed")
                    self.output_message.push_update()
                    
                except Exception as inner_e:
                    logger.error(f"Error during analysis processing: {str(inner_e)}", exc_info=True)
                    analysis.status = 'error'
                    analysis.meta_data = {"error": str(inner_e)}
                    db_session.commit()
                    raise
                
                return self.output_message
                
        except Exception as e:
            logger.error(f"Error in process_new_analysis: {str(e)}", exc_info=True)
            text_content.status = MsgStatus.error
            text_content.status_message = f"Analysis failed: {str(e)}"
            self.output_message.push_update()
            return self.output_message

    def _analyze_content(self, transcript: str) -> str:
        """Analyze the content using the analysis LLM."""
        try:
            # Generate analysis prompt
            analysis_prompt = self._get_analysis_prompt(transcript, "full")
            
            # Get analysis from LLM
            response = self.analysis_llm.chat_completions(
                messages=analysis_prompt,
                temperature=0.7,
                max_tokens=4000
            )
            
            if not response or not response.content:
                raise Exception("No response received from analysis LLM")
            
            # Log the response for debugging
            logger.info("Analysis response received successfully")
            logger.debug(f"Raw analysis response: {response.content}")
            
            return response.content
            
        except Exception as e:
            logger.error(f"Error in content analysis: {str(e)}", exc_info=True)
            raise Exception(f"Content analysis failed: {str(e)}")