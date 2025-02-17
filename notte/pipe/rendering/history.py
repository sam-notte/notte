from abc import ABC, abstractmethod
from typing import override

from litellm import AllMessageValues
from loguru import logger

from examples.falco.perception import FalcoPerception
from notte.common.agent.config import AgentConfig
from notte.common.agent.perception import BasePerception
from notte.common.tools.conversation import Conversation
from notte.common.tools.trajectory_history import (
    ExecutionStepStatus,
    TrajectoryHistory,
    TrajectoryStep,
    trim_message,
)
from notte.controller.actions import GotoAction


class BaseHistoryRenderer(ABC):
    """Base class to render history

    Implements some sane defaults to render short history, and render some steps, but no main render_history method"""

    @property
    @abstractmethod
    def max_error_length(self) -> int: ...

    @abstractmethod
    def render_history(self, trajectory: TrajectoryHistory) -> list[AllMessageValues]:
        raise NotImplementedError

    def render_short_history(self, trajectory: TrajectoryHistory) -> str:
        steps = "\n".join([self.render_step(step, step_idx=i) for i, step in enumerate(trajectory.steps)])
        return f"""
[Start of action execution history memory]
{steps or self.start_rules()}
[End of action execution history memory]
    """

    def start_rules(self) -> str:
        return f"""
No action executed so far...
Hint: your first action should always be a `{GotoAction.name()}` action with a url related to the task.
You should reflect what url best fits the task you are trying to solve to start the task, e.g.
- flight search task => https://www.google.com/travel/flights
- go to reddit => https://www.reddit.com
- ...
ONLY if you have ABSOLUTELY no idea what to do, you can use `https://www.google.com` as the default url.
THIS SHOULD BE THE LAST RESORT.
"""

    def render_step_result(
        self,
        result: ExecutionStepStatus,
        include_ids: bool = False,
        include_data: bool = False,
    ) -> str:
        action = result.input
        id_str = f" with id={action.id}" if include_ids else ""
        if not result.success:
            err_msg = trim_message(result.message, self.max_error_length)
            return f"[Failure] action '{action.name()}'{id_str} failed with error: {err_msg}"
        success_msg = f"[Success] action '{action.name()}'{id_str}: '{action.execution_message()}'"
        data = result.get().data
        if include_data and data is not None and data.structured is not None and data.structured.data is not None:
            return f"{success_msg}\n\nExtracted JSON data:\n{data.structured.data.model_dump_json()}"
        return success_msg

    def render_step(
        self,
        step: TrajectoryStep,
        step_idx: int = 0,
        include_ids: bool = False,
        include_data: bool = True,
    ) -> str:
        action_msg = "\n".join(["  - " + result.input.dump_str() for result in step.results])
        status_msg = "\n".join(
            ["  - " + self.render_step_result(result, include_ids, include_data) for result in step.results]
        )
        return f"""
# Execution step {step_idx}
* state:
    - page_summary: {step.agent_response.state.page_summary}
    - previous_goal_status: {step.agent_response.state.previous_goal_status}
    - previous_goal_eval: {step.agent_response.state.previous_goal_eval}
    - memory: {step.agent_response.state.memory}
    - next_goal: {step.agent_response.state.next_goal}
* selected actions:
{action_msg}
* execution results:
{status_msg}"""


class CompressedHistRenderer(BaseHistoryRenderer):
    def __init__(self, config: AgentConfig, perception: BasePerception):
        self.config: AgentConfig = config
        self.perception: BasePerception = perception
        self.max_error_length: int = config.max_error_length

    @override
    def render_history(self, trajectory: TrajectoryHistory) -> list[AllMessageValues]:
        conv = Conversation()
        traj_msg = self.render_short_history(trajectory)
        logger.info(f"🔍 Trajectory history:\n{traj_msg}")

        conv.add_user_message(content=traj_msg)

        return conv.messages()


class FullHistRenderer(BaseHistoryRenderer):

    def __init__(self, config: AgentConfig, perception: BasePerception):
        self.config: AgentConfig = config
        self.perception: BasePerception = perception
        self.max_error_length: int = config.max_error_length

    @override
    def render_history(self, trajectory: TrajectoryHistory) -> list[AllMessageValues]:
        conv = Conversation()
        traj_msg = self.render_short_history(trajectory)
        logger.info(f"🔍 Trajectory history:\n{traj_msg}")

        if len(trajectory.steps) == 0:
            conv.add_user_message(content=self.start_rules())

        for step in trajectory.steps:
            conv.add_assistant_message(step.agent_response.model_dump_json(exclude_none=True))

            for result, perceived in step.results:

                short_step_msg = self.render_step_result(result, include_ids=True)
                conv.add_user_message(content=short_step_msg)
                if not result.success:
                    continue

                # add observation data to the conversation
                obs = result.get()
                conv.add_user_message(
                    content=perceived.full,
                    image=obs.screenshot if self.config.include_screenshot else None,
                )

        return conv.messages()


class DataHistoryRenderer(BaseHistoryRenderer):

    def __init__(self, config: AgentConfig, perception: FalcoPerception, raw: bool | None = None):
        self.config: AgentConfig = config
        self.perception: FalcoPerception = perception
        self.max_error_length: int = config.max_error_length
        self.raw: bool | None = raw

    @override
    def render_history(self, trajectory: TrajectoryHistory) -> list[AllMessageValues]:
        conv = Conversation()
        traj_msg = self.render_short_history(trajectory)
        logger.info(f"🔍 Trajectory history:\n{traj_msg}")
        # add trajectory to the conversation
        if len(trajectory.steps) == 0:
            conv.add_user_message(content=self.start_rules())

        for step in trajectory.steps:
            # TODO: choose if we want this to be an assistant message or a tool message
            # self.conv.add_tool_message(step.agent_response, tool_id="step")
            conv.add_assistant_message(step.agent_response.model_dump_json(exclude_none=True))
            for result, perception_result in step.results:
                short_step_msg = self.render_step_result(result, include_ids=True)
                conv.add_user_message(content=short_step_msg)

                if not result.success:
                    continue
                # add observation data to the conversation
                obs = result.get()
                if obs.has_data:
                    conv.add_user_message(content=perception_result.data)

        return conv.messages()
