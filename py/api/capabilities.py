NODE_PREFIX = "ComfyUI-GPT-image"
NODE_CATEGORY = NODE_PREFIX

DEFAULT_BASE_URL = "https://aihubmix.com/v1"

MODELS = ["gpt-image-2", "gpt-image-1.5"]
DEFAULT_MODEL = MODELS[0]

DEFAULT_SIZE = "auto"
GPT_IMAGE_15_SIZE_OPTIONS = ["auto", "1024x1024", "1024x1536", "1536x1024"]

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
        "allowed_sizes": GPT_IMAGE_15_SIZE_OPTIONS,
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

    parts = normalized.split("x")
    if len(parts) != 2:
        raise ValueError("size must be 'auto' or look like 'WIDTHxHEIGHT'.")

    try:
        width = int(parts[0].strip())
        height = int(parts[1].strip())
    except ValueError as exc:
        raise ValueError("size must be 'auto' or look like 'WIDTHxHEIGHT'.") from exc

    if width <= 0 or height <= 0:
        raise ValueError("size width and height must be greater than 0.")

    return f"{width}x{height}", width, height


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


def _resolve_gpt_image_15_auto_size(images):
    ratio = get_input_aspect_ratio(images)
    return min(_GPT_IMAGE_15_SIZE_TO_RATIO, key=lambda size: abs(_GPT_IMAGE_15_SIZE_TO_RATIO[size] - ratio))


def _candidate_values_around(value):
    center = max(1, int(round(value / GPT_IMAGE_2_SIZE_STEP)))
    candidates = set()
    for offset in range(-2, 3):
        index = center + offset
        if index > 0:
            candidates.add(index * GPT_IMAGE_2_SIZE_STEP)
    return sorted(candidates)


def _resolve_gpt_image_2_auto_size(images):
    width, height = _extract_image_dimensions(images)
    width = float(width)
    height = float(height)

    long_edge = max(width, height)
    short_edge = min(width, height)
    if short_edge <= 0:
        raise ValueError("images must have positive width and height.")

    if (long_edge / short_edge) > GPT_IMAGE_2_MAX_ASPECT_RATIO:
        if width >= height:
            width = height * GPT_IMAGE_2_MAX_ASPECT_RATIO
        else:
            height = width * GPT_IMAGE_2_MAX_ASPECT_RATIO

    scale = min(1.0, GPT_IMAGE_2_MAX_EDGE / max(width, height))
    width *= scale
    height *= scale

    total_pixels = width * height
    if total_pixels > GPT_IMAGE_2_MAX_PIXELS:
        scale = (GPT_IMAGE_2_MAX_PIXELS / total_pixels) ** 0.5
        width *= scale
        height *= scale

    total_pixels = width * height
    if total_pixels < GPT_IMAGE_2_MIN_PIXELS:
        scale = (GPT_IMAGE_2_MIN_PIXELS / total_pixels) ** 0.5
        width *= scale
        height *= scale

    scale = min(1.0, GPT_IMAGE_2_MAX_EDGE / max(width, height))
    width *= scale
    height *= scale

    target_ratio = width / height
    target_area = width * height
    width_candidates = _candidate_values_around(width)
    height_candidates = _candidate_values_around(height)

    best = None
    best_score = None
    for candidate_width in width_candidates:
        for candidate_height in height_candidates:
            if not _is_valid_gpt_image_2_size(candidate_width, candidate_height):
                continue

            candidate_ratio = candidate_width / candidate_height
            candidate_area = candidate_width * candidate_height
            score = (
                abs(candidate_ratio - target_ratio),
                abs(candidate_area - target_area) / max(target_area, 1.0),
                abs(candidate_width - width) + abs(candidate_height - height),
            )
            if best_score is None or score < best_score:
                best = (candidate_width, candidate_height)
                best_score = score

    if best is None:
        raise ValueError("Failed to resolve a valid auto size for gpt-image-2 from the input image.")

    return f"{best[0]}x{best[1]}"


def resolve_request_size(model_name, size, images=None):
    spec = get_model_spec(model_name)
    normalized, width, height = _parse_size_value(size)

    if normalized != "auto":
        if spec["supports_custom_size"]:
            _validate_gpt_image_2_size(width, height)
            return normalized

        allowed_sizes = spec["allowed_sizes"]
        if normalized not in allowed_sizes:
            raise ValueError(f"Model {model_name} only supports sizes: {', '.join(allowed_sizes)}.")
        return normalized

    if images is None:
        return "auto"

    if spec["supports_custom_size"]:
        return _resolve_gpt_image_2_auto_size(images)

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
