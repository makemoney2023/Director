import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import yaml
from pydantic import BaseModel
import json

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
        system_prompt = """You are an expert in creating YAML configurations for AI voice agents. Your task is to generate clear, well-organized YAML configurations that capture all necessary settings and parameters.

Your output must be valid YAML and should include:

1. METADATA
- Version information
- Generation timestamp
- Model configurations
- Usage guidelines

2. VOICE SETTINGS
- Base characteristics
  * Tone parameters
  * Pacing controls
  * Expression settings
- Adaptation rules
  * Context-based adjustments
  * Emotional responses
  * Energy level modulation

3. CONVERSATION FRAMEWORK
- Opening strategies
- Discovery techniques
- Solution presentation
- Objection handling
- Closing approaches

4. COMMUNICATION PATTERNS
- Response templates
- Key phrases
- Transition strategies
- Recovery patterns

5. BEHAVIORAL GUIDELINES
- Core principles
- Ethical boundaries
- Professional standards
- Adaptation rules

FORMAT REQUIREMENTS:
1. Use clear, hierarchical structure
2. Include descriptive comments
3. Group related settings
4. Use consistent indentation
5. Follow YAML best practices

The output should be immediately usable for voice agent configuration."""

        user_prompt = f"""Convert this analysis and structured data into a {config_type} YAML configuration for an AI voice agent.

The configuration should:
1. Capture all voice and conversation parameters
2. Include behavioral guidelines
3. Define adaptation rules
4. Specify communication patterns
5. Set quality thresholds

Analysis:
{analysis}

Structured Data:
{json.dumps(structured_data, indent=2)}

Required sections:
1. metadata
2. voice_settings
3. conversation_framework
4. communication_patterns
5. behavioral_guidelines
6. quality_thresholds

Remember to:
- Use descriptive comments
- Include all techniques from the analysis
- Define clear adaptation rules
- Specify response patterns
- Set appropriate thresholds"""

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
            
            # Add header comments
            header_comment = f"""# AI Voice Agent Configuration
# Type: {config_type}
# Generated: {datetime.now().isoformat()}
# 
# This configuration file defines the behavior and characteristics
# of an AI voice agent for sales conversations. It includes:
# - Voice characteristics and adaptation rules
# - Conversation framework and patterns
# - Communication strategies and guidelines
# - Quality thresholds and monitoring parameters
#
"""
            
            # Convert to YAML with comments preserved
            yaml_content = yaml.dump(
                config,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
                width=80,
                indent=2
            )
            
            # Combine header and content
            full_content = header_comment + yaml_content
            
            # Ensure config directory exists
            import os
            os.makedirs("config", exist_ok=True)
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(full_content)
            
            return filename
        except Exception as e:
            logger.warning(f"Error saving configuration: {str(e)}")
            return None

    def _validate_yaml(self, content: str) -> Dict:
        """Validate and clean YAML content"""
        try:
            # First try to parse as is
            yaml_data = yaml.safe_load(content)
            
            # Validate required sections
            required_sections = [
                "metadata",
                "voice_settings",
                "conversation_framework",
                "communication_patterns",
                "behavioral_guidelines",
                "quality_thresholds"
            ]
            
            missing_sections = [section for section in required_sections if section not in yaml_data]
            if missing_sections:
                raise ValueError(f"Missing required sections: {', '.join(missing_sections)}")
            
            # Validate voice settings
            if "voice_settings" in yaml_data:
                required_voice_settings = ["tone", "pacing", "expression", "adaptation"]
                missing_voice_settings = [setting for setting in required_voice_settings 
                                        if setting not in yaml_data["voice_settings"]]
                if missing_voice_settings:
                    raise ValueError(f"Missing required voice settings: {', '.join(missing_voice_settings)}")
            
            return yaml_data
            
        except yaml.YAMLError:
            # If fails, try to extract YAML from markdown
            try:
                # Look for YAML code blocks
                if "```yaml" in content:
                    yaml_content = content.split("```yaml")[1].split("```")[0]
                    return self._validate_yaml(yaml_content)
                # Look for YAML content
                elif "---" in content:
                    return self._validate_yaml(content)
                else:
                    raise ValueError("Could not extract valid YAML from content")
            except Exception as e:
                raise ValueError(f"YAML validation failed: {str(e)}")

    def _generate_yaml_config(self, analysis: str, structured_data: Dict) -> str:
        """Generate YAML configuration from analysis and structured data"""
        try:
            # Extract key components from structured data
            sales_techniques = structured_data.get("sales_techniques", [])
            communication_strategies = structured_data.get("communication_strategies", [])
            objection_handling = structured_data.get("objection_handling", [])
            voice_guidelines = structured_data.get("voice_agent_guidelines", [])
            
            # Build YAML configuration
            config = {
                "metadata": {
                    "version": "1.0",
                    "type": "voice_agent_config",
                    "generated_at": datetime.now().isoformat(),
                    "description": "AI Voice Sales Agent Configuration"
                },
                "voice_settings": {
                    "tone": {
                        "base_characteristics": {
                            "pitch": "medium",
                            "rate": "moderate",
                            "energy": "balanced"
                        },
                        "emotional_mapping": {
                            "positive": {"pitch": "medium-high", "rate": "moderate", "energy": "high"},
                            "neutral": {"pitch": "medium", "rate": "moderate", "energy": "medium"},
                            "negative": {"pitch": "medium-low", "rate": "slower", "energy": "low"}
                        }
                    },
                    "adaptation_rules": {
                        "customer_signals": [s.get("signal", "") for s in structured_data.get("customer_signals", [])],
                        "response_patterns": [r.get("pattern", "") for r in structured_data.get("response_patterns", [])]
                    }
                },
                "conversation_framework": {
                    "opening": {
                        "techniques": [t.get("name", "") for t in sales_techniques if "open" in t.get("name", "").lower()],
                        "key_phrases": [p for p in structured_data.get("key_phrases", []) if any(w in p.lower() for w in ["hello", "welcome", "introduction"])]
                    },
                    "discovery": {
                        "techniques": [t.get("name", "") for t in sales_techniques if "question" in t.get("name", "").lower()],
                        "strategies": [s.get("type", "") for s in communication_strategies if "discovery" in s.get("type", "").lower()]
                    },
                    "presentation": {
                        "techniques": [t.get("name", "") for t in sales_techniques if "present" in t.get("name", "").lower()],
                        "value_props": [p for p in structured_data.get("key_phrases", []) if "value" in p.lower()]
                    },
                    "objection_handling": {
                        "patterns": [{"objection": o.get("objection", ""), "response": o.get("response", "")} for o in objection_handling],
                        "recovery_strategies": [s.get("type", "") for s in communication_strategies if "recovery" in s.get("type", "").lower()]
                    },
                    "closing": {
                        "techniques": [t.get("name", "") for t in sales_techniques if "clos" in t.get("name", "").lower()],
                        "signals": [s.get("signal", "") for s in structured_data.get("success_markers", [])]
                    }
                },
                "behavioral_guidelines": {
                    "core_principles": [g.get("description", "") for g in voice_guidelines if g.get("type") == "do"],
                    "avoid_patterns": [g.get("description", "") for g in voice_guidelines if g.get("type") == "dont"],
                    "professional_standards": [
                        "Maintain professional tone and language",
                        "Focus on customer needs",
                        "Practice active listening",
                        "Show genuine interest",
                        "Be transparent and honest"
                    ]
                },
                "quality_thresholds": {
                    "response_time": "2-3 seconds",
                    "interruption_handling": "graceful pause and acknowledgment",
                    "clarity_threshold": "95% comprehension rate",
                    "engagement_metrics": {
                        "min_turn_length": "10 words",
                        "max_turn_length": "100 words",
                        "ideal_pace": "150-180 words per minute"
                    }
                }
            }
            
            # Convert to YAML
            return yaml.dump(config, sort_keys=False, allow_unicode=True)
            
        except Exception as e:
            logger.error(f"Error generating YAML config: {str(e)}", exc_info=True)
            return ""

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

            # Generate configuration
            messages = self._get_config_prompt(analysis, structured_data, config_type)
            
            logger.info("Requesting configuration generation from Anthropic")
            response = self.config_llm.chat_completions(
                messages=messages,
                temperature=0.7,
                max_tokens=4096
            )
            
            if response.status == LLMResponseStatus.ERROR:
                raise Exception(f"Configuration generation failed: {response.message}")

            # Validate and clean YAML
            yaml_data = self._validate_yaml(response.content)

            # Add metadata
            config_metadata = {
                "version": "1.0",
                "generated_at": datetime.now().isoformat(),
                "config_type": config_type,
                "source": {
                    "analysis": True,
                    "structured_data": True
                },
                "model": {
                    "name": "anthropic-claude",
                    "temperature": 0.7
                }
            }
            
            # Update metadata section
            if "metadata" not in yaml_data:
                yaml_data["metadata"] = {}
            yaml_data["metadata"].update(config_metadata)

            # Save the configuration
            config_file = self._save_config(yaml_data, config_type)

            # Store results
            text_content.yaml_data = yaml_data
            text_content.config_metadata = config_metadata
            text_content.text = yaml.dump(yaml_data, default_flow_style=False)
            text_content.status = MsgStatus.success
            text_content.status_message = "Configuration generated successfully"
            
            self.output_message.actions.append("Configuration generation completed")
            self.output_message.push_update()
            
            logger.info("YAML configuration generated successfully")
            return AgentResponse(
                status=AgentStatus.SUCCESS,
                message="Configuration generated successfully",
                data={
                    "yaml_config": yaml_data,
                    "config_type": config_type,
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