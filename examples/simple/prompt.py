import datetime as dt
import json
from pathlib import Path

import chevron

from notte.controller.actions import (
    ClickAction,
    CompletionAction,
    FillAction,
    GotoAction,
    ScrapeAction,
)
from notte.controller.space import ActionSpace

system_prompt_file = Path(__file__).parent / "system_prompt.md"


class SimplePrompt:

    def __init__(self, max_actions_per_step: int):
        self.system_prompt: str = system_prompt_file.read_text()
        self.max_actions_per_step: int = max_actions_per_step
        self.space: ActionSpace = ActionSpace(description="")

    def example_form_filling(self) -> str:
        return json.dumps(
            [
                {
                    FillAction.name(): FillAction(id="I1", value="username").model_dump(
                        exclude={"category", "description", "selector", "press_enter"}
                    ),
                },
                {
                    FillAction.name(): FillAction(id="I2", value="password").model_dump(
                        exclude={"category", "description", "selector", "press_enter"}
                    ),
                },
                {
                    ClickAction.name(): ClickAction(id="B1").model_dump(
                        exclude={"category", "description", "selector", "press_enter"}
                    ),
                },
            ],
            indent=2,
        )

    def example_navigation_and_extraction(self) -> str:
        return json.dumps(
            [
                {
                    GotoAction.name(): GotoAction(url="https://www.google.com").model_dump(
                        exclude={"category", "description"}
                    ),
                },
                {
                    ScrapeAction.name(): ScrapeAction().model_dump(exclude={"category", "description"}),
                },
            ],
            indent=2,
        )

    def example_step(self) -> str:
        return """
{
  "state": {
    "previous_goal_eval": "Success|Failed|Unknown - Analyze the current elements and the image to check if the previous goals/actions are successful like intended by the task. Ignore the action result. The website is the ground truth. Also mention if something unexpected happened like new suggestions in an input field. Shortly state why/why not",
    "memory": "Description of what has been done and what you need to remember until the end of the task",
    "next_goal": "What needs to be done with the next actions"
  },
  "actions": [
   { "one_action_name": {
      // action-specific parameter
      ...
   }
   }, // ... more actions in sequence ...
  ]
}
"""

    def completion_example(self) -> str:
        return CompletionAction(success=True, answer="<answer to the task>").model_dump_json(
            indent=2, exclude={"category", "description", "id"}
        )

    def system(self) -> str:
        return chevron.render(
            self.system_prompt,
            {
                "timstamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "max_actions_per_step": self.max_actions_per_step,
                "action_description": self.space.markdown(),
                "example_form_filling": self.example_form_filling(),
                "example_step": self.example_step(),
                "completion_example": self.completion_example(),
                "completion_action_name": CompletionAction.name(),
                "goto_action_name": GotoAction.name(),
                "example_navigation_and_extraction": self.example_navigation_and_extraction(),
            },
        )

    def task(self, task: str):
        return f"""
Your ultimate task is: {task}.
If you achieved your ultimate task, stop everything and use the done action in the next step to complete the task.
If not, continue as usual.
"""

    def new_task(self, task: str) -> str:
        return f"""
Your new ultimate task is: {task}.
Take the previous context into account and finish your new ultimate task.
"""
