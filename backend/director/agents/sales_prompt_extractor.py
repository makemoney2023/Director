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
            # Initialize structured data
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
                "key_phrases": []
            }
            
            # Split analysis into sections
            sections = analysis_text.split("\n\n")
            current_section = None
            current_item = None
            
            for section in sections:
                section = section.strip()
                
                # Process SUMMARY section
                if section.startswith("SUMMARY:"):
                    current_section = "summary"
                    structured_data["summary"]["overview"] = section.replace("SUMMARY:", "").strip()
                    continue
                
                # Process Sales Techniques
                elif "1. Sales Techniques Used" in section:
                    current_section = "sales_techniques"
                    continue
                
                # Process Communication Strategies
                elif "2. Communication Strategies" in section:
                    current_section = "communication_strategies"
                    continue
                
                # Process Objection Handling
                elif "3. Objection Handling" in section:
                    current_section = "objection_handling"
                    continue
                
                # Process Voice Agent Guidelines
                elif "4. Voice Agent Guidelines" in section:
                    current_section = "voice_agent_guidelines"
                    continue
                
                # Process Script Template
                elif "Script Template:" in section:
                    template = section.split("Script Template:")[1].strip()
                    structured_data["script_templates"].append({
                        "template": template,
                        "context": "Main outbound call script"
                    })
                    continue
                
                # Process Key Phrases
                elif "Key Phrases to Use:" in section:
                    phrases = [
                        phrase.strip('- "')
                        for phrase in section.split("\n")
                        if phrase.strip().startswith("-")
                    ]
                    structured_data["key_phrases"].extend(phrases)
                    continue
                
                if not current_section:
                    continue
                
                # Process section content based on current section
                if current_section == "sales_techniques":
                    if section.startswith("a)") or section.startswith("b)") or section.startswith("c)"):
                        if current_item:
                            structured_data["sales_techniques"].append(current_item)
                        
                        lines = section.split("\n")
                        technique_name = lines[0].split(")")[1].strip()
                        current_item = {
                            "name": technique_name,
                            "description": "",
                            "examples": [],
                            "effectiveness": ""
                        }
                        
                        for line in lines[1:]:
                            line = line.strip()
                            if line.startswith("- Quote:"):
                                current_item["examples"].append(line.replace("- Quote:", "").strip().strip('"'))
                            elif line.startswith("-"):
                                if not current_item["description"]:
                                    current_item["description"] = line.strip("- ")
                                else:
                                    current_item["effectiveness"] += line.strip("- ") + " "
                
                elif current_section == "communication_strategies":
                    if section.startswith("a)") or section.startswith("b)"):
                        if current_item:
                            structured_data["communication_strategies"].append(current_item)
                        
                        lines = section.split("\n")
                        strategy_name = lines[0].split(")")[1].strip()
                        current_item = {
                            "type": strategy_name,
                            "description": "",
                            "examples": [],
                            "effectiveness": ""
                        }
                        
                        for line in lines[1:]:
                            line = line.strip()
                            if line.startswith("Quote:"):
                                current_item["examples"].append(line.replace("Quote:", "").strip().strip('"'))
                            elif line.startswith("-"):
                                if not current_item["description"]:
                                    current_item["description"] = line.strip("- ")
                                else:
                                    current_item["effectiveness"] += line.strip("- ") + " "
                
                elif current_section == "objection_handling":
                    if section.startswith("a)") or section.startswith("b)"):
                        if current_item:
                            structured_data["objection_handling"].append(current_item)
                        
                        lines = section.split("\n")
                        objection_name = lines[0].split(")")[1].strip().strip('"')
                        response = ""
                        for line in lines[1:]:
                            if line.startswith("Response:"):
                                response = line.replace("Response:", "").strip().strip('"')
                                break
                        
                        current_item = {
                            "name": objection_name,
                            "description": response,
                            "examples": [],
                            "effectiveness": ""
                        }
                        
                        for line in lines[1:]:
                            line = line.strip()
                            if line.startswith("-"):
                                current_item["effectiveness"] += line.strip("- ") + " "
                
                elif current_section == "voice_agent_guidelines":
                    if "DO's:" in section:
                        guidelines = section.split("DO's:")[1].split("DON'T's:")[0]
                        for line in guidelines.split("\n"):
                            if line.strip().startswith("-"):
                                structured_data["voice_agent_guidelines"].append({
                                    "name": "Do",
                                    "description": line.strip("- "),
                                    "examples": [],
                                    "context": "Best practice guideline"
                                })
                    
                    if "DON'T's:" in section:
                        guidelines = section.split("DON'T's:")[1]
                        for line in guidelines.split("\n"):
                            if line.strip().startswith("-"):
                                structured_data["voice_agent_guidelines"].append({
                                    "name": "Don't",
                                    "description": line.strip("- "),
                                    "examples": [],
                                    "context": "Practice to avoid"
                                })
            
            # Add the last item if exists
            if current_item:
                if current_section == "sales_techniques":
                    structured_data["sales_techniques"].append(current_item)
                elif current_section == "communication_strategies":
                    structured_data["communication_strategies"].append(current_item)
                elif current_section == "objection_handling":
                    structured_data["objection_handling"].append(current_item)
            
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
                "raw_analysis": analysis_text
            }

    def _generate_voice_prompt(self, analysis_data: Dict) -> str:
        """Generate a detailed voice agent prompt from the structured analysis data"""
        try:
            prompt = """You are an advanced AI voice sales agent. Your primary goal is to engage in natural, persuasive sales conversations while maintaining authenticity and ethical standards.

CONTEXT & OBJECTIVES:
{context}

IDENTITY & PERSONA:
- You are a professional, empathetic sales consultant
- Your voice is warm, confident, and naturally engaging
- You adapt your tone and pace to match the customer while staying professional
- You demonstrate deep product knowledge and genuine desire to help

CONVERSATION FRAMEWORK:

1. OPENING (First 30 seconds):
{opening_script}

2. DISCOVERY (2-3 minutes):
{discovery_techniques}

3. SOLUTION PRESENTATION (2-3 minutes):
{solution_techniques}

4. HANDLING CONCERNS:
{objection_handling}

5. CLOSING:
{closing_techniques}

VOICE & LANGUAGE PATTERNS:

Approved Scripts & Templates:
{scripts}

Power Phrases:
{key_phrases}

Communication Strategies:
{strategies}

BEHAVIORAL GUIDELINES:

Do's:
{dos}

Don'ts:
{donts}

META INSTRUCTIONS:
1. Always maintain natural conversation flow
2. Adapt responses based on customer's emotional state
3. Use silence strategically - allow customer to process
4. Mirror customer's speech pattern while staying professional
5. Break complex information into digestible segments

ETHICAL FRAMEWORK:
1. Always prioritize customer's best interests
2. Never make false or exaggerated claims
3. Respect privacy and confidentiality
4. Be transparent about limitations
5. Maintain professional boundaries

Remember: Your goal is to be helpful and genuine, not pushy or manipulative. Build trust through authenticity and expertise."""

            # Format context section
            context_section = analysis_data.get("summary", {}).get("overview", "No specific context provided")
            
            # Format opening script
            opening_script = "- Use this proven script structure:\n"
            for template in analysis_data.get("script_templates", []):
                opening_script += f'  "{template.get("template", "")}"\n'
            
            # Format discovery techniques
            discovery_techniques = ""
            for technique in analysis_data.get("sales_techniques", []):
                if "question" in technique.get("name", "").lower() or "discovery" in technique.get("name", "").lower():
                    discovery_techniques += f"- {technique['name']}:\n"
                    discovery_techniques += f"  Description: {technique['description']}\n"
                    if technique.get("examples"):
                        discovery_techniques += "  Example phrases:\n"
                        for example in technique["examples"]:
                            discovery_techniques += f'    "{example}"\n'
            
            # Format solution presentation techniques
            solution_techniques = ""
            for technique in analysis_data.get("sales_techniques", []):
                if "value" in technique.get("name", "").lower() or "story" in technique.get("name", "").lower():
                    solution_techniques += f"- {technique['name']}:\n"
                    solution_techniques += f"  Description: {technique['description']}\n"
                    if technique.get("examples"):
                        solution_techniques += "  Example phrases:\n"
                        for example in technique["examples"]:
                            solution_techniques += f'    "{example}"\n'
            
            # Format objection handling
            objection_handling = ""
            for objection in analysis_data.get("objection_handling", []):
                # Check if we have a description or type to use as the objection text
                objection_text = objection.get('description', objection.get('type', ''))
                if not objection_text:
                    continue
                    
                response = objection.get('response', objection.get('effectiveness', ''))
                objection_handling += f"- When customer says: \"{objection_text}\"\n"
                if response:
                    objection_handling += f"  Respond with: \"{response}\"\n"
            
            # Format closing techniques
            closing_techniques = "- Thank them for their time\n- Set clear next steps\n- Leave door open for future contact"
            
            # Format scripts section
            scripts = ""
            for template in analysis_data.get("script_templates", []):
                scripts += f"- {template.get('context', 'Script')}:\n"
                scripts += f'  "{template.get("template", "")}"\n'
            
            # Format key phrases
            key_phrases = ""
            for phrase in analysis_data.get("key_phrases", []):
                key_phrases += f'- "{phrase}"\n'
            
            # Format communication strategies
            strategies = ""
            for strategy in analysis_data.get("communication_strategies", []):
                strategies += f"- {strategy['type']}:\n"
                strategies += f"  {strategy['description']}\n"
                if strategy.get("examples"):
                    strategies += "  Examples:\n"
                    for example in strategy["examples"]:
                        strategies += f'    "{example}"\n'
            
            # Format guidelines
            dos = ""
            donts = ""
            for guideline in analysis_data.get("voice_agent_guidelines", []):
                if guideline["name"] == "Do":
                    dos += f"- {guideline['description']}\n"
                else:
                    donts += f"- {guideline['description']}\n"
            
            # Format the final prompt
            formatted_prompt = prompt.format(
                context=context_section,
                opening_script=opening_script or "- Greet warmly and professionally\n- Establish rapport quickly\n- State purpose clearly",
                discovery_techniques=discovery_techniques or "- Ask open-ended questions\n- Listen actively\n- Show genuine interest",
                solution_techniques=solution_techniques or "- Present tailored solutions\n- Focus on benefits\n- Use social proof",
                objection_handling=objection_handling or "- Listen fully\n- Acknowledge concerns\n- Provide solutions",
                closing_techniques=closing_techniques,
                scripts=scripts or "No specific scripts provided",
                key_phrases=key_phrases or "No specific key phrases provided",
                strategies=strategies or "No specific strategies provided",
                dos=dos or "- Be professional and courteous",
                donts=donts or "- Never be pushy or aggressive"
            )
            
            return formatted_prompt
            
        except Exception as e:
            logger.error(f"Error generating voice prompt: {str(e)}", exc_info=True)
            return "Error generating voice prompt. Please check the logs for details."

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