import asyncio

from dotenv import load_dotenv
from loguru import logger
from typing_extensions import override

from examples.pipistrello.parser import PipistrelloParser
from examples.pipistrello.perception import PipistrelloPerception
from examples.pipistrello.prompt import PipistrelloPrompt
from notte.browser.observation import Observation
from notte.common.agent.base import BaseAgent
from notte.common.agent.config import AgentConfig
from notte.common.agent.types import AgentOutput
from notte.common.tools.conversation import Conversation
from notte.common.tracer import LlmUsageDictTracer
from notte.controller.actions import CompletionAction
from notte.credentials.models import VaultInterface
from notte.env import NotteEnv, NotteEnvConfig
from notte.llms.engine import LLMEngine

_ = load_dotenv()


class PipistrelloAgentConfig(AgentConfig):
    env: NotteEnvConfig = NotteEnvConfig.use_llm()


class PipistrelloAgent(BaseAgent):
    """
    A specialized agent for password management tasks.
    This agent handles credential storage and verification while maintaining security best practices.
    """

    def __init__(self, config: AgentConfig, vault: VaultInterface | None = None) -> None:
        self.tracer: LlmUsageDictTracer = LlmUsageDictTracer()
        self.config: AgentConfig = config
        self.llm: LLMEngine = LLMEngine(model=config.reasoning_model)
        self.env: NotteEnv = NotteEnv(config=config.env, vault=vault)
        self.parser: PipistrelloParser = PipistrelloParser()
        self.prompt: PipistrelloPrompt = PipistrelloPrompt(self.parser)
        self.perception: PipistrelloPerception = PipistrelloPerception()
        self.conv: Conversation = Conversation()
        self.vault: VaultInterface | None = vault

    async def reset(self):
        await self.env.reset()
        self.conv.reset()

    def output(self, answer: str, success: bool) -> AgentOutput:
        return AgentOutput(
            answer=answer,
            success=success,
            env_trajectory=self.env.trajectory,
            agent_trajectory=[],
            llm_usage=self.tracer.usage,
        )

    async def is_login_page(self) -> bool:
        """
        Use LLM to determine if the current page is a login page.
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant that determines if a webpage is a login page."
                    "Respond with only 'true' or 'false'."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Based on the following webpage content, is this a login page? "
                    "Only respond with 'true' or 'false'.\n\n"
                    f"{self.env.context.snapshot.text}"
                ),
            },
        ]

        response = (
            self.llm.completion(
                messages=messages,
                model=self.config.reasoning_model,
            )
            .choices[0]
            .message.content.lower()
            .strip()
        )

        return response == "true"

    async def step(self) -> CompletionAction | None:
        logger.info(f"🤖 LLM prompt:\n{self.conv.messages()}")
        response: str = self.llm.single_completion(self.conv.messages())
        self.conv.add_assistant_message(content=response)
        logger.info(f"🤖 LLM response:\n{response}")

        parsed_response = self.parser.parse(response)
        if parsed_response is None or parsed_response.action is None:
            self.conv.add_user_message(content=self.prompt.env_rules())
            return None

        if parsed_response.completion is not None:
            return parsed_response.completion

        obs: Observation = await self.env.act(parsed_response.action)
        text_obs = self.perception.perceive(obs)
        self.conv.add_user_message(
            content=f"""
{text_obs}
{self.prompt.select_action_rules()}
{self.prompt.completion_rules()}
""",
            image=obs.screenshot if self.config.include_screenshot else None,
        )
        logger.info(f"🌌 Action successfully executed:\n{text_obs}")
        return None

    @override
    async def run(self, task: str, url: str | None = None) -> AgentOutput:
        logger.info(f"🚀 starting agent with task: {task} and url: {url}")
        self.conv.add_system_message(self.prompt.system(task, url))
        self.conv.add_user_message(self.prompt.env_rules())

        async with self.env:
            for i in range(self.config.env.max_steps):
                logger.info(f"> step {i}: looping in")
                output = await self.step()
                if output is not None:
                    if output.success and self.vault is not None:
                        # Store credentials if task was successful
                        current_url = self.env.context.snapshot.metadata.url
                        self.vault.add_credentials(current_url, "username", "password")
                    status = "😎 task completed successfully" if output.success else "👿 task failed"
                    logger.info(f"{status} with answer: {output.answer}")
                    return self.output(output.answer, output.success)

            error_msg = f"Failed to solve task in {self.config.env.max_steps} steps"
            logger.info(f"🚨 {error_msg}")
            return self.output(error_msg, False)


if __name__ == "__main__":
    parser = AgentConfig.create_parser()
    _ = parser.add_argument("--task", type=str, required=True)
    args = parser.parse_args()
    agent = PipistrelloAgent(config=AgentConfig.from_args(args))
    out = asyncio.run(agent.run(args.task))
    print(out)
