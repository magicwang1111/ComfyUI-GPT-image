NODE_PREFIX = "ComfyUI-GPT-image"
NODE_CATEGORY = NODE_PREFIX

DEFAULT_BASE_URL = "https://aihubmix.com/v1"

MODELS = ["gpt-image-2", "gpt-image-1.5"]
DEFAULT_MODEL = MODELS[0]

SIZE_OPTIONS = ["auto", "1024x1024", "1024x1536", "1536x1024"]
DEFAULT_SIZE = "auto"

QUALITY_OPTIONS = ["auto", "low", "medium", "high"]
DEFAULT_QUALITY = "auto"

BACKGROUND_OPTIONS = ["auto", "transparent", "opaque"]
DEFAULT_BACKGROUND = "auto"

OUTPUT_FORMAT_OPTIONS = ["png", "jpeg", "webp"]
DEFAULT_OUTPUT_FORMAT = "png"

INPUT_FIDELITY_OPTIONS = ["low", "high"]
DEFAULT_INPUT_FIDELITY = "low"

DEFAULT_N = 1
MAX_N = 10

MODEL_SPECS = {
    "gpt-image-2": {
        "label": "GPT Image 2",
        "supports_edit": True,
        "supports_input_fidelity": True,
    },
    "gpt-image-1.5": {
        "label": "GPT Image 1.5",
        "supports_edit": True,
        "supports_input_fidelity": True,
    },
}


def get_model_spec(model_name):
    if model_name not in MODEL_SPECS:
        raise ValueError(f"Unsupported GPT Image model: {model_name}")
    return MODEL_SPECS[model_name]


def _count_input_images(images):
    if images is None:
        raise ValueError("images is required.")

    shape = getattr(images, "shape", None)
    if shape is None:
        raise ValueError("images must be a ComfyUI IMAGE tensor.")

    if len(shape) == 3:
        return 1
    if len(shape) == 4:
        return int(shape[0])

    raise ValueError("images must be a 3D or 4D tensor.")


def _validate_common_request(
    model_name,
    prompt,
    n=DEFAULT_N,
    size=DEFAULT_SIZE,
    quality=DEFAULT_QUALITY,
    background=DEFAULT_BACKGROUND,
    output_format=DEFAULT_OUTPUT_FORMAT,
):
    spec = get_model_spec(model_name)

    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt is required.")

    if not isinstance(n, int):
        raise ValueError("n must be an integer.")
    if n < 1 or n > MAX_N:
        raise ValueError(f"n must be between 1 and {MAX_N}.")

    if size not in SIZE_OPTIONS:
        raise ValueError(f"size must be one of: {', '.join(SIZE_OPTIONS)}.")

    if quality not in QUALITY_OPTIONS:
        raise ValueError(f"quality must be one of: {', '.join(QUALITY_OPTIONS)}.")

    if background not in BACKGROUND_OPTIONS:
        raise ValueError(f"background must be one of: {', '.join(BACKGROUND_OPTIONS)}.")

    if output_format not in OUTPUT_FORMAT_OPTIONS:
        raise ValueError(f"output_format must be one of: {', '.join(OUTPUT_FORMAT_OPTIONS)}.")

    return spec


def validate_generate_request(
    model_name,
    prompt,
    n=DEFAULT_N,
    size=DEFAULT_SIZE,
    quality=DEFAULT_QUALITY,
    background=DEFAULT_BACKGROUND,
    output_format=DEFAULT_OUTPUT_FORMAT,
):
    return _validate_common_request(
        model_name=model_name,
        prompt=prompt,
        n=n,
        size=size,
        quality=quality,
        background=background,
        output_format=output_format,
    )


def validate_edit_request(
    model_name,
    prompt,
    images,
    n=DEFAULT_N,
    size=DEFAULT_SIZE,
    quality=DEFAULT_QUALITY,
    background=DEFAULT_BACKGROUND,
    output_format=DEFAULT_OUTPUT_FORMAT,
    input_fidelity=DEFAULT_INPUT_FIDELITY,
):
    spec = _validate_common_request(
        model_name=model_name,
        prompt=prompt,
        n=n,
        size=size,
        quality=quality,
        background=background,
        output_format=output_format,
    )

    _count_input_images(images)

    if input_fidelity not in INPUT_FIDELITY_OPTIONS:
        raise ValueError(f"input_fidelity must be one of: {', '.join(INPUT_FIDELITY_OPTIONS)}.")

    return spec
