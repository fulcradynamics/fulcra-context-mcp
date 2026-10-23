# Menu icon

`menu-icon.svg` is the transparent navigation variant of [Fulcra's official white vector logo](https://cdn.prod.website-files.com/660cca47b2504b903f5b91f0/67f853c9d6079e37d54b34a4_logo_h_fulcra_white.svg).
The hexagon and spiral paths and stroke width are unchanged; the wordmark is
omitted and there is no background shape. It draws in `currentColor`, so the
host picks the glyph color.

The contact tools embed it as a data URI tool icon because [OpenAI entrypoints](https://github.com/openai/mcp-extensions/blob/main/docs/spec.md#entrypoint-icons)
prefer tool icons over server or registered-app branding.

`icon.png` remains the full-color server/listing and in-app asset. The plugin's
logo and composer icon are separate branding surfaces. The app itself remains
dark-only.
