# Social Card Generation (`og-image.jpg`)

This project uses a dedicated social preview image for link embeds (Open Graph / Twitter), separate from the favicon.

## Output file

- `apps/web/public/og-image.jpg` (`1200x630`)

## Prerequisites

- ImageMagick (`magick`)
- `fontconfig` (`fc-match`) for font lookup

## Regenerate

Run from repo root:

```bash
set -euo pipefail

SANS_FONT="$(fc-match -f '%{file}\n' 'Fira Sans:style=Bold' || true)"
MONO_FONT="$(fc-match -f '%{file}\n' 'JetBrains Mono:style=Bold' || true)"

if [ -z "${SANS_FONT}" ] || [ -z "${MONO_FONT}" ]; then
  echo "Could not resolve required fonts via fc-match" >&2
  exit 1
fi

magick -size 1200x630 xc:'#0a1224' \
  \( -size 1200x630 radial-gradient:'#1d4ed8-#0a1224' \) -compose screen -composite \
  -fill '#22d3ee33' -draw 'circle 980,120 980,340' \
  -fill '#38bdf833' -draw 'circle 200,560 200,760' \
  -stroke '#38bdf8' -strokewidth 3 -fill none -draw 'roundrectangle 82,84 1120,546 26,26' \
  -strokewidth 0 \
  -fill '#e2e8f0' -font "${SANS_FONT}" -pointsize 58 -gravity northwest -annotate +86+130 'Bayram Sahin' \
  -fill '#f8fafc' -font "${SANS_FONT}" -pointsize 84 -gravity northwest -annotate +86+225 'Full-Stack Developer' \
  -fill '#f8fafc' -font "${SANS_FONT}" -pointsize 84 -gravity northwest -annotate +86+318 '& DevOps Practitioner' \
  -fill '#94a3b8' -font "${MONO_FONT}" -pointsize 36 -gravity northwest -annotate +86+430 'Projects | Writing | Lyrics | Systems' \
  -quality 88 \
  apps/web/public/og-image.jpg
```

## Layout wiring

`apps/web/src/layouts/Layout.astro` references this image through:

- `meta[property="og:image"]`
- `meta[name="twitter:image"]`
