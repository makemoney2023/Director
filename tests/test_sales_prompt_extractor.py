import pytest
from director.agents.sales_prompt_extractor import SalesPromptExtractorAgent

SAMPLE_TRANSCRIPT = """
Here's a key sales technique I use: Always start by building rapport. Ask about their day, their business, show genuine interest.

When handling objections about price, I focus on value. I explain how our product saves them time and money in the long run.

For communication, I emphasize active listening. Let them speak 80% of the time, and really understand their needs.

My favorite closing technique is the assumptive close. Instead of asking if they want to buy, I ask when they'd like to start.

Remember to follow up within 24 hours of any meeting. Keep the momentum going.
"""

SAMPLE_ANALYSIS = {
    "sales_techniques": [
        "Build rapport before pitching",
        "Focus on value over price",
        "Use assumptive closing"
    ],
    "communication_strategies": [
        "Practice active listening",
        "Let customer speak 80% of time",
        "Show genuine interest"
    ],
    "objection_handling": [
        "Address price objections with ROI focus",
        "Emphasize long-term benefits"
    ],
    "closing_techniques": [
        "Use assumptive close",
        "Follow up within 24 hours",
        "Maintain momentum"
    ]
}

@pytest.fixture
def agent():
    return SalesPromptExtractorAgent()

@pytest.mark.asyncio
async def test_structure_analysis(agent):
    """Test that the agent can structure raw analysis text correctly"""
    structured = await agent._structure_analysis(SAMPLE_TRANSCRIPT)
    assert "sales_techniques" in structured
    assert "communication_strategies" in structured
    assert "objection_handling" in structured
    assert "closing_techniques" in structured
    
    # Check specific content
    assert any("rapport" in technique.lower() for technique in structured["sales_techniques"])
    assert any("active listening" in strategy.lower() for strategy in structured["communication_strategies"])
    assert any("price" in objection.lower() for objection in structured["objection_handling"])
    assert any("assumptive" in technique.lower() for technique in structured["closing_techniques"])

@pytest.mark.asyncio
async def test_generate_prompt(agent):
    """Test that the agent can generate a valid prompt from structured analysis"""
    prompt = await agent._generate_prompt(SAMPLE_ANALYSIS)
    
    assert isinstance(prompt, dict)
    assert "system_prompt" in prompt
    assert "example_conversations" in prompt
    assert "first_message" in prompt
    
    # Check content
    assert "sales techniques" in prompt["system_prompt"].lower()
    assert len(prompt["example_conversations"]) > 0
    assert isinstance(prompt["first_message"], str) 