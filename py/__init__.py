from .api.capabilities import NODE_PREFIX
from .nodes import GPTImageEditNode, GPTImageGenerateNode


def _node_name(label):
    return f"{NODE_PREFIX} {label}"


NODE_CLASS_MAPPINGS = {
    _node_name("Generate"): GPTImageGenerateNode,
    _node_name("Edit"): GPTImageEditNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {key: key for key in NODE_CLASS_MAPPINGS}
