# ComfyUI-GPT-image

`ComfyUI-GPT-image` 是一个面向 AIHubMix / OpenAI 兼容图片接口的 ComfyUI 自定义节点包，当前提供两个节点：

- `ComfyUI-GPT-image Generate`
- `ComfyUI-GPT-image Edit`

当前版本只覆盖这两类能力：

- 文生图
- 图生图
- 多图参考输入

当前不支持：

- mask / inpainting
- variations
- Responses API

## 模型列表

节点下拉列表只保留两个模型：

- `gpt-image-2`
- `gpt-image-1.5`

如果中转站后续有别名或灰度模型，可以通过 `model_override` 临时覆盖实际请求的模型名。

## 安装

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/your-name/ComfyUI-GPT-image.git
cd ComfyUI-GPT-image
python -m pip install -r requirements.txt
```

## 配置

推荐在仓库根目录创建 `config.local.json`，可以先复制 `config.example.json`：

```json
{
  "api_key": "",
  "request_timeout": 600,
  "base_url": "https://aihubmix.com/v1"
}
```

配置优先级：

1. `config.local.json`
2. 环境变量 `GPT_IMAGE_API_KEY` / `GPT_IMAGE_BASE_URL`
3. 默认值

默认值：

- `base_url`: `https://aihubmix.com/v1`
- `request_timeout`: `600`

`gpt-image-2` 在 2026-04-23 的 AIHubMix relay 实测中响应明显慢于 `gpt-image-1.5`，默认超时建议不要低于 `600` 秒。

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

### size 行为

- `gpt-image-1.5`
  - 只支持 `auto`、`1024x1024`、`1024x1536`、`1536x1024`
- `gpt-image-2`
  - 支持 `auto`
  - 也支持自定义 `WIDTHxHEIGHT`
  - 当前 relay 实测通过的示例包括 `2048x1152`、`3840x2160`、`832x1472`

`gpt-image-2` 自定义尺寸需要满足这些约束：

- 最大边不超过 `3840`
- 宽高都必须是 `16` 的倍数
- 长边 / 短边不超过 `3:1`
- 总像素数在 `655360` 到 `8294400` 之间

`Edit` 节点里如果把 `size` 设成 `auto`：

- `gpt-image-2` 会根据输入图宽高，自动算出最接近输入比例的合法尺寸
- `gpt-image-1.5` 会在 `1024x1024`、`1024x1536`、`1536x1024` 里选最接近输入比例的一档

## 接口行为

- `Generate` 使用 `POST /images/generations`
- `Edit` 使用 `POST /images/edits`
- 多图编辑请求会按 `image[]` 字段发送，而不是重复 `image`
- 节点输出：
  - `image`
  - `response_json`

`response_json` 会保留调试所需的返回结构，但会把 `b64_json` 替换成占位文本，避免输出超大 base64。

## 手动 Probe

仓库内置了一个 relay capability probe 脚本：

```bash
python scripts/probe_aihubmix_capabilities.py --api-key YOUR_KEY
```

脚本会为每个模型执行：

- 一次文生图验证
- 一次单图图生图验证
- 一次多图上限探测

上限探测策略固定为：

1. 依次测试 `1 / 4 / 8 / 16 / 24`
2. 出现失败后，在最后成功值和首次失败值之间二分

## 已验证结果

以下结果用于记录当前 relay 的手动验证结论，会随着脚本复测更新：

- 验证日期：`2026-04-23`
- Relay：`https://aihubmix.com/v1`
- 测试条件：`size=1024x1024`、`quality=low`、`background=auto`、`output_format=png`
- `gpt-image-1.5`
  - 文生图：成功，HTTP `200`
  - 单图图生图：成功，HTTP `200`
  - 多图输入上限探测：`1 / 4 / 8 / 16 / 24` 全部成功
  - 当前已知结论：`last_success = 24`，`first_failure = null`
- `gpt-image-2`
  - 文生图：成功，HTTP `200`
  - 单图图生图：成功，HTTP `200`
  - 多图输入上限探测：`1 / 4 / 8 / 16 / 24` 全部成功
  - 当前已知结论：`last_success = 24`，`first_failure = null`
- 注意：这组结果只能证明 relay 当前“至少支持 24 张输入图”，并不代表 24 是真实上限。

## 测试

```bash
python -m unittest discover -s tests -v
```
