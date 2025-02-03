from pydantic import BaseModel, Field

from notte.browser.observation import Observation
from notte.common.safe_executor import ExecutionStatus
from notte.controller.actions import BaseAction, GotoAction

TrajectoryStep = ExecutionStatus[BaseAction, Observation]


def trim_message(message: str, max_length: int | None = None) -> str:
    if max_length is None or len(message) <= max_length:
        return message
    return f"...{message[-max_length:]}"


class TrajectoryHistory(BaseModel):
    steps: list[TrajectoryStep] = Field(default_factory=list)
    max_error_length: int | None = None

    def perceive(self) -> str:
        steps = "\n".join([f"* {i}. {self.perceive_step(step)}" for i, step in enumerate(self.steps)])
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

    def perceive_step(
        self,
        step: TrajectoryStep,
        include_idx: bool = False,
    ) -> str:
        id_str = step.input.id if include_idx else ""
        if not step.success:
            err_msg = trim_message(step.message, self.max_error_length)
            return f"[Execution Failure] action {id_str}: '{step.input.description}' failed with error: {err_msg}"
        return f"[Execution Success] action {id_str}: '{step.input.execution_message()}'"

    def add_step(self, step: TrajectoryStep) -> None:
        self.steps.append(step)

    def last_obs(self) -> Observation | None:
        for step in self.steps[::-1]:
            if step.success and step.output is not None:
                return step.output
        return None
