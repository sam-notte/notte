from litellm import override
from loguru import logger

from examples.simple.perception import SimplePerception
from examples.simple.prompt import SimplePrompt
from examples.simple.types import StepAgentOutput
from notte.common.agent import AgentOutput, BaseAgent
from notte.common.conversation import Conversation
from notte.common.safe_executor import SafeActionExecutor
from notte.common.trajectory_history import TrajectoryHistory
from notte.common.validator import StepValidator
from notte.env import NotteEnv, NotteEnvConfig
from notte.llms.engine import LLMEngine
from notte.pipe.action.pipe import ActionSpaceType, MainActionSpaceConfig
from notte.pipe.preprocessing.pipe import PreprocessingType
from notte.pipe.scraping.config import ScrapingConfig, ScrapingType

config = NotteEnvConfig(
    max_steps=100,
    auto_scrape=False,
    processing_type=PreprocessingType.DOM,
    scraping=ScrapingConfig(type=ScrapingType.SIMPLE),
    action=MainActionSpaceConfig(type=ActionSpaceType.SIMPLE),
)
max_actions_per_step = 5

# TODO: list
# handle tooling calling methods for different providers (if not supported by litellm)
# Handle control flags
# Done callback
# Setup telemetry
# Setup memory
# Handle custom functions, e.g. `Upload file to element`


# TODO: fix this piece of code
# ```
# from notte.controller.space import ActionSpace
# space = ActionSpace()
# print(space.actions())
# ```


class SimpleAgent(BaseAgent):

    def __init__(
        self,
        model: str,
        headless: bool,
        max_history_tokens: int = 64000,
        max_error_length: int = 500,
        raise_on_failure: bool = True,
        short_history: bool = True,
    ):
        self.model: str = model
        self.llm: LLMEngine = LLMEngine(model=model)
        # Users should implement their own parser to customize how observations
        # and actions are formatted for their specific LLM and use case
        self.env: NotteEnv = NotteEnv(
            headless=headless,
            config=config,
        )
        self.validator: StepValidator = StepValidator(llm=self.llm)
        self.prompt: SimplePrompt = SimplePrompt(max_actions_per_step)
        self.conv: Conversation = Conversation(
            max_tokens=max_history_tokens,
            convert_tools_to_assistant=True,
        )
        self.perception: SimplePerception = SimplePerception()
        self.short_history: bool = short_history
        self.trajectory: TrajectoryHistory = TrajectoryHistory(max_error_length=max_error_length)
        self.raise_on_failure: bool = raise_on_failure

    @override
    async def run(self, task: str, url: str | None = None) -> AgentOutput:
        """Execute the task with maximum number of steps"""
        system_msg, task_msg = self.prompt.system(), self.prompt.task(task)
        self.conv.add_system_message(content=system_msg)
        self.conv.add_user_message(content=task_msg)

        executor = SafeActionExecutor(func=self.env.raw_step, raise_on_failure=self.raise_on_failure)
        max_steps = self.env.config.max_steps
        # Loop through the steps
        async with self.env:
            for step in range(max_steps):
                logger.info(f"> step {step}: looping in")
                if self.short_history:
                    # Clear the conversation and add the system message
                    self.conv.clear()
                    self.conv.add_system_message(content=system_msg)
                    self.conv.add_user_message(content=task_msg)
                    # Add the short trajectory execution history
                    self.conv.add_user_message(content=self.trajectory.perceive())
                    # Add the last observation
                    last_obs = self.trajectory.last_obs()
                    if last_obs is not None:
                        self.conv.add_user_message(content=self.perception.perceive(last_obs))

                # Let the LLM Agent think about the next action
                logger.info(
                    "\n\n".join([f"# Message {i}: {m.role}\n{m.content}" for i, m in enumerate(self.conv.messages())])
                )
                response: StepAgentOutput = self.llm.structured_completion(
                    self.conv.messages(), response_format=StepAgentOutput
                )

                self.conv.add_tool_message(response, tool_id="step")
                # check for completion
                if response.output is not None:
                    # Sucessful execution and LLM output is not None
                    # Need to validate the output
                    logger.info("🔍 Validating final output...")
                    if not self.validator.validate(task, response.output, self.env.trajectory[-1]):
                        continue
                    logger.info("✅ Task completed successfully")
                    return AgentOutput(
                        answer=response.output.answer,
                        success=response.output.success,
                        trajectory=self.env.trajectory,
                        messages=self.conv.messages(),
                    )
                # Execute the actions
                for action in response.get_actions()[:max_actions_per_step]:
                    result = await executor.execute(action)
                    self.trajectory.add_step(result)
                    step_msg = self.trajectory.perceive_step(result, include_idx=True)
                    if not result.success:
                        logger.error(f"🚨 {step_msg}")
                    else:
                        logger.info(f"🚀 {step_msg}")
                        step_msg = self.perception.perceive(result.get())
                    if not self.short_history:
                        self.conv.add_user_message(content=step_msg)
        error_msg = f"Failed to solve task in {max_steps} steps"
        logger.info(f"🚨 {error_msg}")
        return AgentOutput(
            answer=error_msg,
            success=False,
            trajectory=self.env.trajectory,
            messages=self.conv.messages(),
        )
