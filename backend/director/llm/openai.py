import json
from enum import Enum

from pydantic import Field, field_validator, FieldValidationInfo
from pydantic_settings import SettingsConfigDict


from director.llm.base import BaseLLM, BaseLLMConfig, LLMResponse, LLMResponseStatus
from director.constants import (
    LLMType,
    EnvPrefix,
)


class OpenAIChatModel(str, Enum):
    """Enum for OpenAI Chat models"""

    GPT4 = "gpt-4"
    GPT4_32K = "gpt-4-32k"
    GPT4_TURBO = "gpt-4-turbo"
    GPT4o = "gpt-4o-2024-11-20"
    GPT4o_MINI = "gpt-4o-mini"


class OpenaiConfig(BaseLLMConfig):
    """OpenAI Config"""

    model_config = SettingsConfigDict(
        env_prefix=EnvPrefix.OPENAI_,
        extra="ignore",
    )

    llm_type: str = LLMType.OPENAI
    api_key: str = ""
    api_base: str = "https://api.openai.com/v1"
    chat_model: str = Field(default=OpenAIChatModel.GPT4o)
    max_tokens: int = 4096

    @field_validator("api_key")
    @classmethod
    def validate_non_empty(cls, v, info: FieldValidationInfo):
        if not v:
            raise ValueError(
                f"{info.field_name} must not be empty. please set {EnvPrefix.OPENAI_.value}{info.field_name.upper()} environment variable."
            )
        return v


class OpenAI(BaseLLM):
    def __init__(self, config: OpenaiConfig = None):
        """
        :param config: OpenAI Config
        """
        if config is None:
            config = OpenaiConfig()
        super().__init__(config=config)
        try:
            import openai
        except ImportError:
            raise ImportError("Please install OpenAI python library.")

        self.client = openai.OpenAI(api_key=self.api_key, base_url=self.api_base)

    def init_langfuse(self):
        from langfuse.decorators import observe

        self.chat_completions = observe(name=type(self).__name__)(self.chat_completions)
        self.text_completions = observe(name=type(self).__name__)(self.text_completions)

    def _format_messages(self, messages: list):
        """Format the messages to the format that OpenAI expects."""
        formatted_messages = []
        for message in messages:
            if message["role"] == "assistant" and message.get("tool_calls"):
                formatted_messages.append(
                    {
                        "role": message["role"],
                        "content": message["content"],
                        "tool_calls": [
                            {
                                "id": tool_call["id"],
                                "function": {
                                    "name": tool_call["tool"]["name"],
                                    "arguments": json.dumps(
                                        tool_call["tool"]["arguments"]
                                    ),
                                },
                                "type": tool_call["type"],
                            }
                            for tool_call in message["tool_calls"]
                        ],
                    }
                )
            else:
                formatted_messages.append(message)
        return formatted_messages

    def _format_tools(self, tools: list):
        """Format the tools to the format that OpenAI expects.

        **Example**::

            [
                {
                    "type": "function",
                    "function": {
                        "name": "get_delivery_date",
                        "description": "Get the delivery date for a customer's order.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "order_id": {
                                    "type": "string",
                                    "description": "The customer's order ID."
                                }
                            },
                            "required": ["order_id"],
                            "additionalProperties": False
                        }
                    }
                }
            ]
        """
        formatted_tools = []
        for tool in tools:
            formatted_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["parameters"],
                    },
                    "strict": True,
                }
            )
        return formatted_tools

    def chat_completions(
        self, messages: list, tools: list = [], stop=None, response_format=None
    ):
        """Get completions for chat.

        docs: https://platform.openai.com/docs/guides/function-calling
        """
        params = {
            "model": self.chat_model,
            "messages": self._format_messages(messages),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "stop": stop,
            "timeout": self.timeout,
        }
        if tools:
            params["tools"] = self._format_tools(tools)
            params["tool_choice"] = "auto"

        if response_format:
            # Ensure response_format is properly formatted for the API
            if isinstance(response_format, dict) and "type" in response_format:
                params["response_format"] = response_format
            else:
                # Default to JSON response format if not properly specified
                params["response_format"] = {"type": "json_object"}

        try:
            response = self.client.chat.completions.create(**params)
            content = response.choices[0].message.content
            # Validate JSON response if response_format is specified
            if response_format and content:
                try:
                    content = json.loads(content)
                    content = json.dumps(content)  # Re-serialize to ensure valid JSON string
                except json.JSONDecodeError as e:
                    return LLMResponse(
                        content=str(e),
                        status=LLMResponseStatus.ERROR,
                        error_type="JSONDecodeError"
                    )
        except Exception as e:
            print(f"Error: {e}")
            return LLMResponse(
                content=f"Error: {e}",
                status=LLMResponseStatus.ERROR,
                error_type=type(e).__name__
            )

        return LLMResponse(
            content=content or "",
            tool_calls=[
                {
                    "id": tool_call.id,
                    "tool": {
                        "name": tool_call.function.name,
                        "arguments": json.loads(tool_call.function.arguments),
                    },
                    "type": tool_call.type,
                }
                for tool_call in response.choices[0].message.tool_calls
            ]
            if response.choices[0].message.tool_calls
            else [],
            finish_reason=response.choices[0].finish_reason,
            send_tokens=response.usage.prompt_tokens,
            recv_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            status=LLMResponseStatus.SUCCESS,
        )
