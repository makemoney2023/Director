from enum import Enum
import time
from tenacity import retry, stop_after_attempt, wait_exponential
import logging

from pydantic import Field, field_validator, FieldValidationInfo
from pydantic_settings import SettingsConfigDict

from director.core.session import RoleTypes
from director.llm.base import BaseLLM, BaseLLMConfig, LLMResponse, LLMResponseStatus
from director.constants import (
    LLMType,
    EnvPrefix,
)

logger = logging.getLogger(__name__)


class AnthropicChatModel(str, Enum):
    """Enum for Anthropic Chat models"""

    CLAUDE_3_HAIKU = "claude-3-haiku-20240307"
    CLAUDE_3_OPUS = "claude-3-opus-20240229"
    CLAUDE_3_5_SONNET = "claude-3-5-sonnet-20240620"
    CLAUDE_3_5_SONNET_LATEST = "claude-3-5-sonnet-20241022"


class AnthropicAIConfig(BaseLLMConfig):
    """AnthropicAI Config"""

    model_config = SettingsConfigDict(
        env_prefix=EnvPrefix.ANTHROPIC_,
        extra="ignore",
    )

    llm_type: str = LLMType.ANTHROPIC
    api_key: str = Field(default="")
    api_base: str = ""
    chat_model: str = Field(default=AnthropicChatModel.CLAUDE_3_5_SONNET_LATEST)

    @field_validator("api_key")
    @classmethod
    def validate_non_empty(cls, v, info: FieldValidationInfo):
        if not v:
            raise ValueError(
                f"{info.field_name} must not be empty. please set {EnvPrefix.OPENAI_.value}{info.field_name.upper()} environment variable."
            )
        return v


class AnthropicAI(BaseLLM):
    def __init__(self, config: AnthropicAIConfig = None):
        """
        :param config: AnthropicAI Config
        """
        if config is None:
            config = AnthropicAIConfig()
        super().__init__(config=config)
        try:
            import anthropic
        except ImportError:
            raise ImportError("Please install Anthropic python library.")

        self.client = anthropic.Anthropic(api_key=self.api_key)

    def _format_messages(self, messages: list):
        """Format messages for Anthropic's API, handling system messages correctly"""
        system = ""
        formatted_messages = []
        
        # Extract system message if present
        if messages and messages[0]["role"] == RoleTypes.system:
            system = messages[0]["content"]
            messages = messages[1:]

        # Format remaining messages
        for message in messages:
            if message["role"] == RoleTypes.assistant and message.get("tool_calls"):
                tool = message["tool_calls"][0]["tool"]
                formatted_messages.append({
                    "role": "assistant",
                    "content": message["content"]
                })
            elif message["role"] == RoleTypes.tool:
                formatted_messages.append({
                    "role": "user",
                    "content": message["content"]
                })
            else:
                # Convert system role to assistant for non-first messages
                role = "assistant" if message["role"] == RoleTypes.system else message["role"]
                formatted_messages.append({
                    "role": role,
                    "content": message["content"]
                })

        return system, formatted_messages

    def _format_tools(self, tools: list):
        """Format the tools to the format that Anthropic expects.

        **Example**::

            [
                {
                    "name": "get_weather",
                    "description": "Get the current weather in a given location",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city and state, e.g. San Francisco, CA",
                            }
                        },
                        "required": ["location"],
                    },
                }
            ]
        """
        formatted_tools = []
        for tool in tools:
            formatted_tools.append(
                {
                    "name": tool["name"],
                    "description": tool["description"],
                    "input_schema": tool["parameters"],
                }
            )
        return formatted_tools

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    def chat_completions(self, messages: list, tools: list = [], stop=None, response_format=None):
        """Get completions for chat."""
        system, messages = self._format_messages(messages)
        
        # Build parameters for Anthropic's API
        params = {
            "model": self.chat_model,
            "messages": messages,
            "max_tokens": self.max_tokens
        }
        
        # Add system message if present
        if system:
            params["system"] = system
            
        # Add tools if present
        if tools:
            params["tools"] = self._format_tools(tools)

        try:
            response = self.client.messages.create(**params)
            # Add a small delay between requests to respect rate limits
            time.sleep(0.5)
            return LLMResponse(
                content=response.content[0].text,
                tool_calls=[],  # Handle tool calls if needed
                send_tokens=response.usage.input_tokens,
                recv_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens,
                finish_reason=response.stop_reason,
                status=LLMResponseStatus.SUCCESS
            )
        except Exception as e:
            logger.error(f"Error in Anthropic API call: {str(e)}")
            raise  # Let the retry decorator handle the retry logic
