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
from notte.common.credentials.models import VaultInterface
from notte.common.tools.conversation import Conversation
from notte.common.tracer import LlmUsageDictTracer
from notte.controller.actions import CompletionAction
from notte.env import NotteEnv, NotteEnvConfig
from notte.llms.engine import LLMEngine

_ = load_dotenv()


class PipistrelloAgentConfig(AgentConfig):
    env: NotteEnvConfig = NotteEnvConfig().use_llm()


class PipistrelloAgent(BaseAgent):
    """
    A specialized agent for password management tasks.
    This agent handles credential storage and verification while maintaining security best practices.
    """

    def __init__(self, config: AgentConfig, vault: VaultInterface | None = None) -> None:
        self.tracer: LlmUsageDictTracer = LlmUsageDictTracer()
        self.config: AgentConfig = config
        self.llm: LLMEngine = LLMEngine(model=config.reasoning_model)
        self.env: NotteEnv = NotteEnv(config=config.env)
        self.parser: PipistrelloParser = PipistrelloParser()
        self.prompt: PipistrelloPrompt = PipistrelloPrompt(self.parser, has_vault=vault is not None)
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

        print("parsed_response.action")
        print(parsed_response.action)

        if self.vault is not None and hasattr(parsed_response.action, "params_values"):
            current_url = self.env.context.snapshot.metadata.url
            print("params_values")
            print(parsed_response.action.params_values)
            parsed_response.action.params_values = self.vault.replace_placeholder_credentials(
                current_url, parsed_response.action.params_values
            )
            print("new params_values")
            print(parsed_response.action.params_values)

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
                    status = "😎 task completed sucessfully" if output.success else "👿 task failed"
                    logger.info(f"{status} with answer: {output.answer}")
                    return self.output(output.answer, output.success)
            # If the task is not done, raise an error
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
