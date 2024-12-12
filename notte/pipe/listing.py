from litellm.files.main import ModelResponse
from loguru import logger

from notte.actions.base import Action, PossibleAction
from notte.actions.parsing import ActionListingParser
from notte.actions.space import ActionSpace
from notte.browser.context import Context
from notte.llms.engine import StructuredContent
from notte.llms.service import LLMService


class ActionListingPipe:
    def __init__(
        self,
        llmserve: LLMService | None = None,
        parser: ActionListingParser = ActionListingParser.TABLE,
    ) -> None:
        self.llmserve: LLMService = llmserve or LLMService()
        self.parser: ActionListingParser = parser

    def forward(
        self,
        context: Context,
        previous_action_list: list[Action] | None = None,
    ) -> list[PossibleAction]:
        if previous_action_list is not None and len(previous_action_list) > 0:
            return self.forward_incremental(context, previous_action_list)

        ctx = context.markdown_description()

        max_tries = 1
        tries = 0
        while tries < max_tries:
            try:
                response = self.llmserve.completion("action-listing/optim", {"document": ctx})
                return self.parse_llm_response(response)
            except Exception:
                tries += 1
                if tries == max_tries:
                    raise Exception(f"Failed to get action list after {max_tries} tries")
        # Add explicit return to satisfy mypy
        raise Exception("Should never reach here")

    def parse_llm_response(self, response: ModelResponse) -> list[PossibleAction]:
        sc = StructuredContent(outer_tag="action-listing")
        if response.choices[0].message.content is None:  # type: ignore
            raise ValueError("No content in response")
        text = sc.extract(response.choices[0].message.content)  # type: ignore
        return self.parser.parse(text)

    def forward_incremental(
        self,
        context: Context,
        previous_action_list: list[Action],
    ) -> list[PossibleAction]:
        try:
            logger.info("🚀 forward incremental")
            ctx = context.subgraph_without(previous_action_list).markdown_description()
            _space = ActionSpace(_actions=previous_action_list)
            response = self.llmserve.completion(
                "action-listing-incr",
                {
                    "document": ctx,
                    "previous_action_list": _space.markdown("all"),
                },
            )
            return self.parse_llm_response(response)
        except Exception:
            return [
                PossibleAction(
                    id=act.id,
                    description=act.description,
                    category=act.category,
                    params=act.params,
                )
                for act in previous_action_list
            ]
