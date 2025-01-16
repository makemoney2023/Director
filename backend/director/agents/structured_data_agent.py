import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
from pydantic import BaseModel

from director.agents.base import BaseAgent, AgentResponse, AgentStatus
from director.core.session import TextContent, MsgStatus, OutputMessage, Session
from director.tools.anthropic_tool import AnthropicTool
from director.llm.base import LLMResponseStatus

logger = logging.getLogger(__name__)

class StructuredContent(TextContent):
    """Content type for structured data results"""
    structured_data: Dict = {}
    metadata: Dict = {}
    
    def __init__(self, structured_data: Dict = None, metadata: Dict = None, **kwargs):
        super().__init__(**kwargs)
        self.structured_data = structured_data if structured_data is not None else {}
        self.metadata = metadata if metadata is not None else {}

    def to_dict(self) -> Dict:
        base_dict = super().to_dict()
        base_dict.update({
            "structured_data": self.structured_data,
            "metadata": self.metadata
        })
        return base_dict

class StructuredDataAgent(BaseAgent):
    """Agent for generating structured data from analysis and voice prompts"""
    
    def __init__(self, session: Session, **kwargs):
        self.agent_name = "structured_data"
        self.description = "Generates structured data for LLM consumption"
        self.parameters = self.get_parameters()
        super().__init__(session=session, **kwargs)
        
        # Initialize Anthropic
        self.structure_llm = kwargs.get('structure_llm') or AnthropicTool()

    def get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "string",
                    "description": "The sales analysis to structure"
                },
                "voice_prompt": {
                    "type": "string",
                    "description": "The voice prompt to structure (optional)",
                    "default": ""
                },
                "format": {
                    "type": "string",
                    "enum": ["json", "training", "complete"],
                    "default": "complete",
                    "description": "The type of structured data to generate"
                }
            },
            "required": ["analysis"],
            "description": "Generates structured data from analysis and optional voice prompts"
        }

    def _get_structure_prompt(self, analysis: str, voice_prompt: str, format: str) -> List[Dict[str, str]]:
        """Generate appropriate prompt for structured data generation"""
        system_prompt = """You are an expert in converting sales analysis and voice prompts into structured YAML data optimized for LLM consumption. Your task is to generate clean, well-organized YAML that captures all key information.

Your output must be valid YAML and should include:

1. METADATA
- Version information
- Generation timestamp
- Data format details
- Usage guidelines

2. ANALYSIS COMPONENTS
- Sales techniques with examples
- Communication patterns
- Objection handling approaches
- Success indicators

3. VOICE CHARACTERISTICS
- Tone parameters
- Pacing guidelines
- Adaptation rules
- Expression patterns

4. IMPLEMENTATION DETAILS
- Context handling rules
- Response templates
- Recovery strategies
- Quality metrics

5. TRAINING DATA
- Input-output pairs
- Context annotations
- Effectiveness scores
- Usage examples

FORMAT REQUIREMENTS:
1. Use clear, consistent key names
2. Include type information
3. Provide usage examples
4. Add descriptive comments
5. Ensure valid YAML structure
6. ALWAYS wrap the output in ```yaml code blocks

The output should be immediately usable by other LLMs without additional processing."""

        user_prompt = f"""Convert this sales analysis and voice prompt into structured {format} format YAML.

The output should:
1. Capture all key information
2. Maintain relationships between components
3. Include clear metadata
4. Provide usage guidelines
5. Follow YAML best practices
6. Be wrapped in ```yaml code blocks

Analysis:
{analysis}

Voice Prompt:
{voice_prompt}

Remember to:
- Use consistent formatting
- Include all relevant data
- Maintain clear structure
- Add helpful metadata
- Wrap output in ```yaml blocks"""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

    def _find_similar_structures(self) -> List[Dict]:
        """Find similar structured data in the codebase"""
        try:
            # Simplified implementation without using removed tools
            return []
        except Exception as e:
            logger.warning(f"Error finding similar structures: {str(e)}")
            return []

    def _save_structured_data(self, data: Dict, format: str) -> str:
        """Save the structured data to a file"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            # If we have YAML content, save it as YAML
            if "yaml_content" in data:
                filename = f"data/structured_{format}_{timestamp}.yaml"
                yaml_content = data["yaml_content"]
                if yaml_content.startswith("```yaml"):
                    yaml_content = yaml_content.split("```yaml")[1]
                if yaml_content.endswith("```"):
                    yaml_content = yaml_content.rsplit("```", 1)[0]
                
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(yaml_content.strip())
            else:
                filename = f"data/structured_{format}_{timestamp}.json"
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
            
            return filename
        except Exception as e:
            logger.warning(f"Error saving structured data: {str(e)}")
            return None

    def _validate_json(self, content: str) -> Dict:
        """Validate and clean JSON content"""
        try:
            # First try to parse as is
            return json.loads(content)
        except json.JSONDecodeError:
            try:
                # Look for JSON code blocks
                if "```json" in content:
                    json_content = content.split("```json")[1].split("```")[0]
                    return json.loads(json_content)
                # Look for YAML code blocks
                elif "```yaml" in content:
                    yaml_content = content.split("```yaml")[1].split("```")[0]
                    # Convert YAML to JSON structure
                    return {"yaml_content": yaml_content}
                # Look for JSON objects
                elif content.strip().startswith("{"):
                    return json.loads(content)
                else:
                    # Wrap plain text in markdown code block
                    return {"yaml_content": f"```yaml\n{content}\n```"}
            except Exception as e:
                raise ValueError(f"Content validation failed: {str(e)}")

    def run(
        self,
        analysis: str,
        voice_prompt: str = "",
        format: str = "complete",
        *args,
        **kwargs
    ) -> AgentResponse:
        """Generate structured data from analysis and optional voice prompt"""
        try:
            if not analysis:
                raise ValueError("Analysis is required")

            # Initialize content
            text_content = StructuredContent(
                structured_data={},
                metadata={},
                agent_name=self.agent_name,
                status=MsgStatus.progress,
                status_message="Starting structured data generation...",
                text="Processing inputs..."
            )
            self.output_message.add_content(text_content)
            self.output_message.actions.append("Beginning structure generation...")
            self.output_message.push_update()

            # Generate structured data
            messages = self._get_structure_prompt(analysis, voice_prompt, format)
            
            logger.info("Requesting structure generation from Anthropic")
            response = self.structure_llm.chat_completions(
                messages=messages,
                temperature=0.7,
                max_tokens=16384
            )
            
            if response.status == LLMResponseStatus.ERROR:
                raise Exception(f"Anthropic structure generation failed: {response.message}")

            # Extract YAML content directly from the response
            content = response.content
            if "```yaml" in content:
                yaml_content = content.split("```yaml")[1].split("```")[0].strip()
            else:
                yaml_content = content.strip()

            # Format the YAML content with code blocks
            formatted_yaml = f"```yaml\n{yaml_content}\n```"

            # Create structured data
            structured_data = {
                "yaml_content": formatted_yaml,
                "metadata": {
                    "version": "1.0",
                    "timestamp": datetime.now().isoformat(),
                    "format": format,
                    "source": {
                        "analysis": True,
                        "voice_prompt": bool(voice_prompt)
                    }
                }
            }

            # Store results directly in text_content
            text_content.structured_data = structured_data
            text_content.metadata = structured_data["metadata"]
            text_content.text = formatted_yaml  # Set the formatted YAML directly as text
            text_content.status = MsgStatus.success
            text_content.status_message = "Structured data generated"
            
            self.output_message.actions.append("Structure generation completed")
            self.output_message.push_update()
            
            logger.info("Structured data generated successfully")
            return AgentResponse(
                status=AgentStatus.SUCCESS,
                message="Structured data generated successfully",
                data={
                    "structured_data": structured_data,
                    "format": format,
                    "yaml_content": formatted_yaml  # Include formatted YAML in response
                }
            )
            
        except Exception as e:
            logger.error(f"Error in structure generation: {str(e)}", exc_info=True)
            if 'text_content' in locals():
                text_content.status = MsgStatus.error
                text_content.status_message = f"Structure generation failed: {str(e)}"
                self.output_message.push_update()
            return AgentResponse(
                status=AgentStatus.ERROR,
                message=str(e),
                data={"error": str(e)}
            ) 