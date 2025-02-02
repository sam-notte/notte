import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

# ############################################################
# Action enums
# ############################################################

ActionStatus = Literal["valid", "failed", "excluded"]
AllActionStatus = ActionStatus | Literal["all"]
ActionRole = Literal["link", "button", "input", "special", "image", "other"]
AllActionRole = ActionRole | Literal["all"]


class BrowserActionId(StrEnum):
    # Base actions
    GOTO = "S1"
    SCRAPE = "S2"
    SCREENSHOT = "S3"
    # Tab actions
    GO_BACK = "S4"
    GO_FORWARD = "S5"
    RELOAD = "S6"
    GOTO_NEW_TAB = "S7"
    # Press & Scroll actions
    PRESS_KEY = "S8"
    SCROLL_UP = "S9"
    SCROLL_DOWN = "S10"
    # Session actions
    WAIT = "S11"
    COMPLETION = "S12"


class InteractionActionId(StrEnum):
    CLICK = "A1"
    FILL = "A2"
    CHECK = "A3"
    SELECT = "A4"
    LIST_DROPDOWN_OPTIONS = "A5"


# ############################################################
# Browser actions models
# ############################################################


class BaseAction(BaseModel):
    """Base model for all actions."""

    id: str
    category: str = Field(exclude=True)
    description: str

    @classmethod
    def name(cls) -> str:
        """Convert a CamelCase string to snake_case"""
        pattern = re.compile(r"(?<!^)(?=[A-Z])")
        return pattern.sub("_", cls.__name__).lower().replace("_action", "")


class BrowserAction(BaseAction):
    """Base model for special actions that are always available and not related to the current page."""

    id: BrowserActionId
    category: str = "Special Browser Actions"


class GotoAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.GOTO
    description: str = "Goto to a URL (in current tab)"
    url: str

    model_config = {"extra": "forbid", "protected_namespaces": ()}  # Allow 'id' to be a field name

    __pydantic_fields_set__ = {"url"}


class GotoNewTabAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.GOTO_NEW_TAB
    description: str = "Goto to a URL (in new tab)"
    url: str


class ScrapeAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.SCRAPE
    description: str = "Scrape the current page data in text format"


class ScreenshotAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.SCREENSHOT
    description: str = "Take a screenshot of the current page"


class GoBackAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.GO_BACK
    description: str = "Go back to the previous page (in current tab)"


class GoForwardAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.GO_FORWARD
    description: str = "Go forward to the next page (in current tab)"


class ReloadAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.RELOAD
    description: str = "Reload the current page"


class WaitAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.WAIT
    description: str = "Wait for a given amount of time (in milliseconds)"
    time_ms: int


class CompletionAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.COMPLETION
    description: str = "Complete the task by returning the answer and terminate the browser session"
    success: bool
    answer: str


class PressKeyAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.PRESS_KEY
    description: str = "Press a keyboard key: e.g. 'Enter', 'Backspace', 'Insert', 'Delete', etc."
    key: str


class ScrollUpAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.SCROLL_UP
    description: str = "Scroll up by a given amount of pixels. Use `null` for scrolling up one page"
    # amount of pixels to scroll. None for scrolling up one page
    amount: int | None = None


class ScrollDownAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.SCROLL_DOWN
    description: str = "Scroll down by a given amount of pixels. Use `null` for scrolling down one page"
    # amount of pixels to scroll. None for scrolling down one page
    amount: int | None = None


# ############################################################
# Interaction actions models
# ############################################################


class InteractionAction(BaseAction):
    id: str
    selector: str | None = Field(default=None, exclude=True)
    category: str = "Interaction Actions"
    press_enter: bool | None = Field(default=None, exclude=True)


class ClickAction(InteractionAction):
    id: str
    description: str = "Click on an element of the current page"


class FillAction(InteractionAction):
    id: str
    description: str = "Fill an input field with a value"
    value: str


class CheckAction(InteractionAction):
    id: str
    description: str = "Check a checkbox. Use `True` to check, `False` to uncheck"
    value: bool


class ListDropdownOptionsAction(InteractionAction):
    id: str
    description: str = "List all options of a dropdown"


class SelectDropdownOptionAction(InteractionAction):
    id: str
    description: str = (
        "Select an option from a dropdown. The `id` field should be set to the select element's id. "
        "Then you can either set the `value` field to the option's text or the `option_id` field to the option's `id`."
    )
    option_id: str | None = None
    value: str | None = None
    option_selector: str | None = Field(exclude=True, default=None)
