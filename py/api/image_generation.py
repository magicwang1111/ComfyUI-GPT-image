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
