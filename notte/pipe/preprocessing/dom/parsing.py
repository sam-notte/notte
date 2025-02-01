import logging
from pathlib import Path
from typing import TypedDict

from playwright.async_api import Page
from pydantic import BaseModel

from notte.browser.dom_tree import DomNode as NotteDomNode
from notte.pipe.preprocessing.a11y.id_generation import simple_generate_sequential_ids
from notte.pipe.preprocessing.a11y.notte_selector import generate_notte_selector
from notte.pipe.preprocessing.dom.types import DOMBaseNode, DOMElementNode, DOMTextNode

DOM_TREE_JS_PATH = Path(__file__).parent / "buildDomNode.js"
logger = logging.getLogger(__name__)


class DomTreeDict(TypedDict):
    type: str
    text: str
    tagName: str
    xpath: str
    attributes: dict[str, str]
    isVisible: bool
    isInteractive: bool
    isTopElement: bool
    highlightIndex: int | None
    shadowRoot: bool
    children: list["DomTreeDict"]


class DomParsingConfig(BaseModel):
    highlight_elements: bool = True
    focus_element: int = -1
    viewport_expansion: int = 0


class ParseDomTreePipe:

    @staticmethod
    async def forward(page: Page, config: DomParsingConfig | None = None) -> NotteDomNode:
        config = config or DomParsingConfig()
        dom_tree = await ParseDomTreePipe.parse_dom_tree(page, config)
        for step in [simple_generate_sequential_ids, generate_notte_selector]:
            dom_tree = step(dom_tree)
            if isinstance(dom_tree, dict):
                raise ValueError(f"Dom tree is not a valid NotteDomNode: {dom_tree}")
        return dom_tree.to_notte_domnode()

    @staticmethod
    async def parse_dom_tree(page: Page, config: DomParsingConfig) -> DOMBaseNode:
        js_code = DOM_TREE_JS_PATH.read_text()
        node: DomTreeDict | None = await page.evaluate(js_code, config.model_dump())  # type: ignore
        if node is None:
            raise ValueError("Failed to parse HTML to dictionary")
        return ParseDomTreePipe._parse_node(node)

    @staticmethod
    def _parse_node(
        node: DomTreeDict,
        parent: "DOMElementNode | None" = None,
    ) -> DOMBaseNode:
        if node.get("type") == "TEXT_NODE":
            text_node = DOMTextNode(
                text=node["text"],
                is_visible=node["isVisible"],
                parent=parent,
            )

            return text_node

        tag_name = node["tagName"]

        element_node = DOMElementNode(
            tag_name=tag_name,
            xpath=node["xpath"],
            attributes=node.get("attributes", {}),
            is_visible=node.get("isVisible", False),
            is_interactive=node.get("isInteractive", False),
            is_top_element=node.get("isTopElement", False),
            highlight_index=node.get("highlightIndex"),
            shadow_root=node.get("shadowRoot", False),
            parent=parent,
        )

        children: list[DOMBaseNode] = []
        for child in node.get("children", []):
            if child is not None:
                child_node = ParseDomTreePipe._parse_node(child, parent=element_node)
                children.append(child_node)

        element_node.children = children

        return element_node
