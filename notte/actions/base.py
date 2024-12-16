from dataclasses import dataclass, field
from typing import Any, Literal

from notte.browser.node_type import NotteNode


@dataclass
class ActionParameter:
    name: str
    type: str
    default: str | None = None
    values: list[str] = field(default_factory=list)

    def description(self) -> str:
        base = f"{self.name}: {self.type}"
        if len(self.values) > 0:
            base += f" = [{', '.join(self.values)}]"
        return base

    @staticmethod
    def from_json(json: dict[str, Any]) -> "ActionParameter":
        return ActionParameter(
            name=json["name"],
            type=json["type"],
            values=json["values"],
            default=json["default"],
        )


@dataclass
class ActionParameterValue:
    parameter_name: str
    value: str


ActionStatus = Literal["valid", "failed", "excluded"]
ActionRole = Literal["link", "button", "input", "other"]


@dataclass
class CachedAction:
    status: ActionStatus
    description: str
    category: str
    code: str | None
    params: list[ActionParameter] = field(default_factory=list)


@dataclass
class PossibleAction:
    id: str
    description: str
    category: str
    params: list[ActionParameter] = field(default_factory=list)


@dataclass
class Action(PossibleAction):
    status: ActionStatus = "valid"

    def markdown(self) -> str:
        return self.description

    @property
    def role(self) -> ActionRole:
        match self.id[0]:
            case "L":
                return "link"
            case "B":
                return "button"
            case "I":
                return "input"
            case _:
                return "other"

    def embedding_description(self) -> str:
        return self.role + " " + self.description

    @staticmethod
    def from_json(json: dict[str, Any]) -> "Action":
        return Action(
            id=json["id"],
            description=json["description"],
            category=json["category"],
            params=[ActionParameter.from_json(param) for param in json["params"]],
            status=json["status"],
        )


@dataclass
class ExecutableAction(Action):
    node: NotteNode | None = None
    params_values: list[ActionParameterValue] = field(default_factory=list)
    code: str | None = None


@dataclass
class SpecialAction(Action):
    """
    Special actions are actions that are always available and are not related to the current page.

    - "S1": Go to a specific URL
    - "S2": Extract Data page data
    - "S3": Take a screenshot of the current page
    - "S4": Go to the previous page
    - "S5": Go to the next page
    - "S6": Wait for a specific amount of time (in seconds)
    - "S7": Terminate the current session
    """

    id: Literal["S1", "S2", "S3", "S4", "S5", "S6", "S7"]
    description: str = "Special action"
    category: str = "Special Browser Actions"

    @staticmethod
    def is_special(action_id: str) -> bool:
        return action_id in ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]

    def __post_init__(self):
        if not SpecialAction.is_special(self.id):
            raise ValueError(f"Invalid special action ID: {self.id}")

    @staticmethod
    def list() -> list["SpecialAction"]:
        return [
            SpecialAction(
                id="S1",
                description="Go to a specific URL",
                category="Special Browser Actions",
                params=[
                    ActionParameter(name="url", type="string", default=None),
                ],
            ),
            SpecialAction(
                id="S2",
                description="Scrape data from the current page",
                category="Special Browser Actions",
            ),
            SpecialAction(
                id="S3",
                description="Take a screenshot of the current page",
                category="Special Browser Actions",
            ),
            SpecialAction(
                id="S4",
                description="Go to the previous page",
                category="Special Browser Actions",
            ),
            SpecialAction(
                id="S5",
                description="Go to the next page",
                category="Special Browser Actions",
            ),
            SpecialAction(
                id="S6",
                description="Wait for a specific amount of time (in seconds)",
                category="Special Browser Actions",
            ),
            SpecialAction(
                id="S7",
                description="Terminate the current session",
                category="Special Browser Actions",
            ),
        ]
