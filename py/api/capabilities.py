NODE_PREFIX = "ComfyUI-GPT-image"
NODE_CATEGORY = NODE_PREFIX

API_PROVIDER_RELAY = "relay"
API_PROVIDER_OPENAI = "openai"
API_PROVIDER_OPTIONS = [API_PROVIDER_RELAY, API_PROVIDER_OPENAI]
DEFAULT_API_PROVIDER = API_PROVIDER_RELAY

DEFAULT_BASE_URL = "https://aihubmix.com/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"

MODELS = ["gpt-image-2", "gpt-image-1.5"]
DEFAULT_MODEL = MODELS[0]

DEFAULT_SIZE = "auto"
SIZE_PRESETS = ["auto", "1K", "2K", "4K"]
GPT_IMAGE_15_SIZE_OPTIONS = ["1024x1024", "1024x1536", "1536x1024"]

GPT_IMAGE_2_MAX_EDGE = 3840
GPT_IMAGE_2_MIN_PIXELS = 655360
GPT_IMAGE_2_MAX_PIXELS = 8294400
GPT_IMAGE_2_MAX_ASPECT_RATIO = 3.0
GPT_IMAGE_2_SIZE_STEP = 16

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

_GPT_IMAGE_15_SIZE_TO_RATIO = {
    "1024x1024": 1.0,
    "1024x1536": 1024.0 / 1536.0,
    "1536x1024": 1536.0 / 1024.0,
}

_GPT_IMAGE_2_PRESET_SIZES = {
    "1K": ["1024x1024", "1024x1536", "1536x1024"],
    "2K": ["2048x2048", "1152x2048", "2048x1152"],
    "4K": ["2880x2880", "2160x3840", "3840x2160"],
}

_SIZE_TO_RATIO = {}
for _size_list in list(_GPT_IMAGE_2_PRESET_SIZES.values()) + [GPT_IMAGE_15_SIZE_OPTIONS]:
    for _size_value in _size_list:
        _width, _height = [int(part) for part in _size_value.split("x")]
        _SIZE_TO_RATIO[_size_value] = _width / _height

MODEL_SPECS = {
    "gpt-image-2": {
        "label": "GPT Image 2",
        "supports_edit": True,
        "supports_input_fidelity": True,
        "supports_custom_size": True,
    },
    "gpt-image-1.5": {
        "label": "GPT Image 1.5",
        "supports_edit": True,
        "supports_input_fidelity": True,
        "supports_custom_size": False,
        "allowed_presets": ["auto", "1K"],
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


def _extract_image_dimensions(images):
    shape = getattr(images, "shape", None)
    if shape is None:
        raise ValueError("images must be a ComfyUI IMAGE tensor.")

    if len(shape) == 3:
        height = int(shape[0])
        width = int(shape[1])
    elif len(shape) == 4:
        height = int(shape[1])
        width = int(shape[2])
    else:
        raise ValueError("images must be a 3D or 4D tensor.")

    if width <= 0 or height <= 0:
        raise ValueError("images must have positive width and height.")

    return width, height


def get_input_aspect_ratio(images):
    width, height = _extract_image_dimensions(images)
    return width / height


def _parse_size_value(size):
    normalized = str(size).strip().lower()
    if not normalized:
        return "auto", None, None

    if normalized == "auto":
        return normalized, None, None

    normalized = normalized.upper()
    if normalized not in SIZE_PRESETS:
        raise ValueError(f"size must be one of: {', '.join(SIZE_PRESETS)}.")

    return normalized, None, None


def _is_valid_gpt_image_2_size(width, height):
    long_edge = max(width, height)
    short_edge = min(width, height)
    total_pixels = width * height

    return (
        long_edge <= GPT_IMAGE_2_MAX_EDGE
        and width % GPT_IMAGE_2_SIZE_STEP == 0
        and height % GPT_IMAGE_2_SIZE_STEP == 0
        and (long_edge / short_edge) <= GPT_IMAGE_2_MAX_ASPECT_RATIO
        and GPT_IMAGE_2_MIN_PIXELS <= total_pixels <= GPT_IMAGE_2_MAX_PIXELS
    )


def _validate_gpt_image_2_size(width, height):
    if not _is_valid_gpt_image_2_size(width, height):
        raise ValueError(
            "gpt-image-2 size must satisfy: max edge <= 3840, both edges multiples of 16, "
            "long/short ratio <= 3:1, and total pixels between 655360 and 8294400."
        )


def _choose_nearest_size_by_ratio(size_options, ratio):
    return min(size_options, key=lambda size: abs(_SIZE_TO_RATIO[size] - ratio))


def _resolve_gpt_image_15_auto_size(images):
    ratio = get_input_aspect_ratio(images)
    return _choose_nearest_size_by_ratio(GPT_IMAGE_15_SIZE_OPTIONS, ratio)

def _resolve_gpt_image_2_preset_size(size_preset, images=None):
    candidate_sizes = _GPT_IMAGE_2_PRESET_SIZES[size_preset]
    if images is None:
        return candidate_sizes[0]

    ratio = get_input_aspect_ratio(images)
    return _choose_nearest_size_by_ratio(candidate_sizes, ratio)


def _resolve_gpt_image_2_auto_size(images):
    width, height = _extract_image_dimensions(images)
    long_edge = max(width, height)
    if long_edge <= 1536:
        size_preset = "1K"
    elif long_edge <= 2048:
        size_preset = "2K"
    else:
        size_preset = "4K"
    return _resolve_gpt_image_2_preset_size(size_preset, images=images)


def resolve_request_size(model_name, size, images=None):
    spec = get_model_spec(model_name)
    normalized, _width, _height = _parse_size_value(size)

    if normalized == "auto":
        if images is None:
            return "auto"

        if spec["supports_custom_size"]:
            return _resolve_gpt_image_2_auto_size(images)

        return _resolve_gpt_image_15_auto_size(images)

    if spec["supports_custom_size"]:
        return _resolve_gpt_image_2_preset_size(normalized, images=images)

    if normalized not in spec["allowed_presets"]:
        raise ValueError(f"Model {model_name} only supports size presets: {', '.join(spec['allowed_presets'])}.")

    if normalized == "1K":
        if images is None:
            return "1024x1024"
        return _resolve_gpt_image_15_auto_size(images)

    return _resolve_gpt_image_15_auto_size(images)


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

    resolve_request_size(model_name, size)

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
    resolve_request_size(model_name, size, images=images)

    if input_fidelity not in INPUT_FIDELITY_OPTIONS:
        raise ValueError(f"input_fidelity must be one of: {', '.join(INPUT_FIDELITY_OPTIONS)}.")

    return spec
