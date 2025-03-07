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
import yaml

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
from director.utils.supabase import SupabaseVectorStore
from director.tools.sales_analysis_tool import SalesAnalysisTool

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
    voice_prompt: str = ""
    structured_data: Dict = {}
    training_data: List[Dict] = []
    text_color: str = "#E4E4E7"  # Light gray color for dark theme readability
    
    def __init__(self, analysis_data: Dict = None, anthropic_response: Dict = None, 
                 voice_prompt: str = "", structured_data: Dict = None, 
                 training_data: List[Dict] = None, **kwargs):
        super().__init__(**kwargs)
        self.analysis_data = analysis_data if analysis_data is not None else {}
        self.anthropic_response = AnthropicResponse(**anthropic_response) if anthropic_response else None
        self.voice_prompt = voice_prompt
        self.structured_data = structured_data if structured_data is not None else {}
        self.training_data = training_data if training_data is not None else []
        self.text_color = "#E4E4E7"  # Light gray color for dark theme readability

    def to_dict(self) -> Dict:
        base_dict = super().to_dict()
        base_dict.update({
            "analysis_data": self.analysis_data,
            "anthropic_response": self.anthropic_response.dict() if self.anthropic_response else None,
            "voice_prompt": self.voice_prompt,
            "structured_data": self.structured_data,
            "training_data": self.training_data,
            "text_color": self.text_color
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
        
        # Initialize LLMs and vector store
        self.llm = get_default_llm()
        self.analysis_llm = kwargs.get('analysis_llm') or OpenAI(OpenaiConfig())
        self.vector_store = SupabaseVectorStore()
        self.max_retries = 3
        self.retry_delay = 2  # seconds
        self.voice_prompt_agent = VoicePromptGenerationAgent(session)
        self.structured_data_agent = StructuredDataAgent(session)
        self.yaml_config_agent = YAMLConfigurationAgent(session)
        self.logger = logger  # Initialize logger
        self.sales_tool = SalesAnalysisTool(api_key=self.llm.api_key)
        
    def _get_db_session(self):
        """Get a new database session for thread-safe operations"""
        return DBSession()

    ANALYSIS_FUNCTION = {
        "name": "analyze_sales_conversation",
        "description": "Analyze a sales conversation and return analysis, structured data, and voice prompt",
        "parameters": {
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "string",
                    "description": "Detailed markdown analysis covering key points, techniques, and insights"
                },
                "structured_data": {
                    "type": "object",
                    "properties": {
                        "sales_techniques": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "examples": {"type": "array", "items": {"type": "string"}},
                                    "effectiveness": {"type": "string"}
                                }
                            }
                        },
                        "key_metrics": {
                            "type": "object",
                            "properties": {
                                "engagement_level": {"type": "string"},
                                "objection_handling_score": {"type": "string"},
                                "communication_clarity": {"type": "string"}
                            }
                        }
                    }
                },
                "voice_prompt": {
                    "type": "string",
                    "description": "A concise, actionable prompt that starts with 'Hello!' and guides an AI agent in replicating successful techniques. Example: 'Hello! In your conversations, ensure to [key approach]. When customers [situation], respond with [technique]. Always maintain [style] and focus on [objective]. Thank you!'"
                }
            },
            "required": ["analysis", "structured_data", "voice_prompt"]
        }
    }

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

Provide your response in a structured format with:
- A detailed markdown analysis
- Structured data about sales techniques and metrics
- A voice prompt that incorporates the successful patterns identified

The voice prompt MUST be a concise, actionable prompt that guides an AI agent in replicating the successful techniques identified. 
Format it as a direct instruction to the AI, starting with a greeting and including key approaches to use.

IMPORTANT: Your response MUST include all three components:
1. analysis (string): Detailed markdown analysis
2. structured_data (object): Structured data about techniques and metrics
3. voice_prompt (string): A concise, actionable prompt starting with "Hello!" and including specific instructions

Example voice prompt format:
"Hello! In your conversations, ensure to [key approach 1]. When customers [situation], respond with [technique]. Always maintain [style] and focus on [objective]. Thank you!"
"""
                },
                {
                    "role": "user",
                    "content": f"""Analyze this sales conversation transcript and provide detailed insights:

{transcript}"""
                }
            ]
            logger.info("Analysis prompt generated successfully")
            return messages
        except Exception as e:
            logger.error(f"Error generating analysis prompt: {str(e)}", exc_info=True)
            raise

    def _store_analysis_response(self, video_id: str, collection_id: str, analysis_text: str) -> str:
        """Store analysis response in Supabase"""
        try:
            # Store analysis output
            analysis_id = f"analysis_{video_id}"
            self.vector_store.store_generated_output(
                video_id=video_id,
                collection_id=collection_id,
                output_type="analysis",
                content=analysis_text,
                metadata={
                    "collection_id": collection_id
                }
            )
            
            # Format next steps
            next_steps = self._format_next_steps(analysis_id, video_id)
            
            # Add next steps to text content
            text_content = self.output_message.content[0]
            text_content.text += f"\n\n{next_steps}"
            self.output_message.publish()
            
            return analysis_id
            
        except Exception as e:
            logger.error(f"Error storing analysis response: {str(e)}")
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

    def _process_long_transcript(self, transcript: str, video_id: str, collection_id: str) -> str:
        """Process long transcripts using vector search for relevant chunks"""
        try:
            # Store transcript chunks with embeddings
            self.vector_store.store_transcript(transcript, video_id, collection_id)
        except Exception as e:
            # If error is not due to duplicate transcript, raise it
            if "'code': '23505'" not in str(e) and "duplicate key value" not in str(e):
                raise
            logger.info(f"Transcript already exists in Supabase for video {video_id}")
        
        # Define key aspects to search for
        key_aspects = [
            "sales techniques and strategies",
            "communication patterns and approaches",
            "objection handling examples",
            "successful closing techniques",
            "customer engagement methods",
            "rapport building strategies",
            "pricing discussion examples",
            "value proposition presentation"
        ]
        
        # Get relevant chunks for each aspect
        relevant_chunks = []
        for aspect in key_aspects:
            chunks = self.vector_store.search_similar_chunks(aspect, 3)  # Get top 3 chunks per aspect
            relevant_chunks.extend([chunk["chunk_text"] for chunk in chunks])
        
        # Combine relevant chunks into processed transcript
        processed_transcript = "\n\n".join(relevant_chunks)
        return processed_transcript

    def _get_training_data_prompt(self, transcript: str) -> str:
        """Generate prompt for training data extraction"""
        return f"""You are an expert at extracting training data from transcripts to create high-quality examples for fine-tuning language models. Your task is to process a given transcript and structure the output in a format conducive to fine-tuning an LLM.

Here is the transcript you will be working with:

<transcript>
{transcript}
</transcript>

To extract training data, you will create examples in the following format:

<example>
<input>
[Insert a relevant portion of the transcript here, phrased as a prompt or question]
</input>
<output>
[Insert an appropriate response or completion based on the transcript]
</output>
</example>

Follow these steps to process the transcript:

1. Read through the entire transcript carefully.
2. Identify key topics, conversations, or information that would be valuable for training an LLM.
3. Break down the transcript into smaller, coherent segments that can be used as individual training examples.
4. For each segment, create an input-output pair:
   - The input should be a prompt or question based on the content.
   - The output should be the relevant information or response from the transcript.

Guidelines for creating high-quality training examples:

- Ensure each input-output pair is self-contained and makes sense on its own.
- Vary the types of inputs (e.g., questions, prompts, incomplete sentences) to create diverse training data.
- Include a mix of factual information, dialogue, and descriptive content when possible.
- Avoid including sensitive or personal information in the examples.
- Create examples that showcase different aspects of language understanding and generation.
- Focus on extracting examples that demonstrate successful sales techniques and communication patterns.
- Include examples of effective objection handling and closing techniques.

Output your extracted training data as a series of examples, each enclosed in <example> tags, with <input> and <output> subtags. Aim to create at least 5 examples, but no more than 10, depending on the length and complexity of the transcript."""

    def _parse_training_examples(self, response: str) -> List[Dict]:
        """Parse training examples from LLM response"""
        examples = []
        
        # Extract examples using regex
        pattern = r'<example>\s*<input>(.*?)</input>\s*<output>(.*?)</output>\s*</example>'
        matches = re.finditer(pattern, response, re.DOTALL)
        
        for match in matches:
            input_text = match.group(1).strip()
            output_text = match.group(2).strip()
            examples.append({
                "input": input_text,
                "output": output_text
            })
        
        return examples

    def _extract_training_data(self, transcript: str) -> List[Dict]:
        """Extract training examples from transcript"""
        try:
            # Get prompt
            prompt = self._get_training_data_prompt(transcript)
            
            # Get LLM response using OpenAI chat completion
            messages = [
                {"role": "system", "content": "You are an expert at extracting training data from transcripts."},
                {"role": "user", "content": prompt}
            ]
            
            # Use the OpenAI client correctly
            response = self.llm.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.7,
                max_tokens=4000
            )
            
            # Get the response content
            response_text = response.choices[0].message.content
            
            # Parse examples
            examples = self._parse_training_examples(response_text)
            
            if not examples:
                logger.warning("No training examples were extracted from the transcript")
            
            return examples
        except Exception as e:
            logger.error(f"Error extracting training data: {str(e)}", exc_info=True)
            return []

    def _generate_few_shot_examples(self, transcript: str) -> List[Dict]:
        """Generate few-shot learning examples from transcript"""
        try:
            prompt = f"""You are an expert at identifying and extracting few-shot learning examples from sales conversations. 
Your task is to analyze this transcript and create examples that can help an AI understand effective sales techniques.

Here is the transcript:

<transcript>
{transcript}
</transcript>

For each key moment in the conversation, create a few-shot example in this format:

<example>
<context>
[Describe the specific sales situation or customer state]
</context>
<input>
[What the customer said or the situation presented]
</input>
<response>
[How the salesperson effectively responded]
</response>
<reasoning>
[Why this response was effective and what technique it demonstrates]
</reasoning>
</example>

Focus on examples that demonstrate:
1. Objection handling
2. Value proposition delivery
3. Rapport building
4. Closing techniques
5. Discovery questions
6. Problem-solution framing

Create 5-8 diverse examples that cover different sales techniques and situations."""

            # Get LLM response using OpenAI chat completion
            messages = [
                {"role": "system", "content": "You are an expert at extracting sales conversation examples."},
                {"role": "user", "content": prompt}
            ]
            
            response = self.llm.client.chat.completions.create(
                model="gpt-4-1106-preview",
                messages=messages,
                temperature=0.7,
                max_tokens=2000
            )
            
            # Get the response content
            response_text = response.choices[0].message.content
            
            # Parse examples
            examples = self._parse_few_shot_examples(response_text)
            
            if not examples:
                logger.warning("No few-shot examples were extracted from the transcript")
            
            return examples
        except Exception as e:
            logger.error(f"Error generating few-shot examples: {str(e)}", exc_info=True)
            return []

    def _parse_few_shot_examples(self, response: str) -> List[Dict]:
        """Parse few-shot examples from LLM response"""
        examples = []
        
        # Extract examples using regex
        pattern = r'<example>\s*<context>(.*?)</context>\s*<input>(.*?)</input>\s*<response>(.*?)</response>\s*<reasoning>(.*?)</reasoning>\s*</example>'
        matches = re.finditer(pattern, response, re.DOTALL)
        
        for match in matches:
            examples.append({
                "context": match.group(1).strip(),
                "input": match.group(2).strip(),
                "response": match.group(3).strip(),
                "reasoning": match.group(4).strip()
            })
        
        return examples

    def _analyze_content(self, transcript: str) -> dict:
        """Analyze content using the consolidated SalesAnalysisTool"""
        try:
            logger.info("Starting content analysis")
            
            # Use the consolidated tool
            result = self.sales_tool.analyze_conversation(transcript)
            if not result:
                logger.error("Failed to analyze conversation")
                return None
            
            # Extract training data
            training_data = self._extract_training_data(transcript)
            
            # Generate few-shot examples
            few_shot_examples = self._generate_few_shot_examples(transcript)
            
            # Format the result for response
            analysis = "## Analysis\n```markdown\n"
            analysis += result.raw_analysis
            analysis += "\n```"

            # Add structured data section
            analysis += "\n\n## Structured Data\n```json\n"
            analysis += json.dumps(result.structured_data, indent=2)
            analysis += "\n```\n"

            # Add voice prompt section with few-shot examples
            analysis += "\n\n## Voice Prompt\n```\n"
            analysis += result.voice_prompt
            analysis += "\n\n### Few-Shot Learning Examples:\n"
            analysis += yaml.dump({"few_shot_examples": few_shot_examples}, default_flow_style=False, sort_keys=False)
            analysis += "\n```\n"
            
            # Add training data section
            analysis += "\n\n## Training Data\n```json\n"
            analysis += json.dumps(training_data, indent=2)
            analysis += "\n```\n"
                
            return {
                "analysis": analysis,
                "structured_data": result.structured_data,
                "voice_prompt": result.voice_prompt,
                "training_data": training_data,
                "few_shot_examples": few_shot_examples
            }
                
        except Exception as e:
            logger.error(f"Error in content analysis: {str(e)}", exc_info=True)
            raise

    def run(
        self,
        video_id: str = None,
        collection_id: str = None,
        *args,
        **kwargs
    ) -> AgentResponse:
        """Run the sales prompt extraction process"""
        try:
            # Initialize response content
            text_content = SalesAnalysisContent()
            text_content.text = "Starting sales prompt extraction..."
            text_content.status = MsgStatus.progress
            self.output_message.add_content(text_content)
            self.output_message.push_update()

            # Validate required parameters
            if not video_id or not collection_id:
                logger.error("Missing required parameters: video_id and collection_id are required")
                text_content.status = MsgStatus.error
                text_content.status_message = "Missing required parameters"
                text_content.text = "Error: video_id and collection_id are required"
                self.output_message.push_update()
                return AgentResponse(
                    status=AgentStatus.ERROR,
                    message="Missing required parameters",
                    data={"error": "video_id and collection_id are required"}
                )

            # Get transcript
            transcript = self._get_transcript(video_id, collection_id)
            if not transcript:
                text_content.status = MsgStatus.error
                text_content.status_message = "Failed to get transcript"
                text_content.text = "Error: Failed to get transcript"
                return AgentResponse(
                    status=AgentStatus.ERROR,
                    message="Failed to get transcript",
                    data={"error": "transcript_not_found"}
                )

            # Process new analysis directly
            return self._process_new_analysis(transcript, Analysis(video_id=video_id, collection_id=collection_id), text_content)

        except Exception as e:
            logger.error(f"Error in sales prompt extraction: {str(e)}")
            text_content.text = f"Failed to complete analysis: {str(e)}"
            text_content.status = MsgStatus.error
            text_content.status_message = str(e)
            return AgentResponse(
                status=AgentStatus.ERROR,
                message=f"Failed to complete analysis: {str(e)}",
                data={"error": str(e)}
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

    def _generate_voice_prompt(self, analysis_text: str) -> str:
        """Generate voice prompt from analysis"""
        try:
            # Try to parse analysis_text as JSON if it's a string
            if isinstance(analysis_text, str):
                try:
                    analysis_data = json.loads(analysis_text)
                except json.JSONDecodeError:
                    # If not valid JSON, extract key information from the text
                    analysis_data = self._extract_analysis_data(analysis_text)
            else:
                analysis_data = analysis_text

            # Extract components from analysis data
            sales_techniques = analysis_data.get("sales_techniques", [])
            communication_strategies = analysis_data.get("communication_strategies", [])
            objection_handling = analysis_data.get("objection_handling", [])
            voice_guidelines = analysis_data.get("voice_agent_guidelines", [])
            
            # Format the prompt sections
            prompt_sections = []
            
            # Add voice guidelines
            if voice_guidelines:
                prompt_sections.append("Voice Agent Guidelines:")
                for guideline in voice_guidelines:
                    prompt_sections.append(f"- {guideline}")
            
            # Add key communication strategies
            if communication_strategies:
                prompt_sections.append("\nKey Communication Approaches:")
                for strategy in communication_strategies[:3]:  # Limit to top 3
                    prompt_sections.append(f"- {strategy.get('name', '')}: {strategy.get('description', '')}")
            
            # Add objection handling
            if objection_handling:
                prompt_sections.append("\nObjection Handling:")
                for objection in objection_handling[:3]:  # Limit to top 3
                    prompt_sections.append(f"- When hearing: {objection.get('objection', '')}")
                    prompt_sections.append(f"  Respond with: {objection.get('response', '')}")
            
            # Add sales techniques
            if sales_techniques:
                prompt_sections.append("\nKey Sales Techniques:")
                for technique in sales_techniques[:3]:  # Limit to top 3
                    prompt_sections.append(f"- {technique.get('name', '')}: {technique.get('description', '')}")
            
            # Combine all sections
            prompt = "\n".join(prompt_sections)
            
            return prompt or "Use standard sales conversation practices and maintain a professional, friendly tone."
            
        except Exception as e:
            logger.error(f"Error generating voice prompt: {str(e)}", exc_info=True)
            return "Error generating voice prompt. Please use standard sales conversation practices."

    def _extract_analysis_data(self, text: str) -> Dict:
        """Extract structured data from raw analysis text"""
        data = {
            "sales_techniques": [],
            "communication_strategies": [],
            "objection_handling": [],
            "voice_agent_guidelines": []
        }
        
        # Extract sections using regex patterns
        sections = {
            "sales_techniques": r"(?i)sales\s+techniques?.*?(?=\n\n|$)",
            "communication_strategies": r"(?i)communication\s+strategies?.*?(?=\n\n|$)",
            "objection_handling": r"(?i)objection\s+handling.*?(?=\n\n|$)",
            "voice_agent_guidelines": r"(?i)voice.*?guidelines?.*?(?=\n\n|$)"
        }
        
        for key, pattern in sections.items():
            matches = re.findall(pattern, text, re.DOTALL)
            if matches:
                # Split into bullet points and clean up
                points = re.split(r'\n\s*[-•*]\s*', matches[0])
                points = [p.strip() for p in points if p.strip()]
                
                if key in ["sales_techniques", "communication_strategies"]:
                    data[key] = [{"name": p.split(':')[0].strip() if ':' in p else p,
                                "description": p.split(':')[1].strip() if ':' in p else ""} 
                               for p in points[1:]]  # Skip header
                elif key == "objection_handling":
                    data[key] = [{"objection": p.split('Response:')[0].replace('Objection:', '').strip(),
                                "response": p.split('Response:')[1].strip() if 'Response:' in p else ""}
                               for p in points[1:]]  # Skip header
                else:
                    data[key] = points[1:]  # Skip header
        
        return data

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

    def _get_transcript(self, video_id: str, collection_id: str) -> Optional[str]:
        """Get transcript for the given video ID and store in Supabase if not already stored"""
        try:
            if not video_id:
                logger.error("video_id is required")
                raise ValueError("video_id is required")
            
            if not collection_id:
                logger.error("collection_id is required")
                raise ValueError("collection_id is required")

            # First check if we have a cached transcript
            with session_scope() as db_session:
                analysis = db_session.query(Analysis).filter(
                    Analysis.video_id == video_id,
                    Analysis.collection_id == collection_id
                ).first()
                
                if analysis and analysis.transcript:
                    logger.info(f"Found cached transcript for video {video_id}")
                    # Store in Supabase if not already stored
                    try:
                        self.vector_store.store_transcript(analysis.transcript, video_id, collection_id)
                        logger.info(f"Stored transcript in Supabase for video {video_id}")
                    except Exception as e:
                        if "'code': '23505'" in str(e) or "duplicate key value" in str(e):
                            logger.info(f"Transcript already exists in Supabase for video {video_id}")
                        else:
                            logger.warning(f"Failed to store transcript in Supabase: {str(e)}")
                    return analysis.transcript

            # If no cached transcript, get it from the transcription agent
            logger.info(f"Getting transcript for video {video_id} from collection {collection_id}")
            response = self.transcription_agent.run(
                video_id=video_id,
                collection_id=collection_id
            )
            
            if response.status == AgentStatus.SUCCESS and response.data.get("transcript"):
                transcript = response.data["transcript"]
                
                # Store in SQLite
                with session_scope() as db_session:
                    analysis = Analysis(
                        video_id=video_id,
                        collection_id=collection_id,
                        transcript=transcript,
                        status="processing"
                    )
                    db_session.add(analysis)
                    db_session.commit()
                
                # Store in Supabase
                try:
                    self.vector_store.store_transcript(transcript, video_id, collection_id)
                    logger.info(f"Stored transcript in Supabase for video {video_id}")
                except Exception as e:
                    if "'code': '23505'" in str(e) or "duplicate key value" in str(e):
                        logger.info(f"Transcript already exists in Supabase for video {video_id}")
                    else:
                        logger.warning(f"Failed to store transcript in Supabase: {str(e)}")
                    
                return transcript
            else:
                logger.error(f"Failed to get transcript: {response.message}")
                return None

        except Exception as e:
            logger.error(f"Error getting transcript: {str(e)}")
            raise

    def _process_existing_analysis(self, analysis: Analysis, text_content: TextContent) -> AgentResponse:
        """Process an existing analysis"""
        try:
            if analysis.status == 'completed':
                # Try to get outputs from Supabase first
                structured_data = {}
                voice_prompt = ""
                try:
                    structured_data_output = self.vector_store.get_generated_output(
                        video_id=analysis.video_id,
                        collection_id=analysis.collection_id,
                        output_type="structured_data"
                    )
                    voice_prompt_output = self.vector_store.get_generated_output(
                        video_id=analysis.video_id,
                        collection_id=analysis.collection_id,
                        output_type="voice_prompt"
                    )
                    
                    if structured_data_output:
                        structured_data = json.loads(structured_data_output)
                    if voice_prompt_output:
                        voice_prompt = voice_prompt_output
                except Exception as e:
                    logger.warning(f"Failed to get outputs from Supabase: {str(e)}")
                
                # Fallback to SQLite data if Supabase retrieval failed
                if not structured_data and analysis.structured_data:
                    structured_data = analysis.structured_data.data
                if not voice_prompt and analysis.voice_prompt:
                    voice_prompt = analysis.voice_prompt.prompt

                # Format complete response with all components
                complete_response = f"""Here's my detailed analysis:

{analysis.raw_analysis}

STRUCTURED DATA:
```json
{json.dumps(structured_data, indent=2)}
```

VOICE PROMPT:
```
{voice_prompt}
```"""

                # Update text content
                text_content.text = complete_response
                text_content.status = MsgStatus.success
                text_content.status_message = "Retrieved existing analysis"

                return AgentResponse(
                    status=AgentStatus.SUCCESS,
                    message="Retrieved existing analysis",
                    data={
                        "analysis": analysis.raw_analysis,
                        "structured_data": structured_data,
                        "voice_prompt": voice_prompt
                    }
                )
            
            # If not completed, treat as new analysis
            return self._process_new_analysis(self._get_transcript(analysis.video_id, analysis.collection_id), analysis, text_content)
        except Exception as e:
            logger.error(f"Error processing existing analysis: {str(e)}", exc_info=True)
            # Update text content for error case
            text_content.text = f"Error processing analysis: {str(e)}"
            text_content.status = MsgStatus.error
            text_content.status_message = str(e)

            return AgentResponse(
                status=AgentStatus.ERROR,
                message=f"Error processing analysis: {str(e)}",
                data={"error": str(e)}
            )

    def _process_new_analysis(self, transcript: str, analysis: Analysis, text_content: TextContent) -> AgentResponse:
        """Process a new analysis"""
        try:
            # Analyze content
            analysis_result = self._analyze_content(transcript)
            if not analysis_result:
                text_content.text = "Failed to analyze content"
                text_content.status = MsgStatus.error
                text_content.status_message = "Analysis failed"
                return AgentResponse(
                    status=AgentStatus.ERROR,
                    message="Failed to analyze content",
                    data={"error": "analysis_failed"}
                )
            
            # Set video_id and collection_id from analysis object
            self.session.video_id = analysis.video_id
            self.session.collection_id = analysis.collection_id
            
            # Store results
            self._store_analysis_response(
                video_id=analysis.video_id,
                collection_id=analysis.collection_id,
                analysis_text=analysis_result["analysis"]
            )
            
            # Update text content for frontend
            text_content.text = analysis_result["analysis"]
            text_content.structured_data = analysis_result["structured_data"]
            text_content.voice_prompt = analysis_result["voice_prompt"]
            text_content.training_data = analysis_result["training_data"]
            text_content.status = MsgStatus.success
            text_content.status_message = "Analysis completed successfully"
            
            return AgentResponse(
                status=AgentStatus.SUCCESS,
                message="Analysis completed successfully",
                data=analysis_result
            )
                
        except Exception as e:
            logger.error(f"Error processing analysis: {str(e)}")
            text_content.text = f"Error processing analysis: {str(e)}"
            text_content.status = MsgStatus.error
            text_content.status_message = str(e)
            return AgentResponse(
                status=AgentStatus.ERROR,
                message=f"Error processing analysis: {str(e)}",
                data={"error": str(e)}
            )

    def _format_next_steps(self, analysis_id: str, video_id: str) -> str:
        """Format next step commands after analysis completes"""
        next_steps = (
            "Analysis complete! Here are your next steps:\n\n"
            "1. View available pathways:\n"
            "You can type: '@bland_ai show pathways' or '@bland_ai list'\n\n"
            "2. Create a knowledge base:\n"
            "You can type: '@bland_ai create knowledge base' or\n"
            "@bland_ai create_kb name=\"Sales KB\" description=\"Knowledge base from sales analysis\"\n\n"
            "3. Store voice prompts:\n" 
            "You can type: '@bland_ai save prompts' or\n"
            "@bland_ai store_prompts name=\"Sales Prompts\"\n\n"
            "4. Update a pathway with the prompts:\n"
            "You can type something like:\n"
            "'@bland_ai save prompts to Mark Wilsons'\n\n"
            "The agent will automatically use the most recent analysis and prompts - no need to specify IDs!"
        )
        return next_steps