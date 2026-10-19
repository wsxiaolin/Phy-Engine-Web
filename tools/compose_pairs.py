#!/usr/bin/env python3
"""Compose Unity-source vs web side-by-side pair images from
build/refshot/{id}.png + build/webshot/{id}.png  →  build/compare/{id}.png
Also emits build/compare/grid_{g}.png (2x3 pair sheets, 6 components each)
for quick VLM scanning. Supports transparent PNGs (alpha-composite on bg)."""
import os, sys, json
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(ROOT, 'build', 'refshot')
WEB = os.path.join(ROOT, 'build', 'webshot')
OUT = os.path.join(ROOT, 'build', 'compare')
BG = (224, 227, 232)
os.makedirs(OUT, exist_ok=True)

cat = json.load(open(os.path.join(ROOT, 'build/assets/catalog.json')))
items = cat.get('items') if isinstance(cat, dict) else cat
SUPPORTED = ["Ground Component", "Resistor", "Basic Capacitor", "Basic Inductor", "Battery Source", "Simple Switch", "Push Switch", "Air Switch", "Transformer", "Mutual Inductor", "Rectifier", "Logic Input", "Logic Output", "Or Gate", "And Gate", "Nand Gate", "Nor Gate", "Xor Gate", "Xnor Gate", "Imp Gate", "Nimp Gate", "Yes Gate", "No Gate", "Schmitt Trigger", "Comparator", "JK Flipflop", "T Flipflop", "Real-T Flipflop", "Multiplier", "D Flipflop", "Half Adder", "Full Adder", "Half Subtractor", "Full Subtractor", "Counter", "Random Generator"]
friendly = {i['ModelID']: i.get('FriendlyName', '') for i in items}

def font(sz):
    for p in ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
              '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
              '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc'):
        if os.path.exists(p):
            try: return ImageFont.truetype(p, sz)
            except Exception: pass
    return ImageFont.load_default()

def flatten(img):
    if img.mode in ('RGBA', 'LA', 'P'):
        img = img.convert('RGBA')
        base = Image.new('RGB', img.size, BG)
        base.paste(img, mask=img.split()[3])
        return base
    return img.convert('RGB')

def pair(mid):
    rp = os.path.join(REF, mid.replace(' ', '_') + '.png')
    wp = os.path.join(WEB, mid.replace(' ', '_') + '.png')
    if not (os.path.exists(rp) and os.path.exists(wp)):
        return None
    r, w = flatten(Image.open(rp)), flatten(Image.open(wp))
    H = 560
    r = r.resize((int(r.width * H / r.height), H))
    w = w.resize((int(w.width * H / w.height), H))
    GAP, BAR, BOT = 10, 34, 30
    canvas = Image.new('RGB', (r.width + w.width + GAP, H + BAR + BOT), (250, 250, 250))
    canvas.paste(r, (0, BAR)); canvas.paste(w, (r.width + GAP, BAR))
    d = ImageDraw.Draw(canvas)
    f1, f2 = font(20), font(18)
    d.rectangle([0, 0, r.width - 1, BAR - 2], fill=(70, 90, 130))
    d.rectangle([r.width + GAP, 0, canvas.width - 1, BAR - 2], fill=(50, 120, 80))
    d.text((8, 6), 'Unity 源数据 (prefab/FBX/mat → GLB)', font=f1, fill=(255, 255, 255))
    d.text((r.width + GAP + 8, 6), 'web 场景实况', font=f1, fill=(255, 255, 255))
    d.text((8, BAR + H + 6), f'{mid}  {friendly.get(mid, "")}', font=f2, fill=(40, 40, 40))
    canvas.save(os.path.join(OUT, mid.replace(' ', '_') + '.png'))
    return canvas

def sheet(canvases, g):
    cw = max(c.width for c in canvases)
    ch = max(c.height for c in canvases)
    cols, rows = 2, 3
    sc = Image.new('RGB', (cols * cw + 12, rows * ch + 12), (30, 30, 34))
    for i, c in enumerate(canvases):
        sc.paste(c, (6 + (i % cols) * (cw + 2), 6 + (i // cols) * (ch + 2)))
    sc = sc.resize((sc.width // 2, sc.height // 2))
    sc.save(os.path.join(OUT, f'grid_{g}.png'))

def main():
    sheets, buf = [], []
    for g, start in enumerate(range(0, len(SUPPORTED), 6)):
        for mid in SUPPORTED[start:start + 6]:
            c = pair(mid)
            if c is None:
                print('MISS', mid)
                continue
            buf.append(c)
        if buf:
            sheet(buf, g); sheets.append(g)
        buf = []
    n = len([f for f in os.listdir(OUT) if f.endswith('.png') and not f.startswith('grid')])
    print(f'pairs={n} sheets={len(sheets)} → {OUT}')

if __name__ == '__main__':
    main()
