# Social Card Generation (`og-image.jpg`)

This project uses a dedicated social preview image for link embeds (Open Graph / Twitter), separate from the favicon.

## Output file

- `apps/web/public/og-image.jpg` (`1200x630`)

## Prerequisites

- ImageMagick (`magick` for v7, or `convert` for v6)
- `fontconfig` (`fc-match`) for font lookup
- IBM Plex Sans & IBM Plex Mono fonts (e.g. `apt install fonts-ibm-plex`)

## Regenerate

Run from repo root:

```bash
set -euo pipefail

SANS_BOLD="$(fc-match -f '%{file}\n' 'IBM Plex Sans:style=Bold' || true)"
SANS_FONT="$(fc-match -f '%{file}\n' 'IBM Plex Sans:style=Regular' || true)"
MONO_FONT="$(fc-match -f '%{file}\n' 'IBM Plex Mono:style=Bold' || true)"

if [ -z "${SANS_BOLD}" ] || [ -z "${SANS_FONT}" ] || [ -z "${MONO_FONT}" ]; then
  echo "Could not resolve required fonts via fc-match" >&2
  exit 1
fi

magick -size 1200x630 xc:'#09090b' \
  \( -size 1200x630 radial-gradient:'#10b98118-#09090b' -geometry +420+250 \) -compose screen -composite \
  \( -size 1200x630 radial-gradient:'#10b98108-#09090b' -geometry -200-100 \) -compose screen -composite \
  -fill '#10b981' -font "${MONO_FONT}" -pointsize 26 -gravity northwest -annotate +80+78 'bayram.sh' \
  -fill '#10b981' -strokewidth 0 -draw 'line 80,120 1120,120' \
  -fill '#10b981' -draw 'rectangle 80,120 86,440' \
  -fill '#f5f5f5' -font "${SANS_BOLD}" -pointsize 80 -gravity northwest -annotate +108+155 'Bayram Sahin' \
  -fill '#dfdfe3' -font "${SANS_FONT}" -pointsize 46 -gravity northwest -annotate +108+260 'Full-Stack Developer' \
  -fill '#dfdfe3' -font "${SANS_FONT}" -pointsize 46 -gravity northwest -annotate +108+320 '& DevOps Practitioner' \
  -fill '#10b981' -draw 'line 80,540 1120,540' \
  -fill '#aaaab3' -font "${MONO_FONT}" -pointsize 22 -gravity northwest -annotate +80+558 'Software Engineering  ·  DevOps  ·  Open Source' \
  -quality 88 \
  apps/web/public/og-image.jpg
```

## Layout wiring

`apps/web/src/layouts/Layout.astro` references this image through:

- `meta[property="og:image"]`
- `meta[name="twitter:image"]`
