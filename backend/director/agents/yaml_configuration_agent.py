import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import yaml
from pydantic import BaseModel

from director.agents.base import BaseAgent, AgentResponse, AgentStatus
from director.core.session import TextContent, MsgStatus, OutputMessage, Session
from director.tools.anthropic_tool import AnthropicTool
from director.llm.base import LLMResponseStatus

logger = logging.getLogger(__name__)

class YAMLContent(TextContent):
    """Content type for YAML configuration results"""
    yaml_data: Dict = {}
    config_metadata: Dict = {}
    
    def __init__(self, yaml_data: Dict = None, config_metadata: Dict = None, **kwargs):
        super().__init__(**kwargs)
        self.yaml_data = yaml_data if yaml_data is not None else {}
        self.config_metadata = config_metadata if config_metadata is not None else {}

    def to_dict(self) -> Dict:
        base_dict = super().to_dict()
        base_dict.update({
            "yaml_data": self.yaml_data,
            "config_metadata": self.config_metadata
        })
        return base_dict

class YAMLConfigurationAgent(BaseAgent):
    """Agent for generating YAML configurations from analysis and structured data"""
    
    def __init__(self, session: Session, **kwargs):
        self.agent_name = "yaml_configuration"
        self.description = "Generates YAML configurations for system settings"
        self.parameters = self.get_parameters()
        super().__init__(session=session, **kwargs)
        
        # Initialize Anthropic
        self.config_llm = kwargs.get('config_llm') or AnthropicTool()

    def get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "string",
                    "description": "The sales analysis to configure"
                },
                "structured_data": {
                    "type": "object",
                    "description": "The structured data to configure"
                },
                "config_type": {
                    "type": "string",
                    "enum": ["voice", "system", "training", "complete"],
                    "default": "complete",
                    "description": "The type of configuration to generate"
                }
            },
            "required": ["analysis", "structured_data"],
            "description": "Generates YAML configurations from analysis and structured data"
        }

    def _get_config_prompt(self, analysis: str, structured_data: Dict, config_type: str) -> List[Dict[str, str]]:
        """Generate appropriate prompt for YAML configuration generation"""
        system_prompt = """You are an expert in creating YAML configurations for AI systems. Your task is to generate clear, well-organized YAML configurations that capture all necessary settings and parameters.

Your output must be valid YAML and should include:

1. SYSTEM SETTINGS
- Environment configurations
- API integrations
- Performance parameters
- Logging settings

2. VOICE PARAMETERS
- Tone configurations
- Pacing settings
- Adaptation parameters
- Expression controls

3. TRAINING SETTINGS
- Model parameters
- Data processing rules
- Validation settings
- Quality thresholds

4. INTEGRATION CONFIGS
- API endpoints
- Authentication settings
- Rate limiting
- Error handling

5. MONITORING SETUP
- Performance metrics
- Quality indicators
- Alert thresholds
- Logging levels

FORMAT REQUIREMENTS:
1. Use clear, hierarchical structure
2. Include comments for clarity
3. Group related settings
4. Use consistent indentation
5. Follow YAML best practices

The output should be immediately usable for system configuration."""

        user_prompt = f"""Convert this analysis and structured data into a {config_type} YAML configuration.

The configuration should:
1. Capture all necessary settings
2. Use clear hierarchical structure
3. Include helpful comments
4. Follow YAML best practices
5. Be immediately usable

Analysis:
{analysis}

Structured Data:
{structured_data}

Remember to:
- Use consistent formatting
- Group related settings
- Add descriptive comments
- Include all required parameters"""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

    def _find_similar_configs(self, config_type: str) -> List[Dict]:
        """Find similar YAML configurations in the codebase"""
        try:
            # For now, return empty list until we implement proper config search
            return []
        except Exception as e:
            logger.warning(f"Error finding similar configs: {str(e)}")
            return []

    def _save_config(self, config: Dict, config_type: str) -> str:
        """Save the YAML configuration to a file"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"config/{config_type}_config_{timestamp}.yaml"
            
            # Convert to YAML with comments preserved
            yaml_content = yaml.dump(
                config,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
                width=80,
                indent=2
            )
            
            # Ensure config directory exists
            import os
            os.makedirs("config", exist_ok=True)
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(yaml_content)
            
            return filename
        except Exception as e:
            logger.warning(f"Error saving configuration: {str(e)}")
            return None

    def _validate_yaml(self, content: str) -> Dict:
        """Validate and clean YAML content"""
        try:
            # First try to parse as is
            return yaml.safe_load(content)
        except yaml.YAMLError:
            # If fails, try to extract YAML from markdown
            try:
                # Look for YAML code blocks
                if "```yaml" in content:
                    yaml_content = content.split("```yaml")[1].split("```")[0]
                    return yaml.safe_load(yaml_content)
                # Look for YAML content
                elif "---" in content:
                    return yaml.safe_load(content)
                else:
                    raise ValueError("Could not extract valid YAML from content")
            except Exception as e:
                raise ValueError(f"YAML validation failed: {str(e)}")

    def run(
        self,
        analysis: str,
        structured_data: Dict,
        config_type: str = "complete",
        *args,
        **kwargs
    ) -> AgentResponse:
        """Generate YAML configuration from analysis and structured data"""
        try:
            if not analysis or not structured_data:
                raise ValueError("Both analysis and structured data are required")

            # Initialize content
            text_content = YAMLContent(
                yaml_data={},
                config_metadata={},
                agent_name=self.agent_name,
                status=MsgStatus.progress,
                status_message="Starting configuration generation...",
                text="Processing inputs..."
            )
            self.output_message.add_content(text_content)
            self.output_message.actions.append("Beginning configuration generation...")
            self.output_message.push_update()

            # Find similar configurations for context
            similar_configs = self._find_similar_configs(config_type)

            # Generate configuration
            messages = self._get_config_prompt(analysis, structured_data, config_type)
            
            logger.info("Requesting configuration generation from Anthropic")
            response = self.config_llm.chat_completions(
                messages=messages,
                temperature=0.7,
                max_tokens=4096
            )
            
            if response.status == LLMResponseStatus.ERROR:
                raise Exception(f"Anthropic configuration generation failed: {response.message}")

            # Validate and clean YAML
            yaml_data = self._validate_yaml(response.content)

            # Add metadata
            config_metadata = {
                "version": "1.0",
                "timestamp": datetime.now().isoformat(),
                "config_type": config_type,
                "source": {
                    "analysis": True,
                    "structured_data": True
                }
            }
            yaml_data["metadata"] = config_metadata

            # Save the configuration
            config_file = self._save_config(yaml_data, config_type)

            # Store results
            text_content.yaml_data = yaml_data
            text_content.config_metadata = config_metadata
            text_content.text = yaml.dump(yaml_data, default_flow_style=False)
            text_content.status = MsgStatus.success
            text_content.status_message = "Configuration generated"
            
            self.output_message.actions.append("Configuration generation completed")
            self.output_message.push_update()
            
            logger.info("YAML configuration generated successfully")
            return AgentResponse(
                status=AgentStatus.SUCCESS,
                message="Configuration generated successfully",
                data={
                    "yaml_data": yaml_data,
                    "config_type": config_type,
                    "similar_configs": similar_configs,
                    "config_file": config_file
                }
            )
            
        except Exception as e:
            logger.error(f"Error in configuration generation: {str(e)}", exc_info=True)
            if 'text_content' in locals():
                text_content.status = MsgStatus.error
                text_content.status_message = f"Configuration generation failed: {str(e)}"
                self.output_message.push_update()
            return AgentResponse(
                status=AgentStatus.ERROR,
                message=str(e),
                data={"error": str(e)}
            ) 