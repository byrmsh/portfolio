# Social Card Generation (`og-image.jpg`)

This project uses a dedicated social preview image for link embeds (Open Graph / Twitter), separate from the favicon.

## Output file

- `apps/web/public/og-image.jpg` (`1200x630`)

## Prerequisites

- Python 3 with Pillow (`pip install pillow`)
- IBM Plex Sans & IBM Plex Mono fonts (e.g. `apt install fonts-ibm-plex` on Debian/Ubuntu)

## Regenerate

Run from repo root:

```bash
python3 - << 'EOF'
import os, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1200, 630

# Debian/Ubuntu default paths — adjust if your distro installs fonts elsewhere
# (use `fc-match -f '%{file}\n' 'IBM Plex Sans:style=Bold'` to find the correct path)
SANS_BOLD  = '/usr/share/fonts/truetype/ibm-plex/IBMPlexSans-Bold.ttf'
SANS_LIGHT = '/usr/share/fonts/truetype/ibm-plex/IBMPlexSans-Light.ttf'
MONO       = '/usr/share/fonts/truetype/ibm-plex/IBMPlexMono-Regular.ttf'
MONO_BOLD  = '/usr/share/fonts/truetype/ibm-plex/IBMPlexMono-Bold.ttf'

for path in (SANS_BOLD, SANS_LIGHT, MONO, MONO_BOLD):
    if not os.path.exists(path):
        sys.exit(f'Font not found: {path}\n'
                 'Install IBM Plex fonts (apt install fonts-ibm-plex) '
                 'or update the path constants above.')

BG          = (10,  10,  12)
WIN_BG      = (20,  20,  24)
WIN_CHROME  = (30,  30,  35)
WIN_BORDER  = (48,  48,  56)
EMERALD     = (16,  185, 129)
WHITE       = (245, 245, 250)
MUTED       = (120, 120, 135)
DIM         = (60,  62,  70)

img = Image.new('RGB', (W, H), BG)

# Subtle radial emerald glow
glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
ImageDraw.Draw(glow).ellipse([200, 100, 1000, 530], fill=EMERALD + (18,))
glow = glow.filter(ImageFilter.GaussianBlur(radius=120))
img  = Image.alpha_composite(img.convert('RGBA'), glow).convert('RGB')

# Window shadow
shadow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
ImageDraw.Draw(shadow).rounded_rectangle([76, 80, 1128, 558], radius=14, fill=(0, 0, 0, 120))
shadow = shadow.filter(ImageFilter.GaussianBlur(radius=14))
img = Image.alpha_composite(img.convert('RGBA'), shadow).convert('RGB')

draw = ImageDraw.Draw(img)

# Window body + chrome
CHROME_H = 44
PAD, R = 72, 14
draw.rounded_rectangle([PAD, PAD, W-PAD, H-PAD], radius=R, fill=WIN_BG, outline=WIN_BORDER, width=1)
draw.rounded_rectangle([PAD, PAD, W-PAD, PAD+CHROME_H], radius=R, fill=WIN_CHROME)
draw.rectangle([PAD, PAD+CHROME_H//2, W-PAD, PAD+CHROME_H], fill=WIN_CHROME)
draw.line([(PAD, PAD+CHROME_H), (W-PAD, PAD+CHROME_H)], fill=WIN_BORDER, width=1)

# Traffic-light dots
for i, col in enumerate([(255,95,86),(255,189,46),(39,201,63)]):
    cx = PAD + 22 + i*22
    cy = PAD + CHROME_H // 2
    draw.ellipse([cx-6, cy-6, cx+6, cy+6], fill=col)

# Chrome title
fn_chrome = ImageFont.truetype(MONO, 18)
label = 'bayram.sh — zsh'
lw = fn_chrome.getbbox(label)[2]
draw.text((PAD + (W - 2*PAD - lw)//2, PAD + 12), label, fill=MUTED, font=fn_chrome)

# Content
CX   = PAD + 44
CY   = PAD + CHROME_H + 32
LH   = 42
fn_mono = ImageFont.truetype(MONO, 26)
fn_bold = ImageFont.truetype(SANS_BOLD, 66)
fn_light= ImageFont.truetype(SANS_LIGHT, 34)

# Prompt line
draw.text((CX, CY), '~ ', fill=EMERALD, font=fn_mono)
draw.text((CX + fn_mono.getbbox('~ ')[2], CY), 'whois bayram.sh', fill=WHITE, font=fn_mono)

# Name + title
draw.text((CX, CY + LH + 8),       'Bayram Şahin',                           fill=WHITE, font=fn_bold)
draw.text((CX, CY + LH + 8 + 80),  'Full-Stack Developer & DevOps Practitioner', fill=MUTED, font=fn_light)

# Separator
SEP_Y = CY + LH + 8 + 80 + 50
draw.line([(CX, SEP_Y), (W-PAD-44, SEP_Y)], fill=DIM, width=1)

# Key-value rows
fn_kv = ImageFont.truetype(MONO, 26)
KV_Y = SEP_Y + 18
draw.text((CX,       KV_Y),      'location   ', fill=DIM,   font=fn_kv)
draw.text((CX + 220, KV_Y),      'Turkey',      fill=MUTED, font=fn_kv)
draw.text((CX,       KV_Y + LH), 'focus      ', fill=DIM,   font=fn_kv)
draw.text((CX + 220, KV_Y + LH), 'systems · cloud · open-source', fill=MUTED, font=fn_kv)

# Cursor
draw.text((CX, KV_Y + LH*2 + 14), '~ ', fill=EMERALD, font=fn_mono)
draw.text((CX + fn_mono.getbbox('~ ')[2], KV_Y + LH*2 + 14), '▊', fill=EMERALD, font=fn_mono)

img.save('apps/web/public/og-image.jpg', quality=90, optimize=True)
print('Saved apps/web/public/og-image.jpg')
EOF
```

## Layout wiring

`apps/web/src/layouts/Layout.astro` references this image through:

- `meta[property="og:image"]`
- `meta[name="twitter:image"]`
