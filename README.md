# APIshare Image Generation Skill

Generate images through the APIshare image generation gateway at:

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

```bash
python3 scripts/generate_image.py \
  --prompt "A cute dog, clean illustration, no text, no watermark." \
  --output dog.png
```

## Image To Image

This skill still uses the generations endpoint. If you already have a public image URL, attach it:

```bash
python3 scripts/generate_image.py \
  --prompt "Keep the tattoo shape, make it cleaner and sharper." \
  --image-url "https://apishare.l-kx.cn/generated/example.png" \
  --output tattoo-variant.png
```

If the user provides a local image, the skill uploads it to the APIshare gateway first, receives a public URL, then sends that URL with the generations request:

```bash
python3 scripts/generate_image.py \
  --prompt "Turn this tattoo into a minimal blackwork version." \
  --image ./tattoo.png \
  --output tattoo-blackwork.png
```

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

- Missing key: ask the user for their APIshare key and save it in `config/apishare-image-generation.local.json`, or set `IMAGEGEN_API_KEY`.
- `model_not_found`: the API key's group may not have a usable channel for the model.
- `bad_response_status_code`: the gateway reached an upstream, but that upstream returned an error.
- HTML `403 Forbidden`: an upstream nginx/WAF likely blocked the request source IP or network environment.
- Timeout: check gateway upstream timeout, cloud-function timeout, and model-pool health.
