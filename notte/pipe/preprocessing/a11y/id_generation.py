from loguru import logger

from notte.browser.node_type import A11yNode, NodeRole
from notte.pipe.preprocessing.a11y.traversal import (
    find_all_paths_by_role_and_name,
    list_interactive_nodes,
)


def generate_sequential_ids(root: A11yNode) -> A11yNode:
    """
    Generates sequential IDs for interactive elements in the accessibility tree
    using depth-first search.
    """
    stack = [root]
    id_counter = {
        "L": 1,
        "B": 1,
        "I": 1,
    }

    while stack:
        node = stack.pop()
        children = node.get("children", [])

        role = NodeRole.from_value(node["role"])
        if isinstance(role, str):
            logger.error(
                f"Unsupported role to convert to ID: {node}. Please add this role to the ID generation logic ASAP."
            )
        elif len(node["name"].strip()) > 0:
            id = role.short_id()
            if id is not None:
                node["id"] = f"{id}{id_counter[id]}"
                id_counter[id] += 1
        stack.extend(reversed(children))

    return root


def sync_ids_between_trees(target: A11yNode, source: A11yNode) -> A11yNode:
    """
    Synchronizes IDs between two accessibility trees by copying IDs from the source
    tree to matching nodes in the target tree.
    """

    def add_id(reference_node: A11yNode) -> A11yNode:
        ref_id = reference_node.get("id")
        if ref_id is None:
            raise ValueError("Reference node does not have an ID")
        matches = find_all_paths_by_role_and_name(target, reference_node["role"], reference_node["name"])
        if len(matches) == 0:
            raise ValueError(f"Processing error in the complex axt for {reference_node}")

        for match in matches:
            assert match[0]["role"] == reference_node["role"]
            assert match[0]["name"] == reference_node["name"]
            existing_id = match[0].get("id")
            if existing_id == ref_id:
                return match[0]
            if existing_id is None:
                match[0]["id"] = ref_id
                return match[0]

        raise ValueError(f"Sync ID issue for {reference_node} not found in target tree: {matches}")

    interactions = list_interactive_nodes(source)
    for interaction in interactions:
        _ = add_id(interaction)
    return target
