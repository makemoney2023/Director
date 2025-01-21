## OpenAI

OpenAI extends the Base LLM and implements the OpenAI API.

### OpenAI Config

OpenAI Config is the configuration object for OpenAI. It is used to configure OpenAI and is passed to OpenAI when it is created.

Configuration Options:
- `api_key`: OpenAI API key (required)
- `api_base`: API base URL (default: https://api.openai.com/v1)
- `chat_model`: Model to use (default: gpt-4o)
- `max_tokens`: Maximum tokens per response (default: 4096)
- `temperature`: Response randomness (default: 0.9)
- `top_p`: Nucleus sampling parameter (default: 1)
- `timeout`: Request timeout in seconds (default: 30)

::: director.llm.openai.OpenaiConfig

### OpenAI Interface

OpenAI is the LLM used by the agents and tools. It is used to generate responses to messages.

#### Error Handling
The implementation handles several types of errors:
- Timeout errors: Requests exceeding the timeout limit
- Rate limit errors: When API rate limits are reached
- Invalid API key errors: Authentication issues
- Model errors: Issues with model availability or context length

#### Response Formats
Supports two main response formats:
1. Standard text responses
2. JSON-structured responses (using response_format parameter)

Example JSON response format:
```python
response = llm.chat_completions(
    messages=[{"role": "user", "content": "Return JSON"}],
    response_format={"type": "json_object"}
)
```

#### Tool Usage
Supports function calling through tools parameter:
```python
tools = [{
    "name": "get_data",
    "description": "Get data from source",
    "parameters": {
        "type": "object",
        "properties": {
            "id": {"type": "string"}
        }
    }
}]
response = llm.chat_completions(messages=messages, tools=tools)
```

::: director.llm.openai.OpenAI

### Available Models
The following models are supported:
- `gpt-4`: Standard GPT-4 model
- `gpt-4-32k`: Extended context GPT-4
- `gpt-4-turbo`: Latest GPT-4 turbo model
- `gpt-4-turbo-preview`: Preview version of GPT-4 turbo
- `gpt-3.5-turbo`: GPT-3.5 turbo model
- `gpt-4o`: Optimized GPT-4 model
- `gpt-4o-mini`: Smaller optimized GPT-4 model
