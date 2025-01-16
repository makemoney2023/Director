import pytest
from unittest.mock import Mock, patch
import json
from director.agents.voice_prompt_generation_agent import VoicePromptGenerationAgent, VoicePromptContent
from director.core.session import MsgStatus, OutputMessage, TextContent
from director.llm.base import LLMResponseStatus

@pytest.fixture
def mock_session():
    """Create a mock session with required attributes"""
    mock = Mock()
    mock.output_message = Mock(spec=OutputMessage)
    mock.output_message.add_content = Mock()
    mock.output_message.push_update = Mock()
    mock.output_message.actions = []
    return mock

@pytest.fixture
def structured_data():
    return {
        "patterns": ["value_proposition", "objection_handling"],
        "communication": {
            "style": "consultative",
            "key_phrases": ["I understand", "Let me clarify", "Would you explain"]
        },
        "effectiveness": ["clear_value", "active_listening"],
        "recommendations": ["maintain_empathy", "use_active_listening", "provide_examples"]
    }

@pytest.fixture
def yaml_config():
    return {
        "voice_settings": {
            "tone": {
                "base_pitch": "medium",
                "energy": "balanced"
            },
            "pacing": {
                "rate": "moderate",
                "pauses": "natural"
            }
        },
        "adaptation_rules": {
            "emotion_mapping": {
                "positive": {"energy": "high"},
                "neutral": {"energy": "balanced"},
                "negative": {"energy": "measured"}
            }
        }
    }

@pytest.fixture
def context_data():
    return {
        "current_state": {
            "emotion": "positive",
            "engagement": "high"
        },
        "history": [
            {
                "from_state": "introduction",
                "to_state": "value_prop",
                "type": "response"
            }
        ],
        "user_preferences": {
            "communication_style": "direct",
            "pace": "moderate"
        }
    }

@pytest.fixture
def mock_anthropic_response():
    return {
        "prompt": {
            "content": "Could you tell me more about your needs?",
            "tone_guidance": {
                "pitch": "medium",
                "rate": "moderate",
                "energy": "balanced"
            },
            "adaptation_rules": {
                "context_triggers": ["user hesitation", "information gaps"],
                "response_patterns": ["clarifying questions", "active listening"],
                "transitions": ["smooth topic shift", "natural follow-up"]
            }
        },
        "metadata": {
            "style": "consultative",
            "context_awareness": ["user preferences", "conversation history", "emotional state"],
            "emotional_resonance": ["empathy", "understanding", "support"]
        }
    }

class TestVoicePromptGenerationAgent:
    
    @patch('director.tools.anthropic_tool.AnthropicTool')
    def test_initialization(self, mock_anthropic_class, mock_session):
        """Test agent initialization"""
        mock_llm = Mock()
        mock_llm.api_key = "test_key"
        mock_anthropic_class.return_value = mock_llm
        
        agent = VoicePromptGenerationAgent(mock_session, prompt_llm=mock_llm)
        assert agent.agent_name == "voice_prompt_generation"
        assert agent.description == "Generates dynamic voice prompts with context adaptation"
        assert agent.parameters is not None
        assert hasattr(agent, 'prompt_llm')

    @patch('director.tools.anthropic_tool.AnthropicTool')
    def test_extract_analysis_insights(self, mock_anthropic_class, mock_session, structured_data):
        """Test analysis insights extraction"""
        mock_llm = Mock()
        mock_llm.api_key = "test_key"
        mock_anthropic_class.return_value = mock_llm
        
        agent = VoicePromptGenerationAgent(mock_session, prompt_llm=mock_llm)
        insights = agent._extract_analysis_insights(structured_data)
        
        assert "key_patterns" in insights
        assert "communication_style" in insights
        assert "effectiveness_indicators" in insights
        assert "recommended_approaches" in insights
        assert insights["key_patterns"] == structured_data["patterns"]

    @patch('director.tools.anthropic_tool.AnthropicTool')
    def test_get_style_config(self, mock_anthropic_class, mock_session, yaml_config):
        """Test style configuration generation"""
        mock_llm = Mock()
        mock_llm.api_key = "test_key"
        mock_anthropic_class.return_value = mock_llm
        
        agent = VoicePromptGenerationAgent(mock_session, prompt_llm=mock_llm)
        
        # Test professional style
        prof_config = agent._get_style_config("professional", yaml_config)
        assert prof_config["tone"]["base"] == "measured"
        assert prof_config["pacing"]["rate"] == "moderate"
        
        # Test dynamic style
        dynamic_config = agent._get_style_config("dynamic", yaml_config)
        assert dynamic_config["tone"]["base"] == "adaptive"
        assert dynamic_config["pacing"]["emphasis"] == "dynamic"

    @patch('director.tools.anthropic_tool.AnthropicTool')
    def test_analyze_context(self, mock_anthropic_class, mock_session, context_data):
        """Test context analysis"""
        mock_llm = Mock()
        mock_llm.api_key = "test_key"
        mock_anthropic_class.return_value = mock_llm
        
        agent = VoicePromptGenerationAgent(mock_session, prompt_llm=mock_llm)
        analysis = agent._analyze_context(context_data)
        
        assert "state" in analysis
        assert "patterns" in analysis
        assert "preferences" in analysis
        assert "adaptations" in analysis
        assert analysis["state"] == context_data["current_state"]

    @patch('director.tools.anthropic_tool.AnthropicTool')
    def test_emotion_mapping(self, mock_anthropic_class, mock_session):
        """Test emotion to tone mapping"""
        mock_llm = Mock()
        mock_llm.api_key = "test_key"
        mock_anthropic_class.return_value = mock_llm
        
        agent = VoicePromptGenerationAgent(mock_session, prompt_llm=mock_llm)
        
        positive_tone = agent._map_emotion_to_tone("positive")
        assert positive_tone["energy"] == "high"
        assert positive_tone["pitch"] == "medium-high"
        
        negative_tone = agent._map_emotion_to_tone("negative")
        assert negative_tone["energy"] == "low"
        assert negative_tone["pitch"] == "medium-low"

    @patch('director.tools.anthropic_tool.AnthropicTool')
    def test_run_success(self, mock_anthropic_class, mock_session, structured_data, yaml_config, context_data, mock_anthropic_response):
        """Test successful prompt generation"""
        # Setup mock Anthropic response
        mock_llm = Mock()
        mock_llm.api_key = "test_key"
        mock_llm.chat_completions.return_value = Mock(
            status=LLMResponseStatus.SUCCESS,
            content=json.dumps(mock_anthropic_response)
        )
        mock_anthropic_class.return_value = mock_llm

        # Create agent and run
        agent = VoicePromptGenerationAgent(mock_session, prompt_llm=mock_llm)
        response = agent.run(
            structured_data=structured_data,
            yaml_config=yaml_config,
            context=context_data
        )
        
        assert response.status == "success"
        assert "prompt_data" in response.data
        assert "context_metadata" in response.data
        assert "adaptation_rules" in response.data

    @patch('director.tools.anthropic_tool.AnthropicTool')
    def test_run_error_handling(self, mock_anthropic_class, mock_session, structured_data, yaml_config, context_data):
        """Test error handling in prompt generation"""
        # Setup mock Anthropic error response
        mock_llm = Mock()
        mock_llm.api_key = "test_key"
        mock_llm.chat_completions.return_value = Mock(
            status=LLMResponseStatus.ERROR,
            message="API Error"
        )
        mock_anthropic_class.return_value = mock_llm

        # Create agent and run
        agent = VoicePromptGenerationAgent(mock_session, prompt_llm=mock_llm)
        response = agent.run(
            structured_data=structured_data,
            yaml_config=yaml_config,
            context=context_data
        )
        
        assert response.status == "error"
        assert "error" in response.data

    @patch('director.tools.anthropic_tool.AnthropicTool')
    def test_input_validation(self, mock_anthropic_class, mock_session):
        """Test input validation"""
        mock_llm = Mock()
        mock_llm.api_key = "test_key"
        mock_anthropic_class.return_value = mock_llm
        
        agent = VoicePromptGenerationAgent(mock_session, prompt_llm=mock_llm)
        
        # Test missing required inputs
        response = agent.run(structured_data=None, yaml_config=None)
        assert response.status == "error"
        assert "Both structured data and YAML config are required" in response.data["error"]

    def test_voice_prompt_content(self):
        """Test VoicePromptContent class"""
        content = VoicePromptContent(
            prompt_data={"test": "data"},
            context_metadata={"version": "1.0"},
            adaptation_rules={"rule": "test"}
        )
        
        dict_data = content.model_dump()
        assert dict_data["prompt_data"] == {"test": "data"}
        assert dict_data["context_metadata"] == {"version": "1.0"}
        assert dict_data["adaptation_rules"] == {"rule": "test"}

if __name__ == "__main__":
    pytest.main([__file__]) 