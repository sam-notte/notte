import json

import pytest

from notte.env import NotteEnv, NotteEnvConfig


@pytest.mark.asyncio
async def test_user_agent():
    """Test validation of special action parameters"""

    USER_AGENT = "test-user-agent"
    async with NotteEnv(NotteEnvConfig().set_user_agent(USER_AGENT).headless()) as env:
        _ = await env.goto("https://ifconfig.co/json")
        json_resp = json.loads(env.snapshot.dom_node.inner_text())
        assert json_resp["user_agent"]["raw_value"] == USER_AGENT
