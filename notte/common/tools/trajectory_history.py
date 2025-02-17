from pydantic import BaseModel, Field

from examples.falco.types import StepAgentOutput
from notte.browser.observation import Observation
from notte.common.agent.perception import PerceptionResult
from notte.common.tools.safe_executor import ExecutionStatus
from notte.controller.actions import BaseAction, GotoAction

ExecutionStepStatus = ExecutionStatus[BaseAction, Observation]


class TrajectoryStep(BaseModel):
    agent_response: StepAgentOutput
    results: list[tuple[ExecutionStepStatus, PerceptionResult]]


def trim_message(message: str, max_length: int | None = None) -> str:
    if max_length is None or len(message) <= max_length:
        return message
    return f"...{message[-max_length:]}"


class TrajectoryHistory(BaseModel):
    steps: list[TrajectoryStep] = Field(default_factory=list)
    max_error_length: int | None = None

    def reset(self) -> None:
        self.steps = []

    def add_output(self, output: StepAgentOutput) -> None:
        self.steps.append(TrajectoryStep(agent_response=output, results=[]))

    def add_step(self, step: ExecutionStepStatus, perceived: PerceptionResult) -> None:
        if len(self.steps) == 0:
            raise ValueError("Cannot add step to empty trajectory. Use `add_output` first.")
        else:
            self.steps[-1].results.append((step, perceived))

    def last_obs(self) -> Observation | None:
        for step in self.steps[::-1]:
            for step_result, _ in step.results[::-1]:
                if step_result.success and step_result.output is not None:
                    return step_result.output
        return None
