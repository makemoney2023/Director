import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime
import json

from director.agents.sales_prompt_extractor import SalesPromptExtractorAgent
from director.core.session import Session, OutputMessage, RoleTypes, MsgStatus
from director.llm.videodb_proxy import VideoDBProxy, VideoDBProxyConfig
from director.agents.base import AgentStatus

# Sample test data
SAMPLE_TRANSCRIPT = """
In this sales training, we use the SPIN selling technique. First, ask Situation questions
to understand the customer's context. Then, Problem questions to uncover issues.
When handling price objections, always focus on value over cost.
Remember to use active listening and mirror the customer's language.
Close with a summary of benefits and clear next steps.
"""

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
    session.output_message = Mock(spec=OutputMessage)
    session.created_at = datetime.now()
    return session

@pytest.fixture
def mock_config():
    return VideoDBProxyConfig(
        api_key="test_key",
        api_base="https://api.videodb.io",
        llm_type="videodb_proxy"
    )

@pytest.fixture
def mock_llm(mock_config):
    llm = Mock(spec=VideoDBProxy)
    llm.api_key = mock_config.api_key
    llm.api_base = mock_config.api_base
    return llm

@pytest.fixture
def agent(mock_session, mock_llm, mock_config):
    with patch('director.llm.get_default_llm', return_value=mock_llm), \
         patch('director.llm.videodb_proxy.VideoDBProxyConfig', return_value=mock_config):
        agent = SalesPromptExtractorAgent(session=mock_session)
        agent.push_status_update = AsyncMock()
        return agent

@pytest.mark.asyncio
async def test_get_transcript(agent):
    # Mock transcription agent response
    mock_response = Mock(status=AgentStatus.SUCCESS)
    mock_response.data = {"transcript": SAMPLE_TRANSCRIPT}
    agent.transcription_agent.run = AsyncMock(return_value=mock_response)
    
    transcript = await agent._get_transcript("test_video_id")
    assert transcript == SAMPLE_TRANSCRIPT

@pytest.mark.asyncio
async def test_analyze_content(agent):
    # Mock summarization and LLM responses
    mock_summary = Mock(status=AgentStatus.SUCCESS)
    mock_summary.data = {"summary": SAMPLE_TRANSCRIPT}
    agent.summarize_agent.run = AsyncMock(return_value=mock_summary)

    mock_llm_response = Mock()
    mock_llm_response.text = json.dumps(SAMPLE_ANALYSIS["structured_data"])
    agent.llm.agenerate_text = AsyncMock(return_value=mock_llm_response)

    analysis = await agent._analyze_content(SAMPLE_TRANSCRIPT, "full")
    assert analysis["structured_data"] == SAMPLE_ANALYSIS["structured_data"]
    assert "raw_analysis" in analysis
    assert "metadata" in analysis

@pytest.mark.asyncio
async def test_generate_prompt(agent):
    prompt = await agent._generate_prompt(SAMPLE_ANALYSIS)
    
    # Verify prompt structure
    assert "system_prompt" in prompt
    assert "first_message" in prompt
    assert "example_conversations" in prompt
    assert "metadata" in prompt
    
    # Check content
    assert "SPIN Selling" in prompt["system_prompt"]
    assert len(prompt["example_conversations"]) <= 5
    assert isinstance(prompt["metadata"]["techniques_used"], int)

@pytest.mark.asyncio
async def test_full_workflow(agent):
    # Mock all dependent functions
    agent._get_transcript = AsyncMock(return_value=SAMPLE_TRANSCRIPT)
    agent._analyze_content = AsyncMock(return_value=SAMPLE_ANALYSIS)
    agent._generate_prompt = AsyncMock(return_value={
        "system_prompt": "Test prompt",
        "first_message": "Hello",
        "example_conversations": [],
        "metadata": {}
    })

    # Mock status updates
    agent.push_status_update = AsyncMock()

    response = await agent.run("test_video_id")
    assert response.status == AgentStatus.SUCCESS

@pytest.mark.asyncio
async def test_error_handling(agent):
    # Test transcription error
    mock_response = Mock(status=AgentStatus.ERROR)
    mock_response.message = "Transcription failed"
    agent.transcription_agent.run = AsyncMock(return_value=mock_response)
    
    response = await agent.run("test_video_id")
    assert response.status == AgentStatus.ERROR
    assert "Transcription failed" in response.message

@pytest.mark.asyncio
async def test_structure_analysis_json(mock_session, mock_llm, mock_config):
    # Test with mocked configuration
    with patch('director.llm.get_default_llm', return_value=mock_llm), \
         patch('director.llm.videodb_proxy.VideoDBProxyConfig', return_value=mock_config):
        agent = SalesPromptExtractorAgent(mock_session)
        agent.push_status_update = AsyncMock()

        # Mock the analysis response
        mock_analysis = {
            "structured_data": {
                "sales_techniques": [{"name": "Test Technique", "description": "Test description"}]
            }
        }
        agent._analyze_content = AsyncMock(return_value=mock_analysis)
        agent._get_transcript = AsyncMock(return_value=SAMPLE_TRANSCRIPT)

        response = await agent.run("test_video_id", analysis_type="sales_techniques", output_format="structured")
        assert response.status == AgentStatus.SUCCESS

@pytest.mark.asyncio
async def test_structure_analysis_fallback(mock_session, mock_llm, mock_config):
    # Test with mocked configuration
    with patch('director.llm.get_default_llm', return_value=mock_llm), \
         patch('director.llm.videodb_proxy.VideoDBProxyConfig', return_value=mock_config):
        agent = SalesPromptExtractorAgent(mock_session)
        agent.push_status_update = AsyncMock()

        # Mock an invalid analysis response that will fail JSON parsing
        agent._analyze_content = AsyncMock(side_effect=json.JSONDecodeError("Failed to parse", "{", 0))
        agent._get_transcript = AsyncMock(return_value=SAMPLE_TRANSCRIPT)

        response = await agent.run("test_video_id")
        assert response.status == AgentStatus.ERROR
        assert "Failed to extract sales concepts" in response.message 