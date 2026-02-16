# Favicon Generation (`B$`, IBM Plex Mono)

This project uses a generated favicon set for `apps/web` based on `B$` in IBM Plex Mono.

## Output files

The generation flow writes these files to `apps/web/public/`:

- `favicon.svg`
- `favicon.ico`
- `favicon-16x16.png`
- `favicon-32x32.png`
- `favicon-512.png`
- `apple-touch-icon.png`

## Prerequisites

- `curl`
- ImageMagick (`magick`)

## Regenerate

Run from the repo root:

```bash
set -euo pipefail

mkdir -p /tmp/ibm-plex-mono-font apps/web/public
curl -fsSL \
  https://github.com/google/fonts/raw/main/ofl/ibmplexmono/IBMPlexMono-Bold.ttf \
  -o /tmp/ibm-plex-mono-font/IBMPlexMono-Bold.ttf

cat > apps/web/public/favicon.svg <<'SVG'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="B$ favicon">
  <rect width="64" height="64" rx="12" fill="#0f172a" />
  <text
    x="32"
    y="35"
    text-anchor="middle"
    dominant-baseline="middle"
    font-family="'IBM Plex Mono', 'SFMono-Regular', Menlo, Monaco, Consolas, 'Liberation Mono', monospace"
    font-size="26"
    font-weight="700"
    fill="#f8fafc"
    letter-spacing="-1"
  >B$</text>
</svg>
SVG

magick -size 512x512 xc:none \
  -fill '#0f172a' -draw 'roundrectangle 0,0 511,511 96,96' \
  -font /tmp/ibm-plex-mono-font/IBMPlexMono-Bold.ttf \
  -fill '#f8fafc' -gravity center -pointsize 230 -kerning -6 -annotate +0+6 'B$' \
  apps/web/public/favicon-512.png

magick apps/web/public/favicon-512.png -resize 180x180 apps/web/public/apple-touch-icon.png
magick apps/web/public/favicon-512.png -resize 32x32 apps/web/public/favicon-32x32.png
magick apps/web/public/favicon-512.png -resize 16x16 apps/web/public/favicon-16x16.png
magick apps/web/public/favicon-16x16.png apps/web/public/favicon-32x32.png apps/web/public/favicon.ico
```

## Layout wiring

`apps/web/src/layouts/Layout.astro` contains the corresponding icon tags:

- `rel="icon"` for SVG and PNG sizes
- `rel="shortcut icon"` for `.ico`
- `rel="apple-touch-icon"` for iOS home screen icon
