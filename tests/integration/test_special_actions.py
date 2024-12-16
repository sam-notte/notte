import pytest

from notte.actions.base import SpecialAction
from notte.env import NotteEnv
from tests.mock.mock_service import MockLLMService


@pytest.fixture
def llm_service():
    return MockLLMService(mock_response="<data-extraction> # Hello World </data-extraction>")


def test_special_actions_list():
    """Test that all special actions are properly defined"""
    special_actions = SpecialAction.list()

    # Test we have all 7 special actions
    assert len(special_actions) == 7

    # Test each special action ID exists
    action_ids = [action.id for action in special_actions]
    expected_ids = ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]
    assert sorted(action_ids) == sorted(expected_ids)

    # Test special action detection
    for action_id in expected_ids:
        assert SpecialAction.is_special(action_id)

    # Test non-special action detection
    assert not SpecialAction.is_special("B1")
    assert not SpecialAction.is_special("I1")
    assert not SpecialAction.is_special("L1")


@pytest.mark.asyncio
async def test_special_actions_execution(llm_service: MockLLMService):
    """Test the execution of various special actions"""
    async with NotteEnv(headless=True, llmserve=llm_service, screenshot=False) as env:
        # Test S1: Go to URL
        obs = await env.execute("S1", {"url": "https://example.com/"})
        assert obs.clean_url == "example.com"

        # Test S2: Scrape data
        obs = await env.execute("S2")
        assert obs is not None
        assert obs.data == "# Hello World"

        # Test S3: Take screenshot
        obs = await env.execute("S3")
        assert obs.screenshot is not None

        # Test S4: Go back
        obs = await env.execute("S1", {"url": "https://google.com/"})
        assert obs.clean_url == "google.com"
        obs = await env.execute("S4")
        assert obs.clean_url == "example.com"

        # Test S5: Go forward
        obs = await env.execute("S5")
        assert obs.clean_url == "google.com"

        # Test S6: Wait
        _ = await env.execute("S6", {"value": "1"})

        # Test S7: Terminate session (cannot execute any actions after this)
        _ = await env.execute("S7")
        with pytest.raises(RuntimeError, match="Browser not initialized"):
            _ = await env.goto("https://example.com/")


@pytest.mark.asyncio
async def test_special_action_validation(llm_service: MockLLMService):
    """Test validation of special action parameters"""
    async with NotteEnv(headless=True, llmserve=llm_service) as env:
        _ = await env.goto("https://example.com/")
        # Test S1 requires URL parameter
        with pytest.raises(ValueError, match="Special action S1 requires a parameter"):
            _ = await env.execute("S1")

        # Test S6 requires wait time parameter
        with pytest.raises(ValueError, match="Special action S6 requires a parameter"):
            _ = await env.execute("S6")

        # Test invalid special action
        with pytest.raises(ValueError, match="action X1 not found in context"):
            _ = await env.execute("X1")
