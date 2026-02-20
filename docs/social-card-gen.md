# Social Card Generation (`og-image.jpg`)

This project uses a dedicated social preview image for link embeds (Open Graph / Twitter), separate from the favicon.

## Output file

- `apps/web/public/og-image.jpg` (`1200x630`)

## Prerequisites

- Python 3 with Pillow (`pip install pillow`)
- IBM Plex Sans & IBM Plex Mono fonts (e.g. `apt install fonts-ibm-plex`)
- `fontconfig` (`fc-match`) for font lookup

## Regenerate

Run from repo root:

```bash
python3 - << 'EOF'
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import subprocess, sys

def fc(family, style):
    out = subprocess.check_output(
        ['fc-match', '-f', '%{file}\\n', f'{family}:style={style}'],
        text=True
    ).strip()
    if not out:
        sys.exit(f'Font not found: {family} {style}')
    return out

SANS_BOLD = fc('IBM Plex Sans', 'Bold')
SANS_SB   = fc('IBM Plex Sans', 'SemiBold')
SANS      = fc('IBM Plex Sans', 'Regular')
MONO_SB   = fc('IBM Plex Mono', 'SemiBold')
MONO      = fc('IBM Plex Mono', 'Regular')

W, H = 1200, 630
BG         = (245, 245, 244)
SURFACE    = (255, 255, 255)
EMERALD    = (16, 185, 129)
TEXT_PRI   = (23, 23, 23)
TEXT_BODY  = (64, 64, 64)
TEXT_MUTED = (115, 115, 115)
BORDER_SUB = (229, 229, 229)

img = Image.new('RGBA', (W, H), BG + (255,))

# Radial emerald glow at top-left
glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
ImageDraw.Draw(glow).ellipse([-280, -280, 680, 680], fill=EMERALD + (65,))
glow = glow.filter(ImageFilter.GaussianBlur(radius=130))
img  = Image.alpha_composite(img, glow)

# 40px grid background (site signature feature)
grid = Image.new('RGBA', (W, H), (0, 0, 0, 0))
gd   = ImageDraw.Draw(grid)
for x in range(0, W + 1, 40):
    gd.line([(x, 0), (x, H)], fill=(0, 0, 0, 14))
for y in range(0, H + 1, 40):
    gd.line([(0, y), (W, y)], fill=(0, 0, 0, 14))
img = Image.alpha_composite(img, grid)

# Nav bar
NAV_H = 56
nav = Image.new('RGBA', (W, NAV_H), SURFACE + (220,))
ImageDraw.Draw(nav).line([(0, NAV_H - 1), (W, NAV_H - 1)], fill=BORDER_SUB + (255,), width=1)
img.paste(nav, (0, 0))

draw = ImageDraw.Draw(img)
draw.text((40, 16),  'bayram.sh',                fill=EMERALD,    font=ImageFont.truetype(MONO_SB,   22))
draw.rectangle([80, 96, 84, 420],                fill=EMERALD)
draw.text((104, 108), 'Bayram Şahin',            fill=TEXT_PRI,   font=ImageFont.truetype(SANS_BOLD, 82))
draw.text((104, 222), 'Full-Stack Developer',    fill=TEXT_BODY,  font=ImageFont.truetype(SANS_SB,   44))
draw.text((104, 278), '& DevOps Practitioner',  fill=TEXT_BODY,  font=ImageFont.truetype(SANS_SB,   44))

# Knowledge-graph nodes (decorative)
nodes = [
    (960, 360, 18, (16, 185, 129),  30),
    (870, 460, 13, (96, 165, 250),  20),
    (1060, 290, 12, (96, 165, 250), 18),
    (1100, 440, 10, (192, 132, 252), 16),
    (820,  320,  9, (115, 115, 115), 0),
    (990,  500,  8, (115, 115, 115), 0),
    (1130, 360,  8, (115, 115, 115), 0),
    (900,  540,  7, (192, 132, 252),12),
    (1050, 200,  7, (115, 115, 115), 0),
    (1140, 510,  7, (115, 115, 115), 0),
]
edges = [(0,1),(0,2),(0,3),(0,4),(0,5),(1,4),(2,6),(3,5),(7,1),(8,2),(9,3)]

el = Image.new('RGBA', (W, H), (0, 0, 0, 0))
for a, b in edges:
    ImageDraw.Draw(el).line([(nodes[a][0], nodes[a][1]), (nodes[b][0], nodes[b][1])],
                            fill=(0, 0, 0, 40), width=1)
img = Image.alpha_composite(img, el)

for cx, cy, r, col, gr in nodes:
    if gr:
        g2 = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(g2).ellipse([cx-gr, cy-gr, cx+gr, cy+gr], fill=col+(55,))
        img = Image.alpha_composite(img, g2.filter(ImageFilter.GaussianBlur(10)))

nl = Image.new('RGBA', (W, H), (0, 0, 0, 0))
for cx, cy, r, col, _ in nodes:
    ImageDraw.Draw(nl).ellipse([cx-r, cy-r, cx+r, cy+r], fill=col+(220,))
img = Image.alpha_composite(img, nl)

draw = ImageDraw.Draw(img)
draw.line([(80, 540), (1120, 540)], fill=BORDER_SUB, width=1)
draw.text((80, 556), 'Software Engineering  ·  DevOps  ·  Open Source',
          fill=TEXT_MUTED, font=ImageFont.truetype(MONO, 22))

img.convert('RGB').save('apps/web/public/og-image.jpg', quality=88, optimize=True)
print('Saved apps/web/public/og-image.jpg')
EOF
```

## Layout wiring

`apps/web/src/layouts/Layout.astro` references this image through:

- `meta[property="og:image"]`
- `meta[name="twitter:image"]`
