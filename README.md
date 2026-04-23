# ComfyUI-GPT-image

ComfyUI custom nodes for the OpenAI GPT Image API and OpenAI-compatible relay endpoints.

English README. For Chinese documentation, see [README.zh-CN.md](./README.zh-CN.md).

## Nodes

- `ComfyUI-GPT-image Generate`
- `ComfyUI-GPT-image Edit`

## Current scope

Supported:

- Text-to-image
- Image-to-image
- Multi-image reference input

Not supported yet:

- Mask / inpainting
- Variations
- Responses API workflows

## API compatibility

This plugin supports both:

- OpenAI official API
- OpenAI-compatible relay endpoints such as AIHubMix

Both paths use the same Image API routes:

- `POST /v1/images/generations`
- `POST /v1/images/edits`

## Models exposed in the node UI

- `gpt-image-2`
- `gpt-image-1.5`

If your relay uses a different model alias, use `model_override` to send the actual model name.

## Installation

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/magicwang1111/ComfyUI-GPT-image.git
cd ComfyUI-GPT-image
python -m pip install -r requirements.txt
```

## Configuration

Create `config.local.json` in the repo root. You can copy `config.example.json` first.

```json
{
  "api_key": "",
  "api_provider": "relay",
  "request_timeout": 600,
  "base_url": "https://aihubmix.com/v1",
  "openai_organization": "",
  "openai_project": ""
}
```

### Config fields

- `api_key`: API key for either OpenAI or a relay.
- `api_provider`: `relay` or `openai`.
- `request_timeout`: Timeout in seconds.
- `base_url`: API root URL. If omitted, a default is chosen from `api_provider`.
- `openai_organization`: Optional `OpenAI-Organization` header.
- `openai_project`: Optional `OpenAI-Project` header.

### Default base URLs

- `api_provider=relay`: `https://aihubmix.com/v1`
- `api_provider=openai`: `https://api.openai.com/v1`

### Environment variables

Resolution order:

1. `config.local.json`
2. Environment variables
3. Built-in defaults

Supported environment variables:

- `GPT_IMAGE_API_KEY`
- `GPT_IMAGE_BASE_URL`
- `GPT_IMAGE_API_PROVIDER`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_ORGANIZATION`
- `OPENAI_PROJECT_ID`
- `OPENAI_PROJECT`

### OpenAI official API example

```json
{
  "api_key": "sk-...",
  "api_provider": "openai",
  "request_timeout": 600,
  "base_url": "https://api.openai.com/v1",
  "openai_organization": "",
  "openai_project": ""
}
```

Or use environment variables:

```bash
set OPENAI_API_KEY=sk-...
set GPT_IMAGE_API_PROVIDER=openai
```

## Node parameters

### Generate

- `prompt`
- `model`
- `n`
- `size`
- `quality`
- `background`
- `output_format`
- `model_override`

### Edit

- `prompt`
- `images`
- `model`
- `n`
- `size`
- `quality`
- `background`
- `output_format`
- `input_fidelity`
- `model_override`

## Size behavior

`size` is a dropdown preset:

- `auto`
- `1K`
- `2K`
- `4K`

The node maps these presets to actual API `size` values.

### `gpt-image-1.5`

Supports:

- `auto`
- `1K`

It resolves to the nearest ratio among:

- `1024x1024`
- `1024x1536`
- `1536x1024`

### `gpt-image-2`

Supports:

- `auto`
- `1K`
- `2K`
- `4K`

Preset mappings:

- `1K`: `1024x1024`, `1024x1536`, `1536x1024`
- `2K`: `2048x2048`, `1152x2048`, `2048x1152`
- `4K`: `2880x2880`, `2160x3840`, `3840x2160`

For `Edit`, the node chooses the closest preset size for the input image aspect ratio.

For `auto` on `gpt-image-2`, the node first picks the size tier from the input long edge:

- `<= 1536` -> `1K`
- `<= 2048` -> `2K`
- otherwise -> `4K`

Then it maps to the closest legal size inside that tier.

For `Generate` with no input image:

- `auto` is still passed through to the API
- `1K`, `2K`, and `4K` default to the square size in each tier

## Request behavior

- `Generate` uses `POST /images/generations`
- `Edit` uses `POST /images/edits`
- Multi-image edits are sent as `image[]`
- Node outputs:
  - `image`
  - `response_json`

`response_json` keeps the response structure for debugging, but replaces `b64_json` with a placeholder so logs do not explode in size.

## Capability probe

The repo includes a probe script for either OpenAI or relay endpoints:

```bash
python scripts/probe_aihubmix_capabilities.py --api-provider openai
python scripts/probe_aihubmix_capabilities.py --api-provider relay --base-url https://aihubmix.com/v1
```

It checks:

- One text-to-image request
- One single-image edit request
- Multi-image input limit probing

Extra options:

- `--api-key`
- `--api-provider`
- `--base-url`
- `--organization`
- `--project`
- `--timeout`
- `--models`

## Verified relay notes

Manual relay verification on `2026-04-23` against `https://aihubmix.com/v1`:

### `gpt-image-1.5`

- Generate: HTTP `200`
- Single-image edit: HTTP `200`
- Multi-image probe: `1 / 4 / 8 / 16 / 24` all succeeded

### `gpt-image-2`

- Generate: HTTP `200`
- Single-image edit: HTTP `200`
- Multi-image probe: `1 / 4 / 8 / 16 / 24` all succeeded

This only proves the relay supported at least 24 input images at that time. It does not prove 24 is the hard limit.

## Tests

```bash
python -m unittest discover -s tests -v
```
