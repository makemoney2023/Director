import pytest
from unittest.mock import Mock, patch, call, MagicMock
from datetime import datetime
import json
import logging

from director.agents.sales_prompt_extractor import SalesPromptExtractorAgent
from director.core.session import Session, OutputMessage, RoleTypes, MsgStatus, TextContent
from director.llm.videodb_proxy import VideoDBProxy, VideoDBProxyConfig
from director.llm.anthropic import AnthropicAI, AnthropicAIConfig
from director.agents.base import AgentStatus
from director.tools.anthropic_tool import AnthropicTool
from director.llm.openai import OpenaiConfig, OpenAIChatModel, OpenAI
from director.core.db import BaseDB
from director.llm.base import LLMResponseStatus

# Sample test data
SAMPLE_TRANSCRIPT = """In this sales training, we use the SPIN selling technique.

First, ask Situation questions to understand the customer's context.

Then, Problem questions to uncover issues.

When handling price objections, always focus on value over cost.

Remember to use active listening and mirror the customer's language.

Close with a summary of benefits and clear next steps."""

SAMPLE_ANALYSIS = {
    "raw_analysis": SAMPLE_TRANSCRIPT,
    "structured_data": {
        "sales_techniques": [{
            "name": "SPIN Selling",
            "description": "Systematic approach using situation, problem, implication, and need-payoff questions",
            "examples": ["First, ask Situation questions"],
            "context": "Initial customer engagement"
        }],
        "communication_strategies": [{
            "type": "Active Listening",
            "description": "Pay attention and mirror customer's language",
            "application": "Throughout the conversation"
        }],
        "objection_handling": [{
            "objection_type": "Price concerns",
            "recommended_response": "Focus on value over cost",
            "examples": ["When handling price objections"]
        }],
        "closing_techniques": [{
            "name": "Benefit Summary Close",
            "description": "Summarize key benefits and establish next steps",
            "effectiveness": "When customer shows interest but needs final push"
        }]
    },
    "metadata": {
        "sections_found": ["sales_techniques", "communication_strategies", "objection_handling", "closing_techniques"],
        "total_techniques": 4
    }
}

@pytest.fixture
def mock_session():
    session = Mock(spec=Session)
    session.session_id = "test_session_id"
    session.conv_id = "test_conv_id"
    session.collection_id = "test_collection"
    session.db = Mock(spec=BaseDB)
    return session

@pytest.fixture
def mock_output_message():
    message = Mock(spec=OutputMessage)
    message.actions = []
    message.push_update = Mock()
    message.db = Mock(spec=BaseDB)
    message.content = []
    message.session_id = "test_session_id"
    message.conv_id = "test_conv_id"
    message.agents = ["test_agent"]
    return message

@pytest.fixture
def mock_llm():
    llm = Mock(spec=VideoDBProxy)
    llm.api_key = "test_key"
    llm.chat_completions = Mock()
    return llm

@pytest.fixture
def mock_config():
    return VideoDBProxyConfig(
        api_key="test_key",
        api_base="https://api.videodb.io",
        chat_model="gpt-4o-2024-11-20"
    )

@pytest.fixture
def mock_anthropic():
    mock = MagicMock(spec=AnthropicAI)
    mock.api_key = "test_key"
    mock.chat_completions = Mock()
    return mock

@pytest.fixture
def mock_anthropic_config():
    config = MagicMock(spec=AnthropicAIConfig)
    config.api_key = "test_key"
    return config

@pytest.fixture
def mock_logger():
    return Mock(spec=logging.Logger)

@pytest.fixture
def mock_anthropic_tool():
    mock = Mock()
    mock.chat_completions = Mock()
    return mock

@pytest.fixture
def mock_openai_config():
    config = MagicMock(spec=OpenaiConfig)
    config.api_key = "test_openai_key"
    config.chat_model = OpenAIChatModel.GPT4o
    config.max_tokens = 4096
    return config

@pytest.fixture
def mock_openai():
    mock = MagicMock(spec=OpenAI)
    mock.api_key = "test_openai_key"
    mock.chat_completions = Mock()
    return mock

@pytest.fixture
def agent(mock_session, mock_llm, mock_config, mock_anthropic, mock_anthropic_config, mock_anthropic_tool, mock_openai_config, mock_openai):
    with patch('director.llm.get_default_llm', return_value=mock_llm), \
         patch('director.llm.videodb_proxy.VideoDBProxyConfig', return_value=mock_config), \
         patch('director.llm.anthropic.AnthropicAI', return_value=mock_anthropic), \
         patch('director.llm.anthropic.AnthropicAIConfig', return_value=mock_anthropic_config), \
         patch('director.llm.openai.OpenaiConfig', return_value=mock_openai_config), \
         patch('director.llm.openai.OpenAI', return_value=mock_openai):
        agent = SalesPromptExtractorAgent(
            session=mock_session,
            analysis_llm=mock_anthropic_tool,
            openai_config=mock_openai_config,
            conversation_llm=mock_openai
        )
        # Mock the push_status_update method to properly handle status updates
        agent.push_status_update = Mock()
        agent.output_message = mock_output_message
        return agent

def test_get_transcript(agent):
    """Test transcript retrieval"""
    # Mock transcription agent response
    mock_response = Mock(status=AgentStatus.SUCCESS)
    mock_response.data = {"transcript": SAMPLE_TRANSCRIPT}
    agent.transcription_agent.run = Mock(return_value=mock_response)
    
    transcript = agent._get_transcript("test_video_id")
    assert transcript.strip() == SAMPLE_TRANSCRIPT.strip()

def test_analyze_content_status_updates(agent):
    """Test that _analyze_content properly updates status"""
    # Mock the LLM response
    mock_llm_response = Mock()
    mock_llm_response.content = json.dumps(SAMPLE_ANALYSIS["structured_data"])
    mock_llm_response.status = LLMResponseStatus.SUCCESS
    agent.analysis_llm.chat_completions = Mock(return_value=mock_llm_response)
    
    # Mock _get_analysis_prompt
    agent._get_analysis_prompt = Mock(return_value=[{
        "role": "system",
        "content": "Test prompt"
    }])
    
    # Call _analyze_content
    result = agent._analyze_content(SAMPLE_TRANSCRIPT, "full")
    
    # Verify status updates were called
    assert agent.output_message.push_update.called
    assert isinstance(result, dict)
    assert "structured_data" in result

def test_generate_prompt_status_updates(agent):
    """Test that _generate_prompt properly updates status"""
    # Mock the LLM responses
    mock_system_response = Mock()
    mock_system_response.content = "Test system prompt"
    mock_system_response.status = LLMResponseStatus.SUCCESS
    
    mock_conv_response = Mock()
    mock_conv_response.content = json.dumps({"conversations": [{
        "title": "Test Conversation",
        "conversation": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"}
        ]
    }]})
    mock_conv_response.status = LLMResponseStatus.SUCCESS
    
    # Setup the mock to return different responses
    agent.analysis_llm.chat_completions = Mock(side_effect=[
        mock_system_response,
        mock_conv_response
    ])
    
    # Call _generate_prompt
    result = agent._generate_prompt(SAMPLE_ANALYSIS)
    
    # Verify status updates were called
    assert agent.output_message.push_update.called
    assert isinstance(result, dict)
    assert "system_prompt" in result
    assert "example_conversations" in result

def test_error_handling_with_status(agent):
    """Test error handling with proper status updates"""
    # Mock the LLM to raise an exception
    agent.analysis_llm.chat_completions = Mock(side_effect=Exception("API Error"))
    
    # Mock _get_analysis_prompt
    agent._get_analysis_prompt = Mock(return_value=[{
        "role": "system",
        "content": "Test prompt"
    }])
    
    # Call _analyze_content and expect it to fail
    with pytest.raises(Exception):
        agent._analyze_content(SAMPLE_TRANSCRIPT, "full")
    
    # Verify error status was sent
    assert agent.output_message.push_update.called

def test_conversation_parsing_fallback(agent):
    """Test the fallback mechanism for conversation parsing"""
    # Mock the LLM to return invalid JSON
    mock_response = Mock()
    mock_response.content = "Invalid JSON content"
    mock_response.status = LLMResponseStatus.SUCCESS
    agent.analysis_llm.chat_completions = Mock(return_value=mock_response)
    
    # Call _generate_prompt
    result = agent._generate_prompt(SAMPLE_ANALYSIS)
    
    # Verify fallback behavior
    assert isinstance(result, dict)
    assert "system_prompt" in result
    assert "example_conversations" in result
    assert len(result["example_conversations"]) > 0

def test_full_workflow(agent, mock_output_message):
    """Test the complete workflow"""
    # Mock all dependent functions
    agent._get_transcript = Mock(return_value=SAMPLE_TRANSCRIPT)
    agent._analyze_content = Mock(return_value=SAMPLE_ANALYSIS)
    agent._generate_prompt = Mock(return_value={
        "system_prompt": "Test prompt",
        "first_message": "Hello",
        "example_conversations": [],
        "metadata": {}
    })
    
    # Set up output message
    agent.output_message = mock_output_message
    
    # Run the agent
    response = agent.run("test_video_id")
    assert response.status == AgentStatus.SUCCESS

def test_structure_analysis_json(mock_session, mock_llm, mock_config, mock_anthropic, mock_anthropic_config, mock_logger, mock_anthropic_tool, mock_openai_config, mock_openai, mock_output_message):
    """Test structured analysis output"""
    with patch('director.llm.get_default_llm', return_value=mock_llm), \
         patch('director.llm.videodb_proxy.VideoDBProxyConfig', return_value=mock_config), \
         patch('director.llm.anthropic.AnthropicAI', return_value=mock_anthropic), \
         patch('director.llm.anthropic.AnthropicAIConfig', return_value=mock_anthropic_config), \
         patch('director.agents.sales_prompt_extractor.logger', mock_logger), \
         patch('director.llm.openai.OpenaiConfig', return_value=mock_openai_config), \
         patch('director.llm.openai.OpenAI', return_value=mock_openai):
        agent = SalesPromptExtractorAgent(
            mock_session,
            analysis_llm=mock_anthropic_tool,
            openai_config=mock_openai_config,
            conversation_llm=mock_openai
        )
        
        # Mock the analysis response
        mock_analysis = {
            "structured_data": {
                "sales_techniques": [{"name": "Test Technique", "description": "Test description"}],
                "communication_strategies": [{"type": "Test Strategy", "description": "Test strategy description"}],
                "objection_handling": [{"objection_type": "Test Objection", "recommended_response": "Test response"}],
                "closing_techniques": [{"name": "Test Close", "description": "Test closing description"}]
            },
            "raw_analysis": "Test raw analysis",
            "metadata": {
                "sections_found": ["sales_techniques"],
                "total_techniques": 1
            }
        }
        
        # Mock all required methods
        agent._get_transcript = Mock(return_value=SAMPLE_TRANSCRIPT)
        agent._analyze_content = Mock(return_value=mock_analysis)
        agent._generate_prompt = Mock(return_value={
            "system_prompt": "Test prompt",
            "first_message": "Hello",
            "example_conversations": [],
            "metadata": {}
        })
        
        # Set up output message
        agent.output_message = mock_output_message
        
        # Run the test with structured output format
        response = agent.run("test_video_id", analysis_type="sales_techniques", output_format="structured")
        
        # Verify the response
        assert response.status == AgentStatus.SUCCESS

def test_structure_analysis_fallback(mock_session, mock_llm, mock_config, mock_anthropic, mock_anthropic_config, mock_logger, mock_anthropic_tool, mock_openai_config, mock_openai, mock_output_message):
    """Test analysis fallback behavior"""
    with patch('director.llm.get_default_llm', return_value=mock_llm), \
         patch('director.llm.videodb_proxy.VideoDBProxyConfig', return_value=mock_config), \
         patch('director.llm.anthropic.AnthropicAI', return_value=mock_anthropic), \
         patch('director.llm.anthropic.AnthropicAIConfig', return_value=mock_anthropic_config), \
         patch('director.agents.sales_prompt_extractor.logger', mock_logger), \
         patch('director.llm.openai.OpenaiConfig', return_value=mock_openai_config), \
         patch('director.llm.openai.OpenAI', return_value=mock_openai):
        agent = SalesPromptExtractorAgent(
            mock_session,
            analysis_llm=mock_anthropic_tool,
            openai_config=mock_openai_config,
            conversation_llm=mock_openai
        )
        
        # Mock an invalid analysis response that will fail JSON parsing
        agent._analyze_content = Mock(side_effect=json.JSONDecodeError("Failed to parse", "{", 0))
        agent._get_transcript = Mock(return_value=SAMPLE_TRANSCRIPT)
        
        # Set up output message
        agent.output_message = mock_output_message
        
        response = agent.run("test_video_id")
        assert response.status == AgentStatus.ERROR
        # Check that the error message contains the JSON parse error
        assert "Failed to parse" in response.message 