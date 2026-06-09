# APIshare Image Routing

This skill is project-specific for `/www/wwwroot/api-gateway-reseller`.

The gateway proxy registers image generation routes in the API project:

- `/v1/images/generations`
- `/images/generations`

The default public endpoint for this skill is:

```text
https://gateway.l-kx.cn/v1/images/generations
```

Use the bundled script with `--api image`; it appends `/images/generations` to `base_url`.

The project also bridges Responses API `image_generation` tool calls to `/v1/images/generations`, but this skill should prefer the direct image generation endpoint unless the user explicitly asks to test Responses bridging.
