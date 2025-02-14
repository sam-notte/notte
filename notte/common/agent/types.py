from litellm import AllMessageValues
from pydantic import BaseModel

from notte.env import TrajectoryStep


class AgentOutput(BaseModel):
    answer: str
    success: bool
    trajectory: list[TrajectoryStep]
    messages: list[AllMessageValues] | None = None
