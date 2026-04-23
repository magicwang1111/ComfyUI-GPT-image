import argparse
import io
import json
import os
import sys
from pathlib import Path

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_BASE_URL = "https://aihubmix.com/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"
MODELS = ["gpt-image-2", "gpt-image-1.5"]

DEFAULT_COUNTS = [1, 4, 8, 16, 24]


def parse_args():
    parser = argparse.ArgumentParser(description="Probe GPT Image API capabilities for an OpenAI-compatible endpoint.")
    parser.add_argument("--api-key", default="", help="API key. Defaults to config.local.json, GPT_IMAGE_API_KEY, or OPENAI_API_KEY.")
    parser.add_argument("--api-provider", choices=["relay", "openai"], default="", help="Select default base URL and env fallbacks.")
    parser.add_argument("--base-url", default="", help="Override the API base URL.")
    parser.add_argument("--organization", default="", help="Optional OpenAI organization header.")
    parser.add_argument("--project", default="", help="Optional OpenAI project header.")
    parser.add_argument("--timeout", type=int, default=600, help="Request timeout in seconds.")
    parser.add_argument("--models", nargs="+", default=MODELS, help="Models to probe.")
    return parser.parse_args()


def load_config_json():
    config_path = ROOT / "config.local.json"
    if not config_path.exists():
        return {}

    return json.loads(config_path.read_text(encoding="utf-8"))


def resolve_api_provider(cli_provider):
    if cli_provider.strip():
        return cli_provider.strip().lower()

    config_data = load_config_json()
    config_provider = str(config_data.get("api_provider", "")).strip().lower()
    if config_provider:
        return config_provider

    env_provider = os.getenv("GPT_IMAGE_API_PROVIDER", "").strip().lower()
    if env_provider:
        return env_provider

    configured_base_url = str(config_data.get("base_url", "")).strip().rstrip("/")
    if configured_base_url.lower().startswith(OPENAI_BASE_URL.lower()):
        return "openai"

    env_base_url = os.getenv("OPENAI_BASE_URL", "").strip().rstrip("/")
    if env_base_url.lower().startswith(OPENAI_BASE_URL.lower()):
        return "openai"

    if os.getenv("OPENAI_API_KEY", "").strip():
        return "openai"

    return "relay"


def resolve_api_key(cli_key, api_provider):
    if cli_key.strip():
        return cli_key.strip()

    env_key = os.getenv("GPT_IMAGE_API_KEY", "").strip()
    if env_key:
        return env_key

    if api_provider == "openai":
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        if openai_key:
            return openai_key

    config_data = load_config_json()
    config_key = str(config_data.get("api_key", "")).strip()
    if config_key:
        return config_key

    raise ValueError(
        "Missing API key. Pass --api-key, set GPT_IMAGE_API_KEY, set OPENAI_API_KEY for "
        "api_provider=openai, or add api_key to config.local.json."
    )


def resolve_base_url(cli_base_url, api_provider):
    if cli_base_url.strip():
        return cli_base_url.strip().rstrip("/")

    config_data = load_config_json()
    config_base_url = str(config_data.get("base_url", "")).strip()
    if config_base_url:
        return config_base_url.rstrip("/")

    env_base_url = os.getenv("GPT_IMAGE_BASE_URL", "").strip()
    if env_base_url:
        return env_base_url.rstrip("/")

    if api_provider == "openai":
        openai_base_url = os.getenv("OPENAI_BASE_URL", "").strip()
        if openai_base_url:
            return openai_base_url.rstrip("/")
        return OPENAI_BASE_URL

    return DEFAULT_BASE_URL


def resolve_openai_header(cli_value, config_key, *env_keys):
    if cli_value.strip():
        return cli_value.strip()

    config_data = load_config_json()
    config_value = str(config_data.get(config_key, "")).strip()
    if config_value:
        return config_value

    for env_key in env_keys:
        value = os.getenv(env_key, "").strip()
        if value:
            return value

    return ""


def make_test_png_bytes():
    image = Image.new("RGB", (8, 8), color=(220, 220, 220))
    bytes_io = io.BytesIO()
    image.save(bytes_io, format="PNG")
    return bytes_io.getvalue()


def summarize_success(response_payload):
    summary = {"data_len": len(response_payload.get("data", []))}
    if "usage" in response_payload:
        summary["usage"] = response_payload["usage"]
    return summary


def summarize_error(response):
    try:
        payload = response.json()
    except Exception:
        payload = {"error": {"message": response.text}}

    return payload.get("error", payload)


def summarize_exception(exc):
    return {
        "type": exc.__class__.__name__,
        "message": str(exc),
    }


def get_request_id(response):
    return response.headers.get("x-request-id") or response.headers.get("x-aihubmix-request-id")


def run_generate_probe(client, model_name):
    try:
        response = client.post(
            "/images/generations",
            json={
                "model": model_name,
                "prompt": "A simple flat icon of a blue ceramic mug on a white background.",
                "n": 1,
                "size": "1024x1024",
                "quality": "low",
                "background": "auto",
                "output_format": "png",
            },
        )
    except httpx.HTTPError as exc:
        return {
            "status": None,
            "request_id": None,
            "success": False,
            "error": summarize_exception(exc),
        }

    request_id = get_request_id(response)
    if response.status_code != 200:
        return {
            "status": response.status_code,
            "request_id": request_id,
            "success": False,
            "error": summarize_error(response),
        }

    payload = response.json()
    return {
        "status": response.status_code,
        "request_id": request_id,
        "success": True,
        "summary": summarize_success(payload),
    }


def run_edit_probe(client, model_name, image_count):
    png_bytes = make_test_png_bytes()
    data = {
        "model": model_name,
        "prompt": "Turn the object into a green ceramic mug on a white background.",
        "n": "1",
        "size": "1024x1024",
        "quality": "low",
        "background": "auto",
        "output_format": "png",
        "input_fidelity": "low",
    }
    files = [("image[]", (f"input_{index}.png", png_bytes, "image/png")) for index in range(image_count)]
    try:
        response = client.post("/images/edits", data=data, files=files)
    except httpx.HTTPError as exc:
        return {
            "status": None,
            "request_id": None,
            "success": False,
            "error": summarize_exception(exc),
        }

    request_id = get_request_id(response)
    if response.status_code != 200:
        return {
            "status": response.status_code,
            "request_id": request_id,
            "success": False,
            "error": summarize_error(response),
        }

    payload = response.json()
    return {
        "status": response.status_code,
        "request_id": request_id,
        "success": True,
        "summary": summarize_success(payload),
    }


def probe_limit(client, model_name):
    last_success = 0
    first_failure = None
    attempts = []

    for count in DEFAULT_COUNTS:
        result = run_edit_probe(client, model_name, count)
        attempts.append({"count": count, **result})
        if result["success"]:
            last_success = count
            continue

        first_failure = count
        break

    if first_failure is None:
        return {
            "last_success": last_success,
            "first_failure": None,
            "attempts": attempts,
        }

    low = last_success + 1
    high = first_failure - 1
    while low <= high:
        mid = (low + high) // 2
        result = run_edit_probe(client, model_name, mid)
        attempts.append({"count": mid, **result})
        if result["success"]:
            last_success = mid
            low = mid + 1
        else:
            first_failure = mid
            high = mid - 1

    return {
        "last_success": last_success,
        "first_failure": first_failure,
        "attempts": attempts,
    }


def main():
    args = parse_args()
    api_provider = resolve_api_provider(args.api_provider)
    api_key = resolve_api_key(args.api_key, api_provider)
    base_url = resolve_base_url(args.base_url, api_provider)
    organization = resolve_openai_header(args.organization, "openai_organization", "OPENAI_ORGANIZATION")
    project = resolve_openai_header(args.project, "openai_project", "OPENAI_PROJECT_ID", "OPENAI_PROJECT")
    timeout = httpx.Timeout(connect=30.0, read=float(args.timeout), write=60.0, pool=float(args.timeout))
    headers = {"Authorization": f"Bearer {api_key}"}
    if organization:
        headers["OpenAI-Organization"] = organization
    if project:
        headers["OpenAI-Project"] = project

    results = {
        "api_provider": api_provider,
        "base_url": base_url,
        "models": {},
    }

    with httpx.Client(base_url=base_url, headers=headers, timeout=timeout) as client:
        for model_name in args.models:
            generate_result = run_generate_probe(client, model_name)
            edit_result = run_edit_probe(client, model_name, 1)
            limit_result = probe_limit(client, model_name)
            results["models"][model_name] = {
                "generate": generate_result,
                "edit_single": edit_result,
                "edit_limit_probe": limit_result,
            }

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
