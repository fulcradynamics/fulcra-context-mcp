# Menu icons

`menu-light.svg` (black) and `menu-dark.svg` (white) are transparent navigation
variants of [Fulcra's official white vector logo](https://cdn.prod.website-files.com/660cca47b2504b903f5b91f0/67f853c9d6079e37d54b34a4_logo_h_fulcra_white.svg).
The hexagon and spiral paths and stroke width are unchanged; the wordmark is
omitted and the square viewBox adds padding. There is no background shape.

[MCP Icon.theme](https://modelcontextprotocol.io/specification/2025-11-25/schema#icon)
names the host background, not the glyph color. The contact tools advertise both
variants because [OpenAI entrypoints](https://github.com/openai/mcp-extensions/blob/main/docs/spec.md#entrypoint-icons)
prefer tool icons over server or registered-app branding.

`icon.png` remains the full-color server/listing and in-app asset. The plugin's
logo and composer icon are separate branding surfaces and remain unchanged.
The app itself remains dark-only. Native host theme selection requires separate
acceptance after deployment and refreshed tool discovery.
