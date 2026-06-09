#!/usr/bin/env python3
import argparse
import base64
import json
import mimetypes
import os
import re
import getpass
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = SKILL_DIR / "config" / "apishare-image-generation.config.json"
LOCAL_CONFIG = SKILL_DIR / "config" / "apishare-image-generation.local.json"
APISHARE_BASE_URL = "https://gateway.l-kx.cn/v1"


def parse_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def parse_kv(items: Optional[list[str]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for item in items or []:
        if "=" not in item:
            raise SystemExit(f"Invalid parameter {item!r}; expected key=value")
        key, value = item.split("=", 1)
        if not key:
            raise SystemExit(f"Invalid parameter {item!r}; key is empty")
        out[key] = parse_value(value)
    return out


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Config JSON is invalid: {path}: {exc}") from exc


def choose(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return default


def normalize_base_url(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    for suffix in ("/images/generations", "/responses"):
        if base_url.endswith(suffix):
            base_url = base_url[: -len(suffix)]
    return base_url


def save_local_config(config: Dict[str, Any]) -> None:
    LOCAL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_CONFIG.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_effective_config(path: Path) -> Dict[str, Any]:
    cfg = load_config(path)
    if path == DEFAULT_CONFIG and LOCAL_CONFIG.exists():
        cfg = {**cfg, **load_config(LOCAL_CONFIG)}
    return cfg


def is_placeholder_key(api_key: Optional[str]) -> bool:
    return not api_key or api_key in {"sk-your-api-key-here", "sk-...", "REPLACE_ME"}


def prompt_for_api_key(cfg: Dict[str, Any]) -> str:
    if not sys.stdin.isatty():
        raise SystemExit(
            "Missing API key for APIshare gateway. Do not stop here: ask the user "
            "for their APIshare API key, then rerun with --api-key <key> --save-api-key "
            "to save it to config/apishare-image-generation.local.json."
        )
    api_key = getpass.getpass("Enter your APIshare API key: ").strip()
    if is_placeholder_key(api_key):
        raise SystemExit("No API key entered.")
    save_local_config({**cfg, "base_url": APISHARE_BASE_URL, "api_key": api_key})
    print(f"Saved API key to {LOCAL_CONFIG}", file=sys.stderr)
    return api_key


def post_json(url: str, api_key: str, payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(format_http_error(exc.code, url, detail)) from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Request failed for {url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"API returned non-JSON response from {url}") from exc


def upload_local_image(base_url: str, api_key: str, image_path: Path, timeout: int) -> str:
    if not image_path.exists() or not image_path.is_file():
        raise SystemExit(f"Image file not found: {image_path}")
    mime = mimetypes.guess_type(image_path.name)[0] or "image/png"
    raw = image_path.read_bytes()
    payload = {
        "filename": image_path.name,
        "content_type": mime,
        "b64_json": base64.b64encode(raw).decode("ascii"),
    }
    response = post_json(f"{base_url}/images/uploads", api_key, payload, timeout)
    url = response.get("url") if isinstance(response, dict) else None
    if not isinstance(url, str) or not url:
        raise SystemExit(f"Image upload did not return a URL: {json.dumps(response, ensure_ascii=False)[:1000]}")
    return url


def format_http_error(status_code: int, url: str, detail: str) -> str:
    message = f"HTTP {status_code} from {url}: {detail}"
    try:
        data = json.loads(detail)
    except json.JSONDecodeError:
        data = None

    error = data.get("error") if isinstance(data, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    text = json.dumps(data, ensure_ascii=False) if data is not None else detail

    hints = []
    if status_code in (401, 403):
        hints.append("Check that the API key is valid and allowed to use this gateway/model.")
    if code == "model_not_found":
        hints.append("The API key's group may not have an available channel for this model.")
    if code == "bad_response_status_code" or "bad_response_status_code" in text:
        hints.append("The gateway reached an upstream, but the upstream returned an error status.")
    if status_code in (502, 503, 504):
        hints.append("Check gateway model-pool routing, upstream health, and image proxy/COS mode.")
    if "<html" in detail.lower() and "403" in detail:
        hints.append("An upstream nginx/WAF returned 403; check source-IP allowlists and provider firewall rules.")
    if hints:
        message += "\nHints:\n- " + "\n- ".join(hints)
    return message


def image_payload(args: argparse.Namespace, cfg: Dict[str, Any], extras: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": choose(args.model, cfg.get("model"), default="gpt-image-2"),
        "prompt": args.prompt,
    }
    for key in ("size", "quality", "output_format", "background", "moderation", "user"):
        value = choose(getattr(args, key), cfg.get(key))
        if value is not None:
            payload[key] = value
    n = choose(args.n, cfg.get("n"))
    if n is not None:
        payload["n"] = int(n)
    if args.image_url:
        payload["image"] = args.image_url
    payload.update(extras)
    return payload


def responses_payload(
    args: argparse.Namespace,
    cfg: Dict[str, Any],
    tool_extras: Dict[str, Any],
    request_extras: Dict[str, Any],
) -> Dict[str, Any]:
    tool: Dict[str, Any] = {"type": "image_generation"}
    image_model = choose(args.image_model, cfg.get("image_model"))
    if image_model is not None:
        tool["model"] = image_model
    for key in ("size", "quality", "output_format", "background", "moderation"):
        value = choose(getattr(args, key), cfg.get(key))
        if value is not None:
            tool[key] = value
    tool.update(tool_extras)
    payload: Dict[str, Any] = {
        "model": choose(args.model, cfg.get("model"), default="gpt-image-2"),
        "input": args.prompt,
        "tools": [tool],
        "store": choose(args.store, cfg.get("store"), default=False),
    }
    max_output_tokens = choose(args.max_output_tokens, cfg.get("max_output_tokens"))
    if max_output_tokens is not None:
        payload["max_output_tokens"] = int(max_output_tokens)
    payload.update(request_extras)
    return payload


ImageResult = Dict[str, str]


def extract_image_api_result(data: Dict[str, Any]) -> ImageResult:
    items = data.get("data")
    if not isinstance(items, list) or not items:
        raise SystemExit(f"No image data found in Image API response: {json.dumps(data)[:1000]}")
    first = items[0]
    if isinstance(first, dict) and isinstance(first.get("b64_json"), str):
        return {"kind": "b64", "data": first["b64_json"]}
    if isinstance(first, dict) and isinstance(first.get("url"), str):
        return {"kind": "url", "data": first["url"]}
    raise SystemExit(f"No b64_json found in Image API response: {json.dumps(first)[:1000]}")


def extract_responses_result(data: Dict[str, Any]) -> ImageResult:
    output = data.get("output")
    if not isinstance(output, list):
        raise SystemExit(f"No output list found in Responses API response: {json.dumps(data)[:1000]}")
    for item in output:
        if isinstance(item, dict) and item.get("type") == "image_generation_call":
            result = item.get("result")
            if isinstance(result, str) and result:
                if result.startswith("http://") or result.startswith("https://"):
                    return {"kind": "url", "data": result}
                return {"kind": "b64", "data": result}
    raise SystemExit(f"No image_generation_call.result found in Responses API response: {json.dumps(output)[:1000]}")


def save_b64_image(b64_data: str, output: Path) -> None:
    try:
        raw = base64.b64decode(b64_data, validate=True)
    except Exception as exc:
        raise SystemExit("Image result is not valid base64") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)


def output_path(args_output: Optional[str], output_format: str) -> Path:
    ext = output_format.lower().replace("jpeg", "jpg")
    out = Path(args_output or f"generated-{int(time.time())}.{ext}")
    if not out.is_absolute():
        out = Path.cwd() / out
    return out


def extension_from_url(url: str) -> Optional[str]:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower().lstrip(".")
    if suffix in {"png", "jpg", "jpeg", "webp", "gif"}:
        return "jpg" if suffix == "jpeg" else suffix
    return None


def extension_from_content_type(content_type: str) -> Optional[str]:
    media_type = content_type.split(";", 1)[0].strip().lower()
    return {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/webp": "webp",
        "image/gif": "gif",
    }.get(media_type)


def with_extension(output: Path, ext: str) -> Path:
    if output.suffix:
        return output
    clean_ext = re.sub(r"[^a-z0-9]", "", ext.lower()) or "png"
    return output.with_suffix(f".{clean_ext}")


def download_image(url: str, output: Path, timeout: int) -> Path:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"Accept": "image/*,*/*"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("content-type", "")
            data = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} while downloading image URL: {detail[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Failed to download image URL: {exc}") from exc

    if not data:
        raise SystemExit("Downloaded image URL returned an empty body")

    ext = extension_from_content_type(content_type) or extension_from_url(url) or "png"
    out = with_extension(output, ext)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return out


def redact_payload(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


def print_diagnostics(base_url: str, api: str, payload: Dict[str, Any], output: Path, timeout: int) -> None:
    diagnostics = {
        "base_url": base_url,
        "api": api,
        "model": payload.get("model"),
        "size": payload.get("size"),
        "quality": payload.get("quality"),
        "output_format": payload.get("output_format"),
        "has_image": bool(payload.get("image")),
        "output": str(output),
        "timeout": timeout,
    }
    print(json.dumps({"diagnostics": diagnostics}, indent=2), file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate images with gpt-image-2 via Image API or Responses API.")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output", default=None, help="Output filename/path. Defaults to generated-<timestamp>.<format> in cwd.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--api", choices=["image", "responses"], default=None)
    parser.add_argument("--base-url", default=None, help="Ignored; this skill is pinned to the APIshare gateway.")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--save-api-key", action="store_true", help="Save --api-key to the local skill config for future runs.")
    parser.add_argument("--model", default=None)
    parser.add_argument("--image-model", default=None, help="Responses API image_generation tool model override.")
    parser.add_argument("--size", default=None)
    parser.add_argument("--quality", default=None)
    parser.add_argument("--output-format", default=None)
    parser.add_argument("--image", default=None, help="Local reference image path. The skill uploads it first and sends its URL to generations.")
    parser.add_argument("--image-url", default=None, help="Reference image URL to attach to the generations request.")
    parser.add_argument("--background", default=None)
    parser.add_argument("--moderation", default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--n", type=int, default=None)
    parser.add_argument("--store", type=parse_value, default=None)
    parser.add_argument("--max-output-tokens", type=int, default=None)
    parser.add_argument("--param", action="append", help="Extra field as key=value. Image API: request field. Responses: image_generation tool field.")
    parser.add_argument("--request-param", action="append", help="Extra top-level Responses request field as key=value.")
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--print-request", action="store_true")
    parser.add_argument("--diagnose", action="store_true", help="Print non-secret request diagnostics before calling the API.")
    args = parser.parse_args()

    config_path = Path(args.config).expanduser()
    cfg = load_effective_config(config_path)
    api = choose(args.api, os.getenv("IMAGEGEN_API"), cfg.get("api"), default="image")
    base_url = normalize_base_url(APISHARE_BASE_URL)
    api_key = choose(args.api_key, os.getenv("IMAGEGEN_API_KEY"), os.getenv("OPENAI_API_KEY"), cfg.get("api_key"))
    if args.save_api_key:
        if is_placeholder_key(args.api_key):
            raise SystemExit("--save-api-key requires --api-key.")
        save_local_config({**cfg, "base_url": APISHARE_BASE_URL, "api_key": args.api_key})
        print(f"Saved API key to {LOCAL_CONFIG}", file=sys.stderr)
        api_key = args.api_key
    if is_placeholder_key(api_key):
        api_key = prompt_for_api_key({**cfg, "base_url": APISHARE_BASE_URL})
    output_format = choose(args.output_format, cfg.get("output_format"), default="png")
    timeout = int(choose(args.timeout, cfg.get("timeout"), default=300))
    extras = parse_kv(args.param)
    request_extras = parse_kv(args.request_param)

    if args.image and args.image_url:
        raise SystemExit("Use either --image or --image-url, not both.")
    if args.image:
        args.image_url = upload_local_image(base_url, api_key, Path(args.image).expanduser(), timeout)

    if api == "image":
        url = f"{base_url}/images/generations"
        payload = image_payload(args, {**cfg, "output_format": output_format}, extras)
    else:
        url = f"{base_url}/responses"
        payload = responses_payload(args, {**cfg, "output_format": output_format}, extras, request_extras)

    if args.print_request:
        print(f"POST {url}", file=sys.stderr)
        print(redact_payload(payload), file=sys.stderr)

    out = output_path(args.output, output_format)
    if args.diagnose:
        print_diagnostics(base_url, api, payload, out, timeout)

    response = post_json(url, api_key, payload, timeout)
    result = extract_image_api_result(response) if api == "image" else extract_responses_result(response)
    source = result["kind"]
    if source == "url":
        out = download_image(result["data"], out, timeout)
    else:
        save_b64_image(result["data"], out)
    mime = mimetypes.guess_type(out.name)[0] or "application/octet-stream"
    print(json.dumps({"ok": True, "api": api, "source": source, "path": str(out), "bytes": out.stat().st_size, "mime": mime}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
