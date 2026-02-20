#!/usr/bin/env python3
"""
Generate apps/web/public/og-image.jpg — terminal window card.

Usage (from repo root):
  python3 apps/web/scripts/gen-og-image.py [log_line_1] [log_line_2]

If log lines are omitted the script reads from env var GIT_LOG_LINES
(newline-separated) or falls back to built-in placeholder lines.

Typical CI invocation:
  python3 apps/web/scripts/gen-og-image.py \
    "$(git log --all --oneline -2 | head -1)" \
    "$(git log --all --oneline -2 | tail -1)"
"""

import os
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ── Output path (relative to repo root, which is the cwd in CI) ──────────────
OUTPUT = Path('apps/web/public/og-image.jpg')

# ── Font paths (Debian/Ubuntu default; adjust if needed) ─────────────────────
# Use `fc-match -f '%{file}\n' 'IBM Plex Sans:style=Bold'` to find your path.
_FONT_DIR = Path('/usr/share/fonts/truetype/ibm-plex')
SANS_BOLD  = str(_FONT_DIR / 'IBMPlexSans-Bold.ttf')
SANS_LIGHT = str(_FONT_DIR / 'IBMPlexSans-Light.ttf')
MONO       = str(_FONT_DIR / 'IBMPlexMono-Regular.ttf')
MONO_BOLD  = str(_FONT_DIR / 'IBMPlexMono-Bold.ttf')

for _p in (SANS_BOLD, SANS_LIGHT, MONO, MONO_BOLD):
    if not Path(_p).exists():
        sys.exit(
            f'Font not found: {_p}\n'
            'Install IBM Plex fonts (apt install fonts-ibm-plex) '
            'or update the path constants at the top of this script.'
        )

# ── Git log lines ─────────────────────────────────────────────────────────────
MAX_MSG_CHARS = 52  # truncate long commit subjects so lines stay inside the window

def _truncate(line: str, max_chars: int = MAX_MSG_CHARS) -> str:
    """Truncate at max_chars, appending … if needed."""
    if len(line) <= max_chars:
        return line
    return line[:max_chars - 1] + '…'

PLACEHOLDER_LINES = [
    '08ab0fd feat(web): your latest commits appear here',
    'bd8af60 fix(lyricist): regenerated on every deploy',
]

def _resolve_log_lines() -> tuple[str, str]:
    if len(sys.argv) >= 3:
        return _truncate(sys.argv[1]), _truncate(sys.argv[2])
    if len(sys.argv) == 2:
        parts = sys.argv[1].splitlines()
        a = _truncate(parts[0]) if len(parts) > 0 else PLACEHOLDER_LINES[0]
        b = _truncate(parts[1]) if len(parts) > 1 else PLACEHOLDER_LINES[1]
        return a, b
    env = os.environ.get('GIT_LOG_LINES', '')
    if env.strip():
        parts = [l for l in env.splitlines() if l.strip()]
        a = _truncate(parts[0]) if len(parts) > 0 else PLACEHOLDER_LINES[0]
        b = _truncate(parts[1]) if len(parts) > 1 else PLACEHOLDER_LINES[1]
        return a, b
    return PLACEHOLDER_LINES[0], PLACEHOLDER_LINES[1]

LOG_LINE_1, LOG_LINE_2 = _resolve_log_lines()

# ── Dimensions & palette ──────────────────────────────────────────────────────
W, H = 1200, 630

BG          = (10,  10,  12)
WIN_BG      = (20,  20,  24)
WIN_CHROME  = (30,  30,  35)
WIN_BORDER  = (48,  48,  56)
EMERALD     = (16,  185, 129)
WHITE       = (245, 245, 250)
MUTED       = (120, 120, 135)
DIM         = (60,  62,  70)
HASH_COLOR  = (96,  165, 250)   # blue — same as KnowledgeGraph project-node color

# ── Image ─────────────────────────────────────────────────────────────────────
img = Image.new('RGB', (W, H), BG)

# Subtle radial emerald glow
glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
ImageDraw.Draw(glow).ellipse([200, 100, 1000, 530], fill=EMERALD + (18,))
glow = glow.filter(ImageFilter.GaussianBlur(radius=120))
img  = Image.alpha_composite(img.convert('RGBA'), glow).convert('RGB')

# Window shadow
shadow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
ImageDraw.Draw(shadow).rounded_rectangle(
    [76, 80, W - 72 + 4, H - 72 + 8], radius=14, fill=(0, 0, 0, 120)
)
shadow = shadow.filter(ImageFilter.GaussianBlur(radius=14))
img = Image.alpha_composite(img.convert('RGBA'), shadow).convert('RGB')

draw = ImageDraw.Draw(img)

PAD, CHROME_H, R = 72, 44, 14

# Window body
draw.rounded_rectangle(
    [PAD, PAD, W - PAD, H - PAD],
    radius=R, fill=WIN_BG, outline=WIN_BORDER, width=1,
)

# Chrome bar
draw.rounded_rectangle([PAD, PAD, W - PAD, PAD + CHROME_H], radius=R, fill=WIN_CHROME)
draw.rectangle([PAD, PAD + CHROME_H // 2, W - PAD, PAD + CHROME_H], fill=WIN_CHROME)
draw.line([(PAD, PAD + CHROME_H), (W - PAD, PAD + CHROME_H)], fill=WIN_BORDER, width=1)

# Traffic-light dots
for i, col in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
    cx = PAD + 22 + i * 22
    cy = PAD + CHROME_H // 2
    draw.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=col)

# Chrome title
fn_chrome = ImageFont.truetype(MONO, 18)
label = 'bayram.sh — zsh'
lw = fn_chrome.getbbox(label)[2]
draw.text((PAD + (W - 2 * PAD - lw) // 2, PAD + 12), label, fill=MUTED, font=fn_chrome)

# ── Terminal content ──────────────────────────────────────────────────────────
CX = PAD + 44
CY = PAD + CHROME_H + 32
LH = 42

fn_mono  = ImageFont.truetype(MONO, 26)
fn_bold  = ImageFont.truetype(SANS_BOLD, 66)
fn_light = ImageFont.truetype(SANS_LIGHT, 34)

# Prompt 1: whois
draw.text((CX, CY), '~ ', fill=EMERALD, font=fn_mono)
draw.text((CX + fn_mono.getbbox('~ ')[2], CY), 'whois bayram.sh', fill=WHITE, font=fn_mono)

# Name + title
draw.text((CX, CY + LH + 8),      'Bayram Şahin',                                fill=WHITE, font=fn_bold)
draw.text((CX, CY + LH + 8 + 80), 'Full-Stack Developer & DevOps Practitioner',  fill=MUTED, font=fn_light)

# Separator
SEP_Y = CY + LH + 8 + 80 + 50
draw.line([(CX, SEP_Y), (W - PAD - 44, SEP_Y)], fill=DIM, width=1)

# Prompt 2: git log
GIT_Y = SEP_Y + 18
draw.text((CX, GIT_Y), '~ ', fill=EMERALD, font=fn_mono)
draw.text(
    (CX + fn_mono.getbbox('~ ')[2], GIT_Y),
    'git log --all --oneline -2',
    fill=WHITE, font=fn_mono,
)

# Commit log lines — hash in blue, message in muted
def draw_log_line(y: int, line: str) -> None:
    """Render a `shortHash message` line with the hash highlighted."""
    parts = line.split(' ', 1)
    hash_part = parts[0] if parts else line
    msg_part  = (' ' + parts[1]) if len(parts) > 1 else ''
    draw.text((CX, y), hash_part, fill=HASH_COLOR, font=fn_mono)
    hw = fn_mono.getbbox(hash_part)[2]
    draw.text((CX + hw, y), msg_part, fill=MUTED, font=fn_mono)

draw_log_line(GIT_Y + LH,      LOG_LINE_1)
draw_log_line(GIT_Y + LH * 2,  LOG_LINE_2)

# Cursor
CURSOR_Y = GIT_Y + LH * 3 + 6
draw.text((CX, CURSOR_Y), '~ ', fill=EMERALD, font=fn_mono)
draw.text((CX + fn_mono.getbbox('~ ')[2], CURSOR_Y), '▊', fill=EMERALD, font=fn_mono)

# ── Save ──────────────────────────────────────────────────────────────────────
img.save(str(OUTPUT), quality=90, optimize=True)
print(f'Saved {OUTPUT}')
