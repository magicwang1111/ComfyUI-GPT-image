# ComfyUI-GPT-image

面向 OpenAI GPT Image API 和 OpenAI 兼容中转站的 ComfyUI 自定义节点。

英文文档请见 [README.md](./README.md)。

## 节点

- `ComfyUI-GPT-image Generate`
- `ComfyUI-GPT-image Edit`

## 当前能力范围

已支持：

- 文生图
- 图生图
- 多图参考输入

暂不支持：

- mask / inpainting
- variations
- Responses API 工作流

## 接口兼容性

当前同时支持：

- OpenAI 官方 API
- OpenAI 兼容中转站，例如 AIHubMix

两种接入方式都使用同一套图片接口：

- `POST /v1/images/generations`
- `POST /v1/images/edits`

## 节点内置模型列表

- `gpt-image-2`
- `gpt-image-1.5`

如果中转站还有别名模型，可以用 `model_override` 覆盖实际请求模型名。

## 安装

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/magicwang1111/ComfyUI-GPT-image.git
cd ComfyUI-GPT-image
python -m pip install -r requirements.txt
```

## 配置

推荐在仓库根目录创建 `config.local.json`，可以先复制 `config.example.json`。

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

### 配置项说明

- `api_key`：官方 API 或中转站的 key。
- `api_provider`：`relay` 或 `openai`。
- `request_timeout`：请求超时秒数。
- `base_url`：API 根地址。不填时会根据 `api_provider` 自动补默认值。
- `openai_organization`：可选，对应 `OpenAI-Organization` 请求头。
- `openai_project`：可选，对应 `OpenAI-Project` 请求头。

### 默认 base URL

- `api_provider=relay`：`https://aihubmix.com/v1`
- `api_provider=openai`：`https://api.openai.com/v1`

### 环境变量

运行时优先级：

1. `config.local.json`
2. 环境变量
3. 内置默认值

支持的环境变量：

- `GPT_IMAGE_API_KEY`
- `GPT_IMAGE_BASE_URL`
- `GPT_IMAGE_API_PROVIDER`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_ORGANIZATION`
- `OPENAI_PROJECT_ID`
- `OPENAI_PROJECT`

### OpenAI 官方 API 示例

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

或者直接设环境变量：

```bash
set OPENAI_API_KEY=sk-...
set GPT_IMAGE_API_PROVIDER=openai
```

## 节点参数

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

## size 行为

`size` 现在是下拉预设：

- `auto`
- `1K`
- `2K`
- `4K`

节点会把这些预设映射成真实传给 API 的 `size`。

### `gpt-image-1.5`

支持：

- `auto`
- `1K`

实际会在以下三档里选最接近输入图比例的一档：

- `1024x1024`
- `1024x1536`
- `1536x1024`

### `gpt-image-2`

支持：

- `auto`
- `1K`
- `2K`
- `4K`

预设映射如下：

- `1K`：`1024x1024`、`1024x1536`、`1536x1024`
- `2K`：`2048x2048`、`1152x2048`、`2048x1152`
- `4K`：`2880x2880`、`2160x3840`、`3840x2160`

在 `Edit` 节点里，节点会根据输入图比例选最接近的一档。

对于 `gpt-image-2 + auto`，会先根据输入图长边决定档位：

- `<= 1536` -> `1K`
- `<= 2048` -> `2K`
- 其他 -> `4K`

再在该档位里选最接近比例的合法尺寸。

对于没有输入图的 `Generate`：

- `auto` 仍然交给 API 自己决定
- `1K`、`2K`、`4K` 默认使用各自档位的方图尺寸

## 请求行为

- `Generate` 使用 `POST /images/generations`
- `Edit` 使用 `POST /images/edits`
- 多图编辑按 `image[]` 发送
- 节点输出：
  - `image`
  - `response_json`

`response_json` 会保留调试结构，但会把 `b64_json` 替换成占位文本，避免日志过大。

## Capability Probe

仓库内置 probe 脚本，可用于官方 API 或中转站：

```bash
python scripts/probe_aihubmix_capabilities.py --api-provider openai
python scripts/probe_aihubmix_capabilities.py --api-provider relay --base-url https://aihubmix.com/v1
```

会检查：

- 一次文生图请求
- 一次单图编辑请求
- 多图输入上限探测

可选参数：

- `--api-key`
- `--api-provider`
- `--base-url`
- `--organization`
- `--project`
- `--timeout`
- `--models`

## 已验证的 relay 结果

`2026-04-23` 在 `https://aihubmix.com/v1` 做过手动验证：

### `gpt-image-1.5`

- 文生图：HTTP `200`
- 单图图生图：HTTP `200`
- 多图探测：`1 / 4 / 8 / 16 / 24` 全部成功

### `gpt-image-2`

- 文生图：HTTP `200`
- 单图图生图：HTTP `200`
- 多图探测：`1 / 4 / 8 / 16 / 24` 全部成功

这只能说明当时 relay 至少支持 24 张输入图，不代表 24 就是硬上限。

## 测试

```bash
python -m unittest discover -s tests -v
```
