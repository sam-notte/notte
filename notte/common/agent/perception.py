from abc import ABC, abstractmethod

from pydantic import BaseModel

from notte.browser.observation import Observation


class PerceptionResult(BaseModel):
    metadata: str
    actions: str
    data: str
    full: str

    @classmethod
    def empty(cls) -> "PerceptionResult":
        return cls(metadata="", actions="", data="", full="")


class BasePerception(ABC):

    @abstractmethod
    def perceive_metadata(self, obs: Observation) -> str:
        pass

    @abstractmethod
    def perceive_actions(self, obs: Observation) -> str:
        pass

    @abstractmethod
    def perceive_data(self, obs: Observation) -> str:
        pass

    @abstractmethod
    def perceive_full(self, obs: Observation) -> str:
        pass

    def perceive(self, obs: Observation) -> PerceptionResult:
        return PerceptionResult(
            metadata=self.perceive_metadata(obs),
            actions=self.perceive_actions(obs),
            data=self.perceive_data(obs),
            full=self.perceive_full(obs),
        )
