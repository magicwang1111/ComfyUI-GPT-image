import base64
import copy
import io

import numpy
import PIL.Image
import torch

from .capabilities import (
    DEFAULT_BACKGROUND,
    DEFAULT_INPUT_FIDELITY,
    DEFAULT_N,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_QUALITY,
    DEFAULT_SIZE,
)

VAPEUR_GPT_IMAGE_2_RATES_USD_PER_MILLION = {
    "text_input": 5.0,
    "image_input": 8.0,
    "image_output": 30.0,
    "cached_text_input": 1.25,
    "cached_image_input": 2.0,
}


def _tensor_to_pil_images(images):
    if images is None:
        return []

    if not isinstance(images, torch.Tensor):
        raise ValueError("images must be a torch.Tensor.")

    if images.ndim == 3:
        images = images.unsqueeze(0)
    elif images.ndim != 4:
        raise ValueError("images must be a 3D or 4D tensor.")

    np_images = numpy.clip(images.detach().cpu().numpy() * 255.0, 0.0, 255.0).astype(numpy.uint8)
    return [PIL.Image.fromarray(np_image, mode="RGB") for np_image in np_images]


def _pil_images_to_tensor(images):
    if not images:
        raise ValueError("At least one image is required to build an IMAGE tensor.")

    tensors = []
    for image in images:
        rgb_image = image.convert("RGB")
        image_np = numpy.array(rgb_image).astype(numpy.float32) / 255.0
        tensors.append(torch.from_numpy(image_np))
    return torch.stack(tensors)


def _encode_image_to_png_bytes(image):
    bytes_io = io.BytesIO()
    image.save(bytes_io, format="PNG")
    return bytes_io.getvalue()


def build_generate_payload(
    model_name,
    prompt,
    n=DEFAULT_N,
    size=DEFAULT_SIZE,
    quality=DEFAULT_QUALITY,
    background=DEFAULT_BACKGROUND,
    output_format=DEFAULT_OUTPUT_FORMAT,
):
    return {
        "model": model_name,
        "prompt": prompt.strip(),
        "n": n,
        "size": size,
        "quality": quality,
        "background": background,
        "output_format": output_format,
    }


def build_edit_request(
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
    data = {
        "model": model_name,
        "prompt": prompt.strip(),
        "n": n,
        "size": size,
        "quality": quality,
        "background": background,
        "output_format": output_format,
        "input_fidelity": input_fidelity,
    }

    files = []
    for index, image in enumerate(_tensor_to_pil_images(images)):
        files.append(
            (
                "image[]",
                (f"input_{index}.png", _encode_image_to_png_bytes(image), "image/png"),
            )
        )

    return data, files


def _sanitize_payload(value, parent_key=None):
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if key == "b64_json" and isinstance(item, str):
                sanitized[key] = f"<base64 omitted ({len(item)} chars)>"
            else:
                sanitized[key] = _sanitize_payload(item, key)
        return sanitized

    if isinstance(value, list):
        return [_sanitize_payload(item, parent_key) for item in value]

    return value


def sanitize_response_for_debug(response_payload):
    return _sanitize_payload(copy.deepcopy(response_payload))


def _nonnegative_token_count(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def estimate_vapeur_gpt_image_2_cost(response_payload):
    if not isinstance(response_payload, dict):
        return None

    usage = response_payload.get("usage")
    if not isinstance(usage, dict):
        return None

    input_details = usage.get("input_tokens_details")
    output_details = usage.get("output_tokens_details")
    input_details = input_details if isinstance(input_details, dict) else {}
    output_details = output_details if isinstance(output_details, dict) else {}

    text_input_tokens = _nonnegative_token_count(input_details.get("text_tokens"))
    image_input_tokens = _nonnegative_token_count(input_details.get("image_tokens"))
    image_output_tokens = _nonnegative_token_count(output_details.get("image_tokens"))

    if image_output_tokens is None:
        image_output_tokens = _nonnegative_token_count(usage.get("output_tokens"))

    if text_input_tokens is None or image_input_tokens is None or image_output_tokens is None:
        return None

    token_counts = {
        "text_input": text_input_tokens,
        "image_input": image_input_tokens,
        "image_output": image_output_tokens,
    }
    cached_details = input_details.get("cached_tokens_details")
    cached_details = cached_details if isinstance(cached_details, dict) else {}
    cached_text = _nonnegative_token_count(cached_details.get("text_tokens"))
    cached_image = _nonnegative_token_count(cached_details.get("image_tokens"))
    cache_breakdown_available = (
        cached_text is not None and cached_image is not None
        and cached_text <= text_input_tokens and cached_image <= image_input_tokens
    )
    if cache_breakdown_available:
        token_counts["text_input"] -= cached_text
        token_counts["image_input"] -= cached_image
        token_counts["cached_text_input"] = cached_text
        token_counts["cached_image_input"] = cached_image

    breakdown_usd = {
        key: tokens * VAPEUR_GPT_IMAGE_2_RATES_USD_PER_MILLION[key] / 1_000_000
        for key, tokens in token_counts.items()
    }

    return {
        "currency": "USD",
        "cache_pricing": "reported_breakdown" if cache_breakdown_available else "uncached_estimate",
        "estimated_total_usd": sum(breakdown_usd.values()),
        "tokens": token_counts,
        "breakdown_usd": breakdown_usd,
        "rates_usd_per_million": dict(VAPEUR_GPT_IMAGE_2_RATES_USD_PER_MILLION),
    }


def _decode_base64_image(encoded_image):
    image_bytes = base64.b64decode(encoded_image)
    with io.BytesIO(image_bytes) as bytes_io:
        return PIL.Image.open(bytes_io).convert("RGB")


def extract_generation_output(response_payload):
    images = []

    for image_data in response_payload.get("data", []):
        if not isinstance(image_data, dict):
            continue

        encoded_image = image_data.get("b64_json")
        if isinstance(encoded_image, str) and encoded_image:
            images.append(_decode_base64_image(encoded_image))

    if not images:
        raise ValueError("API did not return any base64 image data for this request.")

    return _pil_images_to_tensor(images)
