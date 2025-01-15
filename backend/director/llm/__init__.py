import os

from director.constants import LLMType

from director.llm.openai import OpenAI
from director.llm.anthropic import AnthropicAI
from director.llm.videodb_proxy import VideoDBProxy


def get_default_llm():
    """Get default LLM"""
    default_llm = os.getenv("DEFAULT_LLM")

    # First check DEFAULT_LLM setting
    if default_llm == LLMType.OPENAI and os.getenv("OPENAI_API_KEY"):
        return OpenAI()
    elif default_llm == LLMType.ANTHROPIC and os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicAI()
    
    # If no DEFAULT_LLM, prioritize OpenAI
    if os.getenv("OPENAI_API_KEY"):
        return OpenAI()
    elif os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicAI()
    else:
        return VideoDBProxy()
