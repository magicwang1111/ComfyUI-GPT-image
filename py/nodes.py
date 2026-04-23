import json
import os
from pathlib import Path

from .api import (
    BACKGROUND_OPTIONS,
    DEFAULT_BACKGROUND,
    DEFAULT_BASE_URL,
    DEFAULT_INPUT_FIDELITY,
    DEFAULT_MODEL,
    DEFAULT_N,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_QUALITY,
    DEFAULT_SIZE,
    GPTImageAPIError,
    INPUT_FIDELITY_OPTIONS,
    MAX_N,
    MODELS,
    NODE_CATEGORY,
    OUTPUT_FORMAT_OPTIONS,
    QUALITY_OPTIONS,
    SIZE_PRESETS,
    AsyncClient,
    Client,
    build_edit_request,
    build_generate_payload,
    extract_generation_output,
    resolve_request_size,
    sanitize_response_for_debug,
    validate_edit_request,
    validate_generate_request,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_JSON_PATH = ROOT_DIR / "config.local.json"
DEFAULT_REQUEST_TIMEOUT = 600


def _load_json_config():
    if not CONFIG_JSON_PATH.exists():
        return {}

    try:
        with CONFIG_JSON_PATH.open("r", encoding="utf-8") as handle:
            config_data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{CONFIG_JSON_PATH.name} is not valid JSON: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Failed to read {CONFIG_JSON_PATH.name}: {exc}") from exc

    if not isinstance(config_data, dict):
        raise ValueError(f"{CONFIG_JSON_PATH.name} must contain a top-level JSON object.")

    return config_data


def _load_env_value(*keys):
    for key in keys:
        value = os.getenv(key, "").strip()
        if value:
            return value
    return ""


def _parse_timeout(value):
    if isinstance(value, bool):
        raise ValueError("request_timeout must be an integer.")

    if isinstance(value, int):
        timeout = value
    else:
        try:
            timeout = int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("request_timeout must be an integer.") from exc

    if timeout < 5:
        raise ValueError("request_timeout must be greater than or equal to 5.")

    return timeout


def _json_value_present(config_data, key):
    if key not in config_data:
        return False

    value = config_data[key]
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _resolve_api_key(config_data):
    if _json_value_present(config_data, "api_key"):
        return str(config_data["api_key"]).strip()

    env_api_key = _load_env_value("GPT_IMAGE_API_KEY")
    if env_api_key:
        return env_api_key

    raise ValueError(
        "An API key is required. Add api_key to config.local.json or set GPT_IMAGE_API_KEY."
    )


def _resolve_base_url(config_data):
    if _json_value_present(config_data, "base_url"):
        return str(config_data["base_url"]).strip().rstrip("/")

    env_base_url = _load_env_value("GPT_IMAGE_BASE_URL")
    if env_base_url:
        return env_base_url.rstrip("/")

    return DEFAULT_BASE_URL


def _resolve_request_timeout(config_data):
    if _json_value_present(config_data, "request_timeout"):
        return _parse_timeout(config_data["request_timeout"])

    return DEFAULT_REQUEST_TIMEOUT


def _resolve_model_name(selected_model, model_override):
    if model_override is None:
        return selected_model
    if not isinstance(model_override, str):
        raise ValueError("model_override must be a string.")

    override = model_override.strip()
    return override or selected_model


def _resolve_runtime_client_kwargs():
    config_data = _load_json_config()
    return {
        "api_key": _resolve_api_key(config_data),
        "timeout": _resolve_request_timeout(config_data),
        "base_url": _resolve_base_url(config_data),
    }


def _create_runtime_client():
    return Client(**_resolve_runtime_client_kwargs())


def _create_runtime_async_client():
    return AsyncClient(**_resolve_runtime_client_kwargs())


def _raise_with_api_guidance(exc):
    if exc.status_code in {401, 403}:
        raise ValueError(
            f"API request was rejected with {exc.status_code}. Check api_key, base_url, relay permissions, billing, and model."
        ) from exc

    if exc.status_code == 429:
        raise ValueError("API rate limit exceeded (429). Wait and retry, or use a project with higher quota.") from exc

    raise ValueError(str(exc)) from exc


def _build_response_json(response_payload):
    sanitized = sanitize_response_for_debug(response_payload)
    return json.dumps(sanitized, ensure_ascii=False, indent=2)


class GPTImageGenerateNode:
    OUTPUT_NODE = False
    CATEGORY = NODE_CATEGORY
    FUNCTION = "generate"

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "response_json")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "model": (MODELS, {"default": DEFAULT_MODEL}),
            },
            "optional": {
                "n": ("INT", {"default": DEFAULT_N, "min": 1, "max": MAX_N}),
                "size": (SIZE_PRESETS, {"default": DEFAULT_SIZE}),
                "quality": (QUALITY_OPTIONS, {"default": DEFAULT_QUALITY}),
                "background": (BACKGROUND_OPTIONS, {"default": DEFAULT_BACKGROUND}),
                "output_format": (OUTPUT_FORMAT_OPTIONS, {"default": DEFAULT_OUTPUT_FORMAT}),
                "model_override": ("STRING", {"multiline": False, "default": ""}),
            },
        }

    async def generate(
        self,
        prompt,
        model=DEFAULT_MODEL,
        n=DEFAULT_N,
        size=DEFAULT_SIZE,
        quality=DEFAULT_QUALITY,
        background=DEFAULT_BACKGROUND,
        output_format=DEFAULT_OUTPUT_FORMAT,
        model_override="",
    ):
        validate_generate_request(
            model_name=model,
            prompt=prompt,
            n=n,
            size=size,
            quality=quality,
            background=background,
            output_format=output_format,
        )

        client = _create_runtime_async_client()
        try:
            request_model_name = _resolve_model_name(model, model_override)
            request_size = resolve_request_size(model, size)
            payload = build_generate_payload(
                model_name=request_model_name,
                prompt=prompt,
                n=n,
                size=request_size,
                quality=quality,
                background=background,
                output_format=output_format,
            )

            try:
                response_payload = await client.generate_image(payload)
            except GPTImageAPIError as exc:
                _raise_with_api_guidance(exc)
        finally:
            await client.close()

        print(f"[ComfyUI-GPT-image] {request_model_name} generate request completed")
        return extract_generation_output(response_payload), _build_response_json(response_payload)


class GPTImageEditNode:
    OUTPUT_NODE = False
    CATEGORY = NODE_CATEGORY
    FUNCTION = "generate"

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "response_json")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "images": ("IMAGE",),
                "model": (MODELS, {"default": DEFAULT_MODEL}),
            },
            "optional": {
                "n": ("INT", {"default": DEFAULT_N, "min": 1, "max": MAX_N}),
                "size": (SIZE_PRESETS, {"default": DEFAULT_SIZE}),
                "quality": (QUALITY_OPTIONS, {"default": DEFAULT_QUALITY}),
                "background": (BACKGROUND_OPTIONS, {"default": DEFAULT_BACKGROUND}),
                "output_format": (OUTPUT_FORMAT_OPTIONS, {"default": DEFAULT_OUTPUT_FORMAT}),
                "input_fidelity": (INPUT_FIDELITY_OPTIONS, {"default": DEFAULT_INPUT_FIDELITY}),
                "model_override": ("STRING", {"multiline": False, "default": ""}),
            },
        }

    async def generate(
        self,
        prompt,
        images,
        model=DEFAULT_MODEL,
        n=DEFAULT_N,
        size=DEFAULT_SIZE,
        quality=DEFAULT_QUALITY,
        background=DEFAULT_BACKGROUND,
        output_format=DEFAULT_OUTPUT_FORMAT,
        input_fidelity=DEFAULT_INPUT_FIDELITY,
        model_override="",
    ):
        validate_edit_request(
            model_name=model,
            prompt=prompt,
            images=images,
            n=n,
            size=size,
            quality=quality,
            background=background,
            output_format=output_format,
            input_fidelity=input_fidelity,
        )

        client = _create_runtime_async_client()
        try:
            request_model_name = _resolve_model_name(model, model_override)
            request_size = resolve_request_size(model, size, images=images)
            data, files = build_edit_request(
                model_name=request_model_name,
                prompt=prompt,
                images=images,
                n=n,
                size=request_size,
                quality=quality,
                background=background,
                output_format=output_format,
                input_fidelity=input_fidelity,
            )

            try:
                response_payload = await client.edit_image(data, files)
            except GPTImageAPIError as exc:
                _raise_with_api_guidance(exc)
        finally:
            await client.close()

        print(f"[ComfyUI-GPT-image] {request_model_name} edit request completed")
        return extract_generation_output(response_payload), _build_response_json(response_payload)
