# APIshare Image Generation Skill

Generate and edit images through the APIshare image generation gateway at:

```text
https://gateway.l-kx.cn/v1
```

This skill is pinned to that gateway. Users only need to provide their API key.

This skill supports both common response shapes:

- `data[0].b64_json`: decodes and saves the image locally.
- `data[0].url`: downloads the image URL and saves it locally. This is useful when a gateway uses cloud storage/COS to avoid returning large base64 payloads.

## Setup

Use environment variables:

```bash
export IMAGEGEN_API_KEY="sk-your-key"
```

Or let the script prompt for the key in an interactive terminal. It saves the key to:

```text
config/apishare-image-generation.local.json
```

You can also copy the example config:

```bash
cp config/apishare-image-generation.config.example.json config/apishare-image-generation.local.json
```

For non-interactive agents, save a key with:

```bash
python3 scripts/generate_image.py \
  --prompt "key setup" \
  --api-key "sk-your-key" \
  --save-api-key \
  --output setup.png
```

The request will then use the saved key on future runs.

Then pass it explicitly:

```bash
python3 scripts/generate_image.py \
  --config config/apishare-image-generation.local.json \
  --prompt "A cute dog, clean illustration, no text, no watermark." \
  --output dog.png
```

## Usage

Always call `scripts/generate_image.py`; do not send image requests through `/responses` or a Codex chat/completion request.

```bash
python3 scripts/generate_image.py \
  --prompt "A cute dog, clean illustration, no text, no watermark." \
  --output dog.png
```

## Image To Image

This skill follows the APIshare image configuration document: text-to-image uses `/v1/images/generations`; image-to-image uses `/v1/images/edits` with multipart `image=@file`.

If you already have a public image URL, attach it:

```bash
python3 scripts/generate_image.py \
  --prompt "Keep the tattoo shape, make it cleaner and sharper." \
  --image-url "https://apishare.l-kx.cn/generated/example.png" \
  --output tattoo-variant.png
```

The script downloads the URL first, then sends it to `/v1/images/edits` as multipart image data.

If the user provides a local image, the skill sends it directly to `/v1/images/edits` as multipart image data:

```bash
python3 scripts/generate_image.py \
  --prompt "Turn this tattoo into a minimal blackwork version." \
  --image ./tattoo.png \
  --output tattoo-blackwork.png
```

For image edits, the script automatically wraps the user's prompt with general editing guidance: user-requested changes have the highest priority and must be visible; unmentioned elements should stay stable; unrelated additions are avoided; and the original image must not be returned unchanged. This is intentionally generic rather than a special case for one color, object, or style.

Useful options:

```bash
--api-key sk-your-key
--save-api-key
--model gpt-image-2
--size 1024x1024
--quality low
--output-format png
--image ./reference.png
--image-url https://apishare.l-kx.cn/generated/reference.png
--timeout 300
--diagnose
```

Pass gateway-specific fields:

```bash
--param background=auto
--param moderation=auto
--param user='"local-test"'
```

## Troubleshooting

- `503 system cpu overloaded` from `/responses`: this is not the image script path. The agent or client is sending Codex/model traffic to the gateway; run this skill script instead so it uses `/v1/images/generations`.
- Missing key: ask the user for their APIshare key and save it in `config/apishare-image-generation.local.json`, or set `IMAGEGEN_API_KEY`.
- `model_not_found`: the API key's group may not have a usable channel for the model.
- `bad_response_status_code`: the gateway reached an upstream, but that upstream returned an error.
- HTML `403 Forbidden`: an upstream nginx/WAF likely blocked the request source IP or network environment.
- Timeout: check gateway upstream timeout, cloud-function timeout, and model-pool health.
