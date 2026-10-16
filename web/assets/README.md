# Embedded assets

- `rubik-latin-wght-normal.woff2`: Rubik variable roman, weights 300–900,
  Latin subset, downloaded from Fontsource via jsDelivr. Response identified
  version 5.2.8. Source:
  https://cdn.jsdelivr.net/fontsource/fonts/rubik:vf@5.2.8/latin-wght-normal.woff2
  SHA-256: `691cd1d9b4c0cdf31a1dcf04259c86f92c85e69f6622abab7964d81e36890691`.
- `OFL.txt`: copyright and SIL Open Font License 1.1, from
  https://raw.githubusercontent.com/google/fonts/main/ofl/rubik/OFL.txt.
  Only trailing whitespace is normalized. The build embeds the full license
  with the font in the delivered HTML, including wheels and source distributions.
- The brand image is read directly from the existing repository asset
  `fulcra_mcp/static/icon.png` and embedded unchanged; there is no duplicate source
  file here and no newly drawn official logo.

These files are vendored; the build never downloads assets. Other scripts use
system font fallback. No runtime font or image request is required.
