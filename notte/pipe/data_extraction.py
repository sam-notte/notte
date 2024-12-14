from loguru import logger
from tiktoken import encoding_for_model
from typing_extensions import final

from notte.browser.context import Context
from notte.browser.node_type import NotteNode
from notte.llms.engine import StructuredContent
from notte.llms.service import LLMService
from notte.pipe.preprocessing.a11y.tree import ProcessedA11yTree


@final
class DataExtractionPipe:

    def __init__(self, llmserve: LLMService | None = None) -> None:
        self.llmserve: LLMService = llmserve or LLMService()
        self.token_encoder = encoding_for_model("gpt-4o")
        self.max_tokens = 7300

    def forward(self, context: Context) -> str:
        # TODO: add DIVID & CONQUER once this is implemented
        document = context.markdown_description(include_ids=False)
        if len(self.token_encoder.encode(document)) > self.max_tokens:
            logger.warning(
                (
                    "Document too long for data extraction: "
                    f" {len(self.token_encoder.encode(document))} tokens => use Simple AXT instead"
                )
            )
            tree = ProcessedA11yTree.from_a11y_tree(context.snapshot.a11y_tree)
            simple_node = NotteNode.from_a11y_node(tree.simple_tree, path=context.snapshot.url)
            document = Context.format(simple_node, include_ids=False)
        # make LLM call
        response = self.llmserve.completion(prompt_id="data-extraction", variables={"document": document})
        sc = StructuredContent(outer_tag="data-extraction")
        if response.choices[0].message.content is None:  # type: ignore
            raise ValueError("No content in response")
        text = sc.extract(response.choices[0].message.content)  # type: ignore
        return text
