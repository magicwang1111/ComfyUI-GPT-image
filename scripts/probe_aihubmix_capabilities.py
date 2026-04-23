import argparse
import io
import json
import sys
from pathlib import Path

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_BASE_URL = "https://aihubmix.com/v1"
MODELS = ["gpt-image-2", "gpt-image-1.5"]

DEFAULT_COUNTS = [1, 4, 8, 16, 24]


def parse_args():
    parser = argparse.ArgumentParser(description="Probe AIHubMix GPT Image relay capabilities.")
    parser.add_argument("--api-key", default="", help="Relay API key. Defaults to GPT_IMAGE_API_KEY or config.local.json.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Relay base URL.")
    parser.add_argument("--timeout", type=int, default=600, help="Request timeout in seconds.")
    parser.add_argument("--models", nargs="+", default=MODELS, help="Models to probe.")
    return parser.parse_args()


def load_config_json():
    config_path = ROOT / "config.local.json"
    if not config_path.exists():
        return {}

    return json.loads(config_path.read_text(encoding="utf-8"))


def resolve_api_key(cli_key):
    if cli_key.strip():
        return cli_key.strip()

    import os

    env_key = os.getenv("GPT_IMAGE_API_KEY", "").strip()

    if env_key:
        return env_key

    config_data = load_config_json()
    config_key = str(config_data.get("api_key", "")).strip()
    if config_key:
        return config_key

    raise ValueError("Missing API key. Pass --api-key, set GPT_IMAGE_API_KEY, or add api_key to config.local.json.")


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

    request_id = response.headers.get("x-aihubmix-request-id")
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

    request_id = response.headers.get("x-aihubmix-request-id")
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
    api_key = resolve_api_key(args.api_key)
    timeout = httpx.Timeout(connect=30.0, read=float(args.timeout), write=60.0, pool=float(args.timeout))
    headers = {"Authorization": f"Bearer {api_key}"}

    results = {
        "base_url": args.base_url.rstrip("/"),
        "models": {},
    }

    with httpx.Client(base_url=args.base_url.rstrip("/"), headers=headers, timeout=timeout) as client:
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
