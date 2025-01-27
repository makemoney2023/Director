import json
import time
from enum import Enum
from openai import OpenAI, RateLimitError, APIError, APITimeoutError

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
    GPT4_TURBO_PREVIEW = "gpt-4-turbo-preview"
    GPT35_TURBO = "gpt-3.5-turbo"
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
    chat_model: str = Field(default=OpenAIChatModel.GPT4o_MINI)
    max_tokens: int = 8096

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

    @property
    def chat_model(self) -> str:
        return self._chat_model

    @chat_model.setter
    def chat_model(self, value: str):
        self._chat_model = value

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

        max_retries = 3
        base_delay = 1  # Base delay in seconds

        for attempt in range(max_retries):
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
                            content="",
                            status=LLMResponseStatus.ERROR,
                            error=str(e),
                            error_type="JSONDecodeError"
                        )
                
                # Successful response
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
                    error="",
                    error_type=""
                )

            except RateLimitError as e:
                error_msg = f"Rate limit exceeded: {str(e)}"
                if attempt < max_retries - 1:
                    delay = (base_delay * (2 ** attempt))  # Exponential backoff
                    time.sleep(delay)
                    continue
                return LLMResponse(
                    content="",
                    status=LLMResponseStatus.ERROR,
                    error=error_msg,
                    error_type="RateLimitError"
                )

            except APITimeoutError as e:
                error_msg = f"Request timed out: {str(e)}"
                if attempt < max_retries - 1:
                    continue
                return LLMResponse(
                    content="",
                    status=LLMResponseStatus.ERROR,
                    error=error_msg,
                    error_type="TimeoutError"
                )

            except APIError as e:
                error_msg = f"API error: {str(e)}"
                if attempt < max_retries - 1 and "internal_server_error" in str(e).lower():
                    time.sleep(base_delay)
                    continue
                return LLMResponse(
                    content="",
                    status=LLMResponseStatus.ERROR,
                    error=error_msg,
                    error_type="APIError"
                )

            except Exception as e:
                error_msg = str(e)
                error_type = type(e).__name__
                print(f"Error: {error_msg}")
                return LLMResponse(
                    content="",
                    status=LLMResponseStatus.ERROR,
                    error=error_msg,
                    error_type=error_type
                )
