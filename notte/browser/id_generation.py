from typing import Literal, final

from notte.browser.snapshot import BrowserSnapshot
from notte.pipe.preprocessing.a11y.id_generation import (
    generate_sequential_ids,
    sync_ids_between_trees,
)


@final
class RandomIdGenerator:
    """
    Generates IDs for Notte nodes.
    """

    def __init__(
        self,
        id_element: Literal["a11y_tree", "html_tree", "snapshot"] = "a11y_tree",
    ):
        self.id_element = id_element

    def generate(self, snapshot: BrowserSnapshot) -> BrowserSnapshot:
        match self.id_element:
            case "a11y_tree":
                snapshot.a11y_tree.simple = generate_sequential_ids(snapshot.a11y_tree.simple)
                snapshot.a11y_tree.raw = sync_ids_between_trees(
                    source=snapshot.a11y_tree.simple, target=snapshot.a11y_tree.raw
                )
            case _:
                raise ValueError(f"ID element: {self.id_element} is currently not supported")
        return snapshot

    def sync(self, target: BrowserSnapshot, source: BrowserSnapshot) -> BrowserSnapshot:
        match self.id_element:
            case "a11y_tree":
                target.a11y_tree.simple = sync_ids_between_trees(
                    source=source.a11y_tree.simple, target=target.a11y_tree.simple
                )
                target.a11y_tree.raw = sync_ids_between_trees(source=source.a11y_tree.raw, target=target.a11y_tree.raw)
            case _:
                raise ValueError(f"ID element: {self.id_element} is currently not supported")
        return target
