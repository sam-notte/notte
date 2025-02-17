from enum import StrEnum

from litellm import AllMessageValues, override
from loguru import logger

import notte
from notte.browser.observation import Observation
from notte.browser.pool import BrowserPool
from notte.common.agent.base import BaseAgent
from notte.common.agent.config import AgentConfig
from notte.common.agent.perception import PerceptionResult
from notte.common.agent.types import AgentOutput
from notte.common.tools.conversation import Conversation
from notte.common.tools.safe_executor import ExecutionStatus, SafeActionExecutor
from notte.common.tools.trajectory_history import TrajectoryHistory
from notte.common.tools.validator import CompletionValidator
from notte.controller.actions import BaseAction, CompletionAction
from notte.env import NotteEnv, NotteEnvConfig
from notte.llms.engine import LLMEngine
from notte.pipe.rendering.history import (
    BaseHistoryRenderer,
    CompressedHistRenderer,
    DataHistoryRenderer,
    FullHistRenderer,
)

from .perception import FalcoPerception
from .prompt import FalcoPrompt
from .types import StepAgentOutput

# TODO: list
# handle tooling calling methods for different providers (if not supported by litellm)
# Handle control flags
# Done callback
# Setup telemetry
# Setup memory
# Handle custom functions, e.g. `Upload file to element`ç
# Remove base 64 images from current state
# TODO: add fault tolerance LLM parsing
# TODO: only display modal actions when modal is open (same as before)
# TODO: handle prevent default click JS events
# TODO: add some tree structure for menu elements (like we had in notte before. Ex. Menu in Arxiv)


class HistoryType(StrEnum):
    FULL_CONVERSATION = "full_conversation"
    SHORT_OBSERVATIONS = "short_observations"
    SHORT_OBSERVATIONS_WITH_RAW_DATA = "short_observations_with_raw_data"
    SHORT_OBSERVATIONS_WITH_SHORT_DATA = "short_observations_with_short_data"
    COMPRESSED = "compressed"


class FalcoAgentConfig(AgentConfig):
    env: NotteEnvConfig = NotteEnvConfig.disable_llm()
    max_actions_per_step: int = 1
    history_type: HistoryType = HistoryType.SHORT_OBSERVATIONS_WITH_SHORT_DATA


class FalcoAgent(BaseAgent):

    def __init__(
        self,
        config: FalcoAgentConfig,
        pool: BrowserPool | None = None,
    ):
        self.config: FalcoAgentConfig = config

        if config.include_screenshot and not config.env.browser.screenshot:
            raise ValueError("Cannot `include_screenshot=True` if `screenshot` is not enabled in the browser config")
        self.llm: LLMEngine = LLMEngine(model=config.reasoning_model)
        # Users should implement their own parser to customize how observations
        # and actions are formatted for their specific LLM and use case
        self.env: NotteEnv = NotteEnv(
            config=config.env,
            pool=pool,
        )
        self.perception: FalcoPerception = FalcoPerception()
        self.validator: CompletionValidator = CompletionValidator(llm=self.llm, perception=self.perception)
        self.prompt: FalcoPrompt = FalcoPrompt(max_actions_per_step=config.max_actions_per_step)
        self.conv: Conversation = Conversation(max_tokens=config.max_history_tokens, convert_tools_to_assistant=True)
        self.history_type: HistoryType = config.history_type
        self.history_renderer: BaseHistoryRenderer

        match self.history_type:
            case HistoryType.COMPRESSED:
                self.history_renderer = CompressedHistRenderer(self.config)
            case HistoryType.FULL_CONVERSATION:
                self.history_renderer = FullHistRenderer(self.config)
            case HistoryType.SHORT_OBSERVATIONS:
                self.history_renderer = DataHistoryRenderer(self.config)
            case HistoryType.SHORT_OBSERVATIONS_WITH_RAW_DATA:
                self.history_renderer = DataHistoryRenderer(self.config)
            case HistoryType.SHORT_OBSERVATIONS_WITH_SHORT_DATA:
                self.history_renderer = DataHistoryRenderer(self.config)

        self.trajectory: TrajectoryHistory = TrajectoryHistory(max_error_length=config.max_error_length)
        self.step_executor: SafeActionExecutor[BaseAction, Observation] = SafeActionExecutor(
            func=self.env.act,
            raise_on_failure=config.raise_on_failure,
            max_consecutive_failures=config.max_consecutive_failures,
        )

    async def reset(self) -> None:
        self.conv.reset()
        self.trajectory.reset()
        self.step_executor.reset()
        await self.env.reset()

    def output(self, answer: str, success: bool) -> AgentOutput:
        return AgentOutput(
            answer=answer,
            success=success,
            trajectory=self.env.trajectory,
            messages=self.conv.messages(),
        )

    def get_messages(self, task: str) -> list[AllMessageValues]:
        self.conv.reset()
        system_msg, task_msg = self.prompt.system(), self.prompt.task(task)
        self.conv.add_system_message(content=system_msg)
        self.conv.add_user_message(content=task_msg)

        # get history messages
        self.conv.add_messages(self.history_renderer.render_history(self.trajectory))

        # add last perception
        last_valid_obs = self.trajectory.last_obs()
        if last_valid_obs is None or self.history_type is HistoryType.FULL_CONVERSATION:
            return self.conv.messages()

        last_obs, last_perception = last_valid_obs

        self.conv.add_user_message(
            content=last_perception.full,
            image=last_obs.screenshot if self.config.include_screenshot else None,
        )

        logger.info(f"🔍 Latest step perception:\n{last_perception.full}")
        return self.conv.messages()

    async def step(self, task: str) -> CompletionAction | None:
        """Execute a single step of the agent"""
        messages = self.get_messages(task)
        # logger.info(f"🔍 LLM messages:\n{messages}")
        response: StepAgentOutput = self.llm.structured_completion(messages, response_format=StepAgentOutput)
        logger.info(f"🔍 LLM response:\n{response}")
        self.trajectory.add_output(response)
        # check for completion
        if response.output is not None:
            return response.output
        # Execute the actions
        for action in response.get_actions(self.config.max_actions_per_step):

            # execute, perceive, add to history
            result = await self.step_executor.execute(action)
            perceived_env = self.perception.perceive(result.get())
            self.trajectory.add_step(result, perceived_env)

            step_msg = self.history_renderer.render_step_result(result, include_ids=True)
            if not result.success:
                logger.error(f"🚨 {step_msg}")
                # stop the loop
                break
            # Successfully executed the action
            logger.info(f"🚀 {step_msg}")
        return None

    @override
    async def run(self, task: str, url: str | None = None) -> AgentOutput:
        """Execute the task with maximum number of steps"""
        # change this to DEV if you want more explicit error messages
        # when you are developing your own agent
        notte.set_error_mode("agent")
        if url is not None:
            task = f"Start on '{url}' and {task}"

        # Loop through the steps
        async with self.env:
            for step in range(self.env.config.max_steps):
                logger.info(f"> step {step}: looping in")
                output: CompletionAction | None = await self.step(task)

                if output is None:
                    continue
                # validate the output
                if not output.success:
                    logger.error(f"🚨 Agent terminated early with failure: {output.answer}")
                    return self.output(output.answer, False)
                # Sucessful execution and LLM output is not None
                # Need to validate the output
                logger.info(f"🔥 Validating agent output:\n{output.model_dump_json()}")
                val = self.validator.validate(task, output, self.env.trajectory[-1])
                if val.is_valid:
                    # Successfully validated the output
                    logger.info("✅ Task completed successfully")
                    return self.output(output.answer, output.success)
                else:
                    # TODO handle that differently
                    failed_val_msg = f"Final validation failed: {val.reason}. Continuing..."
                    logger.error(failed_val_msg)
                    # add the validation result to the trajectory and continue
                    self.trajectory.add_step(
                        ExecutionStatus(
                            input=output,
                            output=None,
                            success=False,
                            message=failed_val_msg,
                        ),
                        PerceptionResult.empty(),
                    )

        error_msg = f"Failed to solve task in {self.env.config.max_steps} steps"
        logger.info(f"🚨 {error_msg}")
        notte.set_error_mode("developer")
        return self.output(error_msg, False)
