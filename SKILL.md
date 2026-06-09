---
name: "APIshare image generation"
description: "Generate and edit images through the APIshare gateway at https://gateway.l-kx.cn/v1. Uses /v1/images/generations for text-to-image and /v1/images/edits multipart for image-to-image."
---

# APIshare Image Generation

This skill generates images through the APIshare gateway:

```text
https://gateway.l-kx.cn/v1
```

The base URL is pinned. Do not ask users for another gateway URL.

## Configure

Use the user's APIshare API key. If no key is configured, do not end the task as failed. Ask the user for their APIshare API key, then save it to:

```text
/root/.codex/skills/apishare-image-generation/config/apishare-image-generation.local.json
```

In non-interactive Codex runs, save the key by rerunning the script once with:

```bash
--api-key "USER_KEY_HERE" --save-api-key
```

After saving, rerun the original image generation request.

Environment variable option:

```bash
export IMAGEGEN_API_KEY="sk-your-key"
```

Or copy the example config and pass it explicitly:

```bash
cp config/apishare-image-generation.config.example.json config/apishare-image-generation.local.json
```

## Use

Always call the script. Do not call the gateway directly from Codex chat/completion tooling.

```bash
python3 /root/.codex/skills/apishare-image-generation/scripts/generate_image.py \
  --config /root/.codex/skills/apishare-image-generation/config/apishare-image-generation.local.json \
  --api image \
  --prompt "A cute dog, clean illustration, no text, no watermark." \
  --output dog.png
```

The output path is relative to the current working directory.

## Defaults

The example config is:

```text
/root/.codex/skills/apishare-image-generation/config/apishare-image-generation.config.example.json
```

It includes:

- `base_url`: `https://gateway.l-kx.cn/v1` (pinned)
- `api`: `image`
- endpoint: `/v1/images/generations`
- `model`: `gpt-image-2`
- `size`: `1024x1024`
- `quality`: `low`
- `output_format`: `png`
- `timeout`: `300`

## Parameter Passing

Use first-class flags for common API fields:

```bash
--model gpt-image-2
--size 1024x1024
--quality low
--output-format png
```

Use passthrough for gateway/OpenAI-compatible fields:

```bash
--param background=auto
--param moderation=auto
--param user='"local-test"'
```

Use diagnostics without exposing the API key:

```bash
--diagnose
```

## APIshare Notes

The APIshare project code registers both `/v1/images/generations` and `/images/generations`, plus `/v1/images/edits` and `/images/edits`. Keep `base_url` ending in `/v1`, not the full endpoint path.

Use `/v1/images/generations` for text-to-image JSON requests. Use `/v1/images/edits` multipart for image-to-image with an `image` file field, following the APIshare image configuration document. Do not use `/responses`, `/v1/responses`, chat completions, or Codex model traffic for image generation.

The script supports both `b64_json` and URL responses. If a gateway returns a COS/public image URL, the script downloads it locally.

## Image To Image

For image-to-image, use the edits endpoint through the script. If the user references a previous generated image URL, pass it with:

```bash
--image-url "https://apishare.l-kx.cn/generated/example.png"
```

The script downloads the URL first, then sends it as multipart `image=@reference.png`.

If the user provides a local image path, pass it with:

```bash
--image /absolute/path/to/reference.png
```

The script sends local images as multipart `image=@file` to `/v1/images/edits`, matching the upstream document.

For every image edit, plan the prompt generically instead of adding special-case color or object rules. State the requested change clearly, require a visible edit, preserve all unmentioned elements, and prevent returning the original image unchanged. The script applies this prompt planning automatically for `--image` and `--image-url`.

If `/v1/images/generations` returns `502 Bad Gateway`, the script reached the gateway but the gateway/upstream path failed or timed out. If it returns `model_not_found`, the API key's group lacks a usable channel for the configured model. If it returns HTML `403 Forbidden`, an upstream nginx/WAF may be blocking the gateway or cloud-function source IP.
