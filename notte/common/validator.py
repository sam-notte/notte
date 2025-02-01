from typing import final

import chevron
from loguru import logger
from pydantic import BaseModel

from examples.simple.perception import SimplePerception
from notte.common.conversation import Conversation
from notte.common.parser import TaskOutput
from notte.env import TrajectoryStep
from notte.llms.engine import LLMEngine

system_rules = """
You are a validator of an agent who interacts with a browser.
Validate if the output of last action is what the user wanted and if the task is completed.
If the task is unclear defined, you can let it pass.
But if something is missing or the image does not show what was requested dont let it pass.
Try to understand the page and help the model with suggestions like scroll, do x, ... to get the solution right.
Task to validate: {{task}}. Return a JSON object with 2 keys: is_valid and reason.
is_valid is a boolean that indicates if the output is correct.
reason is a string that explains why it is valid or not.
Example:
{
    "is_valid": false,
    "reason": "The user wanted to search for "cat photos", but the agent searched for "dog photos" instead."
}
"""


class ValidationResult(BaseModel):
    valid: bool
    reason: str


@final
class StepValidator:
    def __init__(
        self,
        llm: LLMEngine,
        use_vision: bool = True,
        include_attributes: bool = True,
    ):
        self.use_vision = use_vision
        self.include_attributes = include_attributes
        self.llm: LLMEngine = llm
        self.conv: Conversation = Conversation()
        self.perception: SimplePerception = SimplePerception()

    def validation_message(
        self,
        output: TaskOutput,
        step: TrajectoryStep,
    ) -> str:
        return f"""
Last observation:
{self.perception.perceive(step.obs)}

Last action:
{'No action' if step.action is None else step.action.model_dump_json(exclude_unset=True)}

Task output:
{output}
"""

    def validate(
        self,
        task: str,
        output: TaskOutput,
        step: TrajectoryStep,
    ) -> bool:
        """Validate the output of the last action is what the user wanted"""
        self.conv.clear()
        system_prompt = chevron.render(system_rules, {"task": task})
        self.conv.add_system_message(content=system_prompt)
        self.conv.add_user_message(content=self.validation_message(output, step))

        answer: ValidationResult = self.llm.structured_completion(self.conv.messages(), ValidationResult)
        if not answer.valid:
            logger.info(f"❌ Validator decision: {answer.reason}")
        else:
            logger.info(f"✅ Validator decision: {answer.reason}")
        return answer.valid
